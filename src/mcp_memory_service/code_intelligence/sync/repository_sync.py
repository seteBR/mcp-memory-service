# src/mcp_memory_service/code_intelligence/sync/repository_sync.py
"""
Repository synchronization for code intelligence.
Enhanced for ConnectivityTestingTool MCP Code Intelligence project.
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

from ..chunker.factory import ChunkerFactory
from ...models.code import CodeChunk
from .file_watcher import FileWatcher, FileChangeEvent, ChangeType

logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """Metadata about a file in the repository."""
    path: str
    size: int
    mtime: float
    content_hash: str
    last_synced: float
    chunk_count: int = 0


@dataclass 
class SyncResult:
    """Result of a repository synchronization operation."""
    repository_name: str
    repository_path: str
    total_files: int
    processed_files: int
    new_files: int
    modified_files: int
    deleted_files: int
    total_chunks: int
    new_chunks: int
    updated_chunks: int
    deleted_chunks: int
    sync_duration: float
    errors: List[str] = field(default_factory=list)
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_files == 0:
            return 100.0
        return (self.processed_files / self.total_files) * 100.0
    
    def add_error(self, error: str):
        """Add an error to the result."""
        self.errors.append(error)
        logger.error(f"Sync error in {self.repository_name}: {error}")


class RepositorySync:
    """Handles synchronization of code repositories with the intelligence system."""
    
    def __init__(self, storage_backend, enable_file_watching: bool = True):
        self.storage = storage_backend
        self.enable_file_watching = enable_file_watching
        
        # File metadata cache (in-memory for now, could be persisted later)
        self.file_cache: Dict[str, Dict[str, FileMetadata]] = {}  # repo_name -> file_path -> metadata
        
        # Repository metadata
        self.repositories: Dict[str, Dict[str, Any]] = {}  # repo_name -> metadata
        
        # File watcher for real-time updates
        if enable_file_watching:
            self.file_watcher = FileWatcher(debounce_delay=1.0)  # 1 second debounce
            self.file_watcher.add_change_callback(self._handle_file_change)
        else:
            self.file_watcher = None
    
    async def sync_repository(self, repository_path: str, repository_name: str, 
                            incremental: bool = True, force_full: bool = False) -> SyncResult:
        """Synchronize a repository with the code intelligence system."""
        start_time = time.time()
        
        logger.info(f"Starting {'incremental' if incremental and not force_full else 'full'} sync of repository: {repository_name}")
        
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
        
        try:
            # Validate repository path
            repo_path = Path(repository_path).resolve()
            if not repo_path.exists() or not repo_path.is_dir():
                result.add_error(f"Invalid repository path: {repository_path}")
                return result
            
            # Store repository metadata first for file processing
            self.repositories[repository_name] = {
                'path': str(repo_path),
                'last_sync': time.time(),
                'total_files': 0,  # Will be updated later
                'total_chunks': 0,  # Will be updated later
                'sync_type': 'full' if not incremental or force_full else 'incremental'
            }
            
            # Get current file metadata
            current_files = await self._scan_repository(repo_path)
            result.total_files = len(current_files)
            
            # Initialize cache if needed
            if repository_name not in self.file_cache:
                self.file_cache[repository_name] = {}
            
            cached_files = self.file_cache[repository_name]
            
            # Determine sync strategy
            if not incremental or force_full or not cached_files:
                # Full sync
                await self._full_sync(repository_name, current_files, result)
            else:
                # Incremental sync
                await self._incremental_sync(repository_name, current_files, cached_files, result)
            
            # Update repository metadata with final results
            self.repositories[repository_name].update({
                'last_sync': time.time(),
                'total_files': result.total_files,
                'total_chunks': result.total_chunks,
                'sync_type': 'full' if not incremental or force_full else 'incremental'
            })
            
            # Start watching if enabled
            if self.file_watcher and not self.file_watcher.is_watching(str(repo_path)):
                self.file_watcher.add_repository(str(repo_path), repository_name)
                if not self.file_watcher.is_running:
                    self.file_watcher.start()
            
            result.sync_duration = time.time() - start_time
            logger.info(f"Repository sync completed: {repository_name} in {result.sync_duration:.2f}s")
            
        except Exception as e:
            result.add_error(f"Sync failed: {str(e)}")
            logger.error(f"Repository sync failed for {repository_name}: {e}")
        
        return result
    
    async def _scan_repository(self, repo_path: Path) -> Dict[str, FileMetadata]:
        """Scan repository and create file metadata."""
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
    
    async def _full_sync(self, repository_name: str, current_files: Dict[str, FileMetadata], 
                        result: SyncResult):
        """Perform a full synchronization."""
        for file_path, metadata in current_files.items():
            try:
                chunk_count = await self._process_file(repository_name, file_path, metadata)
                metadata.chunk_count = chunk_count
                metadata.last_synced = time.time()
                
                result.processed_files += 1
                result.new_files += 1
                result.total_chunks += chunk_count
                result.new_chunks += chunk_count
                
            except Exception as e:
                result.add_error(f"Failed to process file {file_path}: {str(e)}")
        
        # Update cache
        self.file_cache[repository_name] = current_files
    
    async def _incremental_sync(self, repository_name: str, current_files: Dict[str, FileMetadata],
                               cached_files: Dict[str, FileMetadata], result: SyncResult):
        """Perform an incremental synchronization."""
        
        # Find new and modified files
        for file_path, metadata in current_files.items():
            cached_metadata = cached_files.get(file_path)
            
            if not cached_metadata:
                # New file
                try:
                    chunk_count = await self._process_file(repository_name, file_path, metadata)
                    metadata.chunk_count = chunk_count
                    metadata.last_synced = time.time()
                    
                    result.processed_files += 1
                    result.new_files += 1
                    result.total_chunks += chunk_count
                    result.new_chunks += chunk_count
                    
                except Exception as e:
                    result.add_error(f"Failed to process new file {file_path}: {str(e)}")
                    
            elif (metadata.content_hash != cached_metadata.content_hash or 
                  metadata.mtime > cached_metadata.mtime):
                # Modified file
                try:
                    # Delete old chunks first
                    await self._delete_file_chunks(repository_name, file_path)
                    
                    # Process updated file
                    chunk_count = await self._process_file(repository_name, file_path, metadata)
                    metadata.chunk_count = chunk_count
                    metadata.last_synced = time.time()
                    
                    result.processed_files += 1
                    result.modified_files += 1
                    result.total_chunks += chunk_count
                    result.updated_chunks += chunk_count
                    result.deleted_chunks += cached_metadata.chunk_count
                    
                except Exception as e:
                    result.add_error(f"Failed to process modified file {file_path}: {str(e)}")
        
        # Find deleted files
        for file_path, cached_metadata in cached_files.items():
            if file_path not in current_files:
                try:
                    await self._delete_file_chunks(repository_name, file_path)
                    result.deleted_files += 1
                    result.deleted_chunks += cached_metadata.chunk_count
                    
                except Exception as e:
                    result.add_error(f"Failed to delete chunks for file {file_path}: {str(e)}")
        
        # Update cache
        self.file_cache[repository_name] = current_files
    
    async def _process_file(self, repository_name: str, file_path: str, metadata: FileMetadata) -> int:
        """Process a single file and store its chunks."""
        # Get the chunker for this file
        factory = ChunkerFactory()
        chunker = factory.get_chunker(file_path)
        
        # Read file content
        full_path = Path(self.repositories.get(repository_name, {}).get('path', '')) / file_path
        with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Chunk the content
        chunks = chunker.chunk_content(content, file_path, repository_name)
        
        # Store chunks
        stored_count = 0
        for chunk in chunks:
            memory = chunk.to_memory()
            success, _ = await self.storage.store(memory)
            if success:
                stored_count += 1
        
        logger.debug(f"Processed file {file_path}: {stored_count}/{len(chunks)} chunks stored")
        return len(chunks)
    
    async def _delete_file_chunks(self, repository_name: str, file_path: str):
        """Delete all chunks for a specific file."""
        # This would require a way to query chunks by file path
        # For now, we'll log this as a TODO
        logger.debug(f"TODO: Delete chunks for file {file_path} in repository {repository_name}")
        # Implementation would depend on storage backend supporting file-based deletion
    
    async def _handle_file_change(self, event: FileChangeEvent, repository_name: str):
        """Handle file system change events."""
        logger.info(f"File change detected: {event.change_type.value} {event.path} in {repository_name}")
        
        try:
            if event.change_type in [ChangeType.CREATED, ChangeType.MODIFIED]:
                # Process the changed file
                file_path = Path(event.path)
                repo_path = Path(self.repositories[repository_name]['path'])
                relative_path = str(file_path.relative_to(repo_path))
                
                # Create metadata for the file
                stat = file_path.stat()
                with open(file_path, 'rb') as f:
                    content_hash = hashlib.sha256(f.read()).hexdigest()
                
                metadata = FileMetadata(
                    path=relative_path,
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    content_hash=content_hash,
                    last_synced=0.0
                )
                
                # Delete old chunks if this is a modification
                if event.change_type == ChangeType.MODIFIED:
                    await self._delete_file_chunks(repository_name, relative_path)
                
                # Process the file
                chunk_count = await self._process_file(repository_name, relative_path, metadata)
                metadata.chunk_count = chunk_count
                metadata.last_synced = time.time()
                
                # Update cache
                if repository_name not in self.file_cache:
                    self.file_cache[repository_name] = {}
                self.file_cache[repository_name][relative_path] = metadata
                
                logger.info(f"Real-time sync: processed {relative_path} ({chunk_count} chunks)")
                
            elif event.change_type == ChangeType.DELETED:
                # Remove from cache and delete chunks
                file_path = Path(event.path)
                repo_path = Path(self.repositories[repository_name]['path'])
                relative_path = str(file_path.relative_to(repo_path))
                
                await self._delete_file_chunks(repository_name, relative_path)
                
                if repository_name in self.file_cache:
                    self.file_cache[repository_name].pop(relative_path, None)
                
                logger.info(f"Real-time sync: deleted chunks for {relative_path}")
                
        except Exception as e:
            logger.error(f"Error handling file change {event.path}: {e}")
    
    def get_repository_status(self, repository_name: str) -> Optional[Dict[str, Any]]:
        """Get status information for a repository."""
        if repository_name not in self.repositories:
            return None
        
        repo_info = self.repositories[repository_name].copy()
        repo_info['cached_files'] = len(self.file_cache.get(repository_name, {}))
        repo_info['is_watching'] = (self.file_watcher and 
                                   self.file_watcher.is_watching(repo_info['path']))
        
        return repo_info
    
    def list_repositories(self) -> List[Dict[str, Any]]:
        """List all synchronized repositories."""
        return [
            {
                'name': name,
                **self.get_repository_status(name)
            }
            for name in self.repositories.keys()
        ]
    
    def stop_watching(self):
        """Stop file watching."""
        if self.file_watcher:
            self.file_watcher.stop()
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        if hasattr(self, 'file_watcher') and self.file_watcher:
            self.file_watcher.stop()