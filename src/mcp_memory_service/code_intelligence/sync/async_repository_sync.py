"""
Asynchronous repository synchronization that doesn't block other operations.
This implementation uses background tasks and batch processing to avoid blocking.
"""

import asyncio
import hashlib
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple, Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import queue
import threading

from ..chunker.factory import ChunkerFactory
from ...models.code import CodeChunk
from .repository_sync import FileMetadata, SyncResult, RepositorySync

logger = logging.getLogger(__name__)


class AsyncRepositorySync(RepositorySync):
    """Non-blocking repository synchronization using background processing."""
    
    def __init__(self, storage_backend, enable_file_watching: bool = True, 
                 max_queue_size: int = 10000, batch_size: int = 100):
        super().__init__(storage_backend, enable_file_watching)
        
        # Queue for chunks to be processed
        self.chunk_queue = queue.Queue(maxsize=max_queue_size)
        self.batch_size = batch_size
        
        # Background worker thread for processing chunks
        self.worker_thread = None
        self.worker_running = False
        
        # Track active sync operations
        self.active_syncs: Dict[str, SyncResult] = {}
        self.sync_lock = threading.Lock()
        
        # Start background worker
        self._start_worker()
    
    def _start_worker(self):
        """Start background worker thread for processing chunks."""
        if not self.worker_thread or not self.worker_thread.is_alive():
            self.worker_running = True
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info("Started background chunk processing worker")
    
    def _worker_loop(self):
        """Background worker loop for processing chunks."""
        batch = []
        last_process_time = time.time()
        
        while self.worker_running:
            try:
                # Try to get items with timeout
                try:
                    item = self.chunk_queue.get(timeout=1.0)
                    if item is None:  # Shutdown signal
                        break
                    batch.append(item)
                except queue.Empty:
                    pass
                
                # Process batch if it's full or timeout reached
                should_process = (
                    len(batch) >= self.batch_size or 
                    (len(batch) > 0 and time.time() - last_process_time > 5.0)  # 5 second timeout
                )
                
                if should_process and batch:
                    # Process batch asynchronously
                    asyncio.run(self._process_batch(batch))
                    batch = []
                    last_process_time = time.time()
                    
            except Exception as e:
                logger.error(f"Error in chunk processing worker: {e}")
                # Don't lose the batch on error
                if batch:
                    for item in batch:
                        try:
                            self.chunk_queue.put_nowait(item)
                        except queue.Full:
                            logger.warning("Queue full, dropping chunk")
                batch = []
    
    async def _process_batch(self, batch: List[Tuple[CodeChunk, str]]):
        """Process a batch of chunks asynchronously."""
        logger.debug(f"Processing batch of {len(batch)} chunks")
        
        # Group by repository
        repo_chunks = {}
        for chunk, repo_name in batch:
            if repo_name not in repo_chunks:
                repo_chunks[repo_name] = []
            repo_chunks[repo_name].append(chunk)
        
        # Process each repository's chunks
        for repo_name, chunks in repo_chunks.items():
            try:
                # Store chunks
                stored = 0
                for chunk in chunks:
                    memory = chunk.to_memory()
                    success, _ = await self.storage.store(memory)
                    if success:
                        stored += 1
                
                # Update sync result if active
                with self.sync_lock:
                    if repo_name in self.active_syncs:
                        result = self.active_syncs[repo_name]
                        result.total_chunks += len(chunks)
                        result.new_chunks += stored
                        
                logger.debug(f"Stored {stored}/{len(chunks)} chunks for {repo_name}")
                
            except Exception as e:
                logger.error(f"Error processing batch for {repo_name}: {e}")
                with self.sync_lock:
                    if repo_name in self.active_syncs:
                        self.active_syncs[repo_name].add_error(f"Batch processing error: {str(e)}")
    
    async def sync_repository(self, repository_path: str, repository_name: str, 
                            incremental: bool = True, force_full: bool = False) -> SyncResult:
        """Non-blocking repository synchronization."""
        start_time = time.time()
        
        logger.info(f"Starting async {'incremental' if incremental and not force_full else 'full'} sync of repository: {repository_name}")
        
        # Initialize result
        result = SyncResult(
            repository_name=repository_name,
            repository_path=repository_path,
            total_files=0,
            processed_files=0,
            new_files=0,
            modified_files=0,
            deleted_files=0,
            total_chunks=0,
            new_chunks=0,
            updated_chunks=0,
            deleted_chunks=0,
            sync_duration=0.0
        )
        
        # Track this sync operation
        with self.sync_lock:
            self.active_syncs[repository_name] = result
        
        try:
            # Validate repository path
            repo_path = Path(repository_path).resolve()
            if not repo_path.exists() or not repo_path.is_dir():
                result.add_error(f"Invalid repository path: {repository_path}")
                return result
            
            # Store repository metadata
            self.repositories[repository_name] = {
                'path': str(repo_path),
                'last_sync': time.time(),
                'total_files': 0,
                'total_chunks': 0,
                'sync_type': 'full' if not incremental or force_full else 'incremental'
            }
            
            # Start async file scanning
            scan_task = asyncio.create_task(self._scan_repository_async(repo_path))
            
            # Return immediately with initial result
            # The background worker will continue processing
            asyncio.create_task(self._complete_sync(
                repository_name, repo_path, scan_task, result, 
                incremental, force_full, start_time
            ))
            
            # Return partial result immediately
            result.sync_duration = time.time() - start_time
            return result
            
        except Exception as e:
            result.add_error(f"Sync initialization failed: {str(e)}")
            logger.error(f"Repository sync failed for {repository_name}: {e}")
            result.sync_duration = time.time() - start_time
            return result
    
    async def _complete_sync(self, repository_name: str, repo_path: Path, 
                           scan_task: asyncio.Task, result: SyncResult,
                           incremental: bool, force_full: bool, start_time: float):
        """Complete the sync operation in the background."""
        try:
            # Wait for scan to complete
            current_files = await scan_task
            result.total_files = len(current_files)
            
            # Initialize cache if needed
            if repository_name not in self.file_cache:
                self.file_cache[repository_name] = {}
            
            cached_files = self.file_cache[repository_name]
            
            # Process files asynchronously
            if not incremental or force_full or not cached_files:
                # Full sync - process all files
                for file_path, metadata in current_files.items():
                    await self._queue_file_for_processing(repository_name, file_path, metadata)
                    result.new_files += 1
                    result.processed_files += 1
            else:
                # Incremental sync
                # New files
                new_files = set(current_files.keys()) - set(cached_files.keys())
                for file_path in new_files:
                    await self._queue_file_for_processing(repository_name, file_path, current_files[file_path])
                    result.new_files += 1
                    result.processed_files += 1
                
                # Modified files
                for file_path, metadata in current_files.items():
                    if file_path in cached_files:
                        cached = cached_files[file_path]
                        if metadata.content_hash != cached.content_hash:
                            await self._queue_file_for_processing(repository_name, file_path, metadata)
                            result.modified_files += 1
                            result.processed_files += 1
                
                # Deleted files
                deleted_files = set(cached_files.keys()) - set(current_files.keys())
                result.deleted_files = len(deleted_files)
                # TODO: Handle deletion of chunks for deleted files
            
            # Update cache
            self.file_cache[repository_name] = current_files
            
            # Update final duration
            result.sync_duration = time.time() - start_time
            
            # Update repository metadata
            self.repositories[repository_name].update({
                'last_sync': time.time(),
                'total_files': result.total_files,
                'total_chunks': result.total_chunks,
                'sync_type': 'full' if not incremental or force_full else 'incremental'
            })
            
            logger.info(f"Repository sync completed (async): {repository_name} in {result.sync_duration:.2f}s")
            
        except Exception as e:
            result.add_error(f"Background sync failed: {str(e)}")
            logger.error(f"Background sync error for {repository_name}: {e}")
        finally:
            # Remove from active syncs after a delay to allow final updates
            await asyncio.sleep(10)
            with self.sync_lock:
                self.active_syncs.pop(repository_name, None)
    
    async def _scan_repository_async(self, repo_path: Path) -> Dict[str, FileMetadata]:
        """Scan repository asynchronously."""
        loop = asyncio.get_event_loop()
        
        # Run the scan in a thread pool to avoid blocking
        with ThreadPoolExecutor(max_workers=4) as executor:
            return await loop.run_in_executor(
                executor, 
                self._scan_repository_sync, 
                repo_path
            )
    
    def _scan_repository_sync(self, repo_path: Path) -> Dict[str, FileMetadata]:
        """Synchronous repository scanning (runs in thread pool)."""
        files = {}
        factory = ChunkerFactory()
        supported_extensions = factory.get_supported_extensions()
        
        for file_path in repo_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in supported_extensions:
                # Skip common directories that shouldn't be indexed
                if any(part.startswith('.') or part in ['node_modules', '__pycache__', 'target', 'build', 'dist', 'venv', 'env'] 
                       for part in file_path.parts):
                    continue
                
                try:
                    stat = file_path.stat()
                    
                    # Calculate content hash
                    with open(file_path, 'rb') as f:
                        content_hash = hashlib.sha256(f.read()).hexdigest()
                    
                    relative_path = str(file_path.relative_to(repo_path))
                    files[relative_path] = FileMetadata(
                        path=relative_path,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                        content_hash=content_hash,
                        last_synced=0.0
                    )
                    
                except (OSError, IOError) as e:
                    logger.warning(f"Could not read file {file_path}: {e}")
        
        return files
    
    async def _queue_file_for_processing(self, repository_name: str, file_path: str, metadata: FileMetadata):
        """Queue a file for background processing."""
        factory = ChunkerFactory()
        chunker = factory.get_chunker(file_path)
        
        # Read file content
        full_path = Path(self.repositories.get(repository_name, {}).get('path', '')) / file_path
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Chunk the content
            chunks = chunker.chunk_content(content, file_path, repository_name)
            
            # Queue chunks for processing
            for chunk in chunks:
                try:
                    self.chunk_queue.put_nowait((chunk, repository_name))
                except queue.Full:
                    logger.warning(f"Chunk queue full, waiting...")
                    self.chunk_queue.put((chunk, repository_name))  # Blocking put
                    
            # Update metadata
            metadata.last_synced = time.time()
            metadata.chunk_count = len(chunks)
            
        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            with self.sync_lock:
                if repository_name in self.active_syncs:
                    self.active_syncs[repository_name].add_error(f"File processing error: {file_path}: {str(e)}")
    
    def get_sync_status(self, repository_name: str) -> Optional[Dict[str, Any]]:
        """Get current sync status for a repository."""
        with self.sync_lock:
            if repository_name in self.active_syncs:
                result = self.active_syncs[repository_name]
                return {
                    'active': True,
                    'progress': {
                        'total_files': result.total_files,
                        'processed_files': result.processed_files,
                        'total_chunks': result.total_chunks,
                        'duration': time.time() - (result.sync_duration or 0),
                        'errors': len(result.errors)
                    }
                }
        
        # Check if repository exists but not actively syncing
        if repository_name in self.repositories:
            return {
                'active': False,
                'last_sync': self.repositories[repository_name].get('last_sync'),
                'total_files': self.repositories[repository_name].get('total_files', 0),
                'total_chunks': self.repositories[repository_name].get('total_chunks', 0)
            }
        
        return None
    
    def shutdown(self):
        """Shutdown the async sync service."""
        logger.info("Shutting down async repository sync...")
        
        # Stop worker
        self.worker_running = False
        self.chunk_queue.put(None)  # Shutdown signal
        
        if self.worker_thread:
            self.worker_thread.join(timeout=5.0)
        
        # Stop file watcher if enabled
        if self.file_watcher:
            self.file_watcher.stop()