"""
Fixed AsyncRepositorySync that batches storage operations to avoid lock contention.
"""
import asyncio
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import logging
from concurrent.futures import ThreadPoolExecutor

from ..chunker.factory import ChunkerFactory
from ..chunker.extended_factory import initialize_extended_file_support
from ...models.memory import Memory
from ...utils.hashing import generate_content_hash

# Initialize extended file support
initialize_extended_file_support()

logger = logging.getLogger(__name__)


@dataclass
class FileMetadata:
    """Metadata for a scanned file."""
    path: str
    size: int
    modified: float
    content_hash: str


@dataclass
class SyncResult:
    """Result of repository synchronization."""
    repository_name: str = ""
    repository_path: str = ""
    total_files: int = 0
    processed_files: int = 0
    new_files: int = 0
    modified_files: int = 0
    deleted_files: int = 0
    total_chunks: int = 0
    new_chunks: int = 0
    updated_chunks: int = 0
    deleted_chunks: int = 0
    files_scanned: int = 0
    sync_duration: float = 0.0
    errors: List[str] = field(default_factory=list)
    success_rate: float = 100.0
    
    def add_error(self, error: str):
        """Add an error to the result."""
        self.errors.append(error)
        if self.total_files > 0:
            self.success_rate = ((self.processed_files - len(self.errors)) / self.total_files) * 100


class AsyncRepositorySync:
    """
    Fixed version that batches memory storage to avoid lock contention.
    All operations complete before returning.
    """
    
    def __init__(self, storage_backend):
        self.storage = storage_backend
        self.repositories: Dict[str, dict] = {}
        self.file_cache: Dict[str, Dict[str, FileMetadata]] = {}
        self.active_syncs: Dict[str, SyncResult] = {}  # For compatibility
        self.sync_lock = asyncio.Lock()  # For compatibility
        
        # Thread pool for file I/O operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        # Semaphore to limit concurrent chunk processing
        self.chunk_semaphore = asyncio.Semaphore(10)
        
    async def sync_repository(
        self,
        repository_path: str,
        repository_name: str,
        incremental: bool = True,
        force_full: bool = False
    ) -> SyncResult:
        """
        Synchronize a repository with batched storage operations.
        Completes all work before returning.
        """
        start_time = time.time()
        
        # Initialize result
        result = SyncResult(
            repository_name=repository_name,
            repository_path=repository_path
        )
        
        try:
            # Validate repository path
            repo_path = Path(repository_path).resolve()
            if not repo_path.exists() or not repo_path.is_dir():
                result.add_error(f"Invalid repository path: {repository_path}")
                result.sync_duration = time.time() - start_time
                return result
            
            # Update repository metadata
            self.repositories[repository_name] = {
                'path': str(repo_path),
                'last_sync': time.time(),
                'sync_type': 'full' if not incremental or force_full else 'incremental'
            }
            
            # Step 1: Scan repository for files
            logger.info(f"Scanning repository: {repository_name}")
            current_files = await self._scan_repository_async(repo_path)
            result.files_scanned = len(current_files)
            result.total_files = len(current_files)
            
            if not current_files:
                logger.info(f"No supported files found in {repository_path}")
                result.sync_duration = time.time() - start_time
                return result
            
            # Step 2: Determine which files to process
            cached_files = self.file_cache.get(repository_name, {}) if incremental and not force_full else {}
            files_to_process = []
            
            for file_path, metadata in current_files.items():
                if file_path not in cached_files:
                    files_to_process.append((file_path, metadata, 'new'))
                    result.new_files += 1
                elif metadata.content_hash != cached_files[file_path].content_hash:
                    files_to_process.append((file_path, metadata, 'modified'))
                    result.modified_files += 1
            
            # Deleted files (for incremental sync)
            if incremental and not force_full:
                deleted_files = set(cached_files.keys()) - set(current_files.keys())
                result.deleted_files = len(deleted_files)
                # TODO: Handle deletion of chunks for deleted files
            
            # Step 3: Process files and collect memories
            logger.info(f"Processing {len(files_to_process)} files for {repository_name}")
            
            # Collect all memories to store in batch
            all_memories = []
            
            # Process files in batches
            batch_size = 10
            for i in range(0, len(files_to_process), batch_size):
                batch = files_to_process[i:i + batch_size]
                
                # Process batch concurrently and collect memories
                tasks = [
                    self._process_file_for_memories(file_info, repository_name, result)
                    for file_info in batch
                ]
                
                # Wait for batch to complete and collect memories
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                for batch_result in batch_results:
                    if isinstance(batch_result, list):
                        all_memories.extend(batch_result)
                    elif isinstance(batch_result, Exception):
                        logger.error(f"Error processing file: {batch_result}")
                        result.add_error(str(batch_result))
                
                # Log progress
                progress = (result.processed_files / len(files_to_process)) * 100
                logger.info(f"Progress: {result.processed_files}/{len(files_to_process)} files ({progress:.1f}%)")
            
            # Step 4: Store all memories in batch
            if all_memories:
                logger.info(f"Storing {len(all_memories)} memories in batch...")
                stored_count = await self._store_memories_batch(all_memories)
                result.total_chunks = stored_count
                logger.info(f"Stored {stored_count} memories successfully")
            
            # Step 5: Update cache
            self.file_cache[repository_name] = current_files
            
            # Update repository metadata
            self.repositories[repository_name].update({
                'last_sync': time.time(),
                'total_files': result.total_files,
                'total_chunks': result.total_chunks
            })
            
        except Exception as e:
            result.add_error(f"Sync failed: {str(e)}")
            logger.error(f"Repository sync failed for {repository_name}: {e}")
        
        finally:
            # Calculate final metrics
            result.sync_duration = time.time() - start_time
            
            logger.info(
                f"Repository sync completed: {repository_name} - "
                f"{result.processed_files}/{result.total_files} files, "
                f"{result.total_chunks} chunks in {result.sync_duration:.2f}s"
            )
        
        return result
    
    async def _process_file_for_memories(
        self, 
        file_info: tuple, 
        repository_name: str, 
        result: SyncResult
    ) -> List[Memory]:
        """Process a single file and return memories to store."""
        async with self.chunk_semaphore:
            return await self._process_single_file_for_memories(
                file_info, repository_name, result
            )
    
    async def _process_single_file_for_memories(
        self, 
        file_info: tuple, 
        repository_name: str, 
        result: SyncResult
    ) -> List[Memory]:
        """Process a single file and return memories."""
        file_path, metadata, status = file_info
        memories = []
        
        try:
            # Read file content
            loop = asyncio.get_event_loop()
            content = await loop.run_in_executor(
                self.executor,
                self._read_file,
                file_path
            )
            
            # Detect language
            factory = ChunkerFactory()
            language = self._detect_language(file_path)
            
            # Get appropriate chunker
            chunker = factory.get_chunker(language)
            if not chunker:
                chunker = factory.get_chunker('generic')
            
            # Chunk the content
            chunks = await loop.run_in_executor(
                self.executor,
                chunker.chunk_content,
                content,
                file_path
            )
            
            # Create memories for chunks
            for chunk in chunks:
                memory = Memory(
                    content=chunk.text,
                    content_hash=generate_content_hash(chunk.text),
                    memory_type="code_chunk",
                    metadata={
                        "file_path": file_path,
                        "repository": repository_name,
                        "language": language,
                        "chunk_type": chunk.chunk_type,
                        "chunk_id": chunk.chunk_id,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "code_chunk": True
                    }
                )
                memories.append(memory)
            
            result.processed_files += 1
            result.total_chunks += len(chunks)
            
        except Exception as e:
            result.add_error(f"Error processing {file_path}: {str(e)}")
            logger.error(f"Error processing file {file_path}: {e}")
        
        return memories
    
    async def _store_memories_batch(self, memories: List[Memory]) -> int:
        """Store memories in batch to minimize lock contention."""
        stored = 0
        batch_size = 50  # Store 50 memories at a time
        
        for i in range(0, len(memories), batch_size):
            batch = memories[i:i + batch_size]
            
            # Store each batch with a small delay to allow other operations
            for memory in batch:
                try:
                    await self.storage.store(memory)
                    stored += 1
                except Exception as e:
                    logger.error(f"Failed to store memory: {e}")
            
            # Small delay between batches to prevent lock starvation
            if i + batch_size < len(memories):
                await asyncio.sleep(0.1)
        
        return stored
    
    async def _scan_repository_async(self, repo_path: Path) -> Dict[str, FileMetadata]:
        """Scan repository for supported files."""
        loop = asyncio.get_event_loop()
        
        # Run the synchronous scan in thread pool
        return await loop.run_in_executor(
            self.executor,
            self._scan_repository_sync,
            repo_path
        )
    
    def _scan_repository_sync(self, repo_path: Path) -> Dict[str, FileMetadata]:
        """Synchronous repository scanning."""
        files = {}
        factory = ChunkerFactory()
        supported_extensions = factory.get_supported_extensions()
        
        # Excluded directories
        excluded_dirs = {
            'node_modules', '__pycache__', 'target', 'build', 'dist', 
            'venv', 'env', '.venv', '.env', 'virtualenv',
            '.git', '.svn', '.hg', '.bzr',
            'vendor', 'third_party', 'deps', 'dependencies',
            'packages', '.packages', 'bower_components',
            'coverage', '.coverage', 'htmlcov',
            '.pytest_cache', '.mypy_cache', '.ruff_cache',
            'site-packages', 'dist-packages',
            '.idea', '.vscode', '.eclipse'
        }
        
        for file_path in repo_path.rglob('*'):
            if not file_path.is_file():
                continue
            
            # Check if extension is supported
            file_ext = file_path.suffix.lower()
            if file_ext not in supported_extensions and file_path.name not in supported_extensions:
                continue
            
            # Skip excluded directories
            if any(part in excluded_dirs for part in file_path.parts):
                continue
            
            try:
                stat = file_path.stat()
                
                # Skip very large files (> 10MB)
                if stat.st_size > 10 * 1024 * 1024:
                    continue
                
                # Calculate content hash
                with open(file_path, 'rb') as f:
                    content_hash = hashlib.sha256(f.read()).hexdigest()
                
                files[str(file_path)] = FileMetadata(
                    path=str(file_path),
                    size=stat.st_size,
                    modified=stat.st_mtime,
                    content_hash=content_hash
                )
                
            except Exception as e:
                logger.warning(f"Error scanning file {file_path}: {e}")
        
        return files
    
    def _read_file(self, file_path: str) -> str:
        """Read file content."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Try with different encoding
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
    
    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        path = Path(file_path)
        ext = path.suffix.lower()
        
        language_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.go': 'go',
            '.rs': 'rust',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.h': 'c',
            '.hpp': 'cpp',
            '.cs': 'csharp',
            '.rb': 'ruby',
            '.php': 'php',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.r': 'r',
            '.m': 'matlab',
            '.jl': 'julia',
            '.sh': 'bash',
            '.ps1': 'powershell',
            '.sql': 'sql',
            '.html': 'html',
            '.css': 'css',
            '.xml': 'xml',
            '.json': 'json',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.md': 'markdown',
            '.rst': 'restructuredtext',
            '.tex': 'latex'
        }
        
        return language_map.get(ext, 'generic')
    
    async def get_sync_status(self, repository_name: str) -> dict:
        """Get current sync status."""
        if repository_name in self.repositories:
            repo = self.repositories[repository_name]
            return {
                'repository': repository_name,
                'status': 'synced',
                'last_sync': repo.get('last_sync'),
                'total_files': repo.get('total_files', 0),
                'total_chunks': repo.get('total_chunks', 0)
            }
        return {
            'repository': repository_name,
            'status': 'not_synced'
        }
    
    async def get_repository_stats(self, repository_name: str) -> dict:
        """Get detailed statistics for a repository."""
        repo_info = self.repositories.get(repository_name, {})
        
        return {
            'repository': repository_name,
            'path': repo_info.get('path', 'Unknown'),
            'last_sync': repo_info.get('last_sync'),
            'last_sync_type': repo_info.get('sync_type'),
            'total_files': repo_info.get('total_files', 0),
            'total_chunks': repo_info.get('total_chunks', 0),
            'cached_files': len(self.file_cache.get(repository_name, {}))
        }
    
    async def cleanup(self):
        """Cleanup resources."""
        self.executor.shutdown(wait=True)