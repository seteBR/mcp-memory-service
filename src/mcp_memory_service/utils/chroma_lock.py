"""ChromaDB concurrent access management with file locking and request queuing."""

import os
import time
import asyncio
import json
import logging
import platform

# Platform-specific imports
if platform.system() != 'Windows':
    import fcntl
else:
    # Windows doesn't have fcntl, we'll use a different approach
    import msvcrt
from pathlib import Path
from typing import Optional, Any, Callable, TypeVar, Union
from functools import wraps
from dataclasses import dataclass
from datetime import datetime, timedelta
import threading
from queue import Queue, Empty
import sqlite3

logger = logging.getLogger(__name__)

T = TypeVar('T')


@dataclass
class LockStats:
    """Statistics for lock acquisition and wait times."""
    total_acquisitions: int = 0
    total_wait_time: float = 0.0
    max_wait_time: float = 0.0
    failed_acquisitions: int = 0
    active_locks: int = 0
    last_acquisition: Optional[datetime] = None


class ChromaDBLock:
    """File-based lock for ChromaDB operations with statistics and monitoring."""
    
    def __init__(self, chroma_path: str, timeout: float = 30.0):
        self.chroma_path = Path(chroma_path)
        self.lock_file = self.chroma_path / ".chroma.lock"
        self.stats_file = self.chroma_path / ".chroma_stats.json"
        self.timeout = timeout
        self.lock_fd: Optional[int] = None
        self.stats = LockStats()
        self._load_stats()
        
    def _load_stats(self):
        """Load statistics from file."""
        try:
            if self.stats_file.exists():
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                    self.stats.total_acquisitions = data.get('total_acquisitions', 0)
                    self.stats.total_wait_time = data.get('total_wait_time', 0.0)
                    self.stats.max_wait_time = data.get('max_wait_time', 0.0)
                    self.stats.failed_acquisitions = data.get('failed_acquisitions', 0)
                    if data.get('last_acquisition'):
                        self.stats.last_acquisition = datetime.fromisoformat(data['last_acquisition'])
        except Exception as e:
            logger.warning(f"Failed to load lock stats: {e}")
    
    def _save_stats(self):
        """Save statistics to file."""
        try:
            data = {
                'total_acquisitions': self.stats.total_acquisitions,
                'total_wait_time': self.stats.total_wait_time,
                'max_wait_time': self.stats.max_wait_time,
                'failed_acquisitions': self.stats.failed_acquisitions,
                'active_locks': self.stats.active_locks,
                'last_acquisition': self.stats.last_acquisition.isoformat() if self.stats.last_acquisition else None
            }
            with open(self.stats_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save lock stats: {e}")
    
    def acquire(self) -> bool:
        """Acquire the lock with timeout."""
        start_time = time.time()
        
        # Ensure lock file exists
        self.lock_file.touch(exist_ok=True)
        
        # Open file descriptor
        if platform.system() == 'Windows':
            # Windows: Open file for locking
            try:
                self.lock_fd = os.open(str(self.lock_file), os.O_RDWR | os.O_CREAT)
            except FileExistsError:
                self.lock_fd = os.open(str(self.lock_file), os.O_RDWR)
        else:
            self.lock_fd = os.open(str(self.lock_file), os.O_RDWR)
        
        deadline = start_time + self.timeout
        while time.time() < deadline:
            try:
                if platform.system() == 'Windows':
                    # Windows: Try to lock using msvcrt
                    try:
                        msvcrt.locking(self.lock_fd, msvcrt.LK_NBLCK, 1)
                        lock_acquired = True
                    except IOError:
                        lock_acquired = False
                else:
                    # Unix: Use fcntl
                    try:
                        fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        lock_acquired = True
                    except IOError:
                        lock_acquired = False
                
                if lock_acquired:
                    # Lock acquired
                    wait_time = time.time() - start_time
                    self.stats.total_acquisitions += 1
                    self.stats.total_wait_time += wait_time
                    self.stats.max_wait_time = max(self.stats.max_wait_time, wait_time)
                    self.stats.active_locks += 1
                    self.stats.last_acquisition = datetime.now()
                    self._save_stats()
                    
                    logger.debug(f"ChromaDB lock acquired after {wait_time:.2f}s")
                    return True
                else:
                    # Lock is held by another process, wait a bit
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.debug(f"Lock acquisition attempt failed: {e}")
                time.sleep(0.1)
        
        # Timeout reached
        self.stats.failed_acquisitions += 1
        self._save_stats()
        
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
            
        logger.warning(f"Failed to acquire ChromaDB lock after {self.timeout}s")
        return False
    
    def release(self):
        """Release the lock."""
        if self.lock_fd is not None:
            try:
                if platform.system() == 'Windows':
                    # Windows: Unlock using msvcrt
                    try:
                        msvcrt.locking(self.lock_fd, msvcrt.LK_UNLCK, 1)
                    except:
                        pass  # If unlock fails, closing the file will release it
                else:
                    # Unix: Use fcntl
                    fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                
                os.close(self.lock_fd)
                self.lock_fd = None
                
                self.stats.active_locks = max(0, self.stats.active_locks - 1)
                self._save_stats()
                
                logger.debug("ChromaDB lock released")
            except Exception as e:
                logger.error(f"Error releasing lock: {e}")
    
    def __enter__(self):
        """Context manager entry."""
        if not self.acquire():
            raise TimeoutError(f"Could not acquire ChromaDB lock within {self.timeout}s")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()
    
    def get_stats(self) -> dict:
        """Get current lock statistics."""
        return {
            'total_acquisitions': self.stats.total_acquisitions,
            'total_wait_time': self.stats.total_wait_time,
            'average_wait_time': self.stats.total_wait_time / max(1, self.stats.total_acquisitions),
            'max_wait_time': self.stats.max_wait_time,
            'failed_acquisitions': self.stats.failed_acquisitions,
            'active_locks': self.stats.active_locks,
            'last_acquisition': self.stats.last_acquisition.isoformat() if self.stats.last_acquisition else None
        }


class RequestQueue:
    """Thread-safe request queue for serializing ChromaDB operations."""
    
    def __init__(self, max_size: int = 1000):
        self.queue = Queue(maxsize=max_size)
        self.processing = False
        self.worker_thread: Optional[threading.Thread] = None
        
    def submit(self, operation: Callable, *args, **kwargs) -> asyncio.Future:
        """Submit an operation to the queue."""
        future = asyncio.Future()
        
        try:
            self.queue.put((operation, args, kwargs, future), block=False)
        except:
            future.set_exception(Exception("Request queue is full"))
            
        return future
    
    def start_processing(self):
        """Start processing queued requests."""
        if not self.processing:
            self.processing = True
            self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
            self.worker_thread.start()
    
    def stop_processing(self):
        """Stop processing requests."""
        self.processing = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5.0)
    
    def _process_queue(self):
        """Worker thread to process queued requests."""
        while self.processing:
            try:
                operation, args, kwargs, future = self.queue.get(timeout=1.0)
                
                try:
                    result = operation(*args, **kwargs)
                    if not future.done():
                        future.set_result(result)
                except Exception as e:
                    if not future.done():
                        future.set_exception(e)
                        
            except Empty:
                continue
            except Exception as e:
                logger.error(f"Error in request queue worker: {e}")


def with_chroma_lock(timeout: float = 30.0):
    """Decorator for ChromaDB operations that require exclusive access."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(self, *args, **kwargs) -> T:
            # Get or create lock from instance
            if not hasattr(self, '_chroma_lock'):
                self._chroma_lock = ChromaDBLock(self.path, timeout)
            
            with self._chroma_lock:
                return await func(self, *args, **kwargs)
        
        @wraps(func)
        def sync_wrapper(self, *args, **kwargs) -> T:
            # Get or create lock from instance
            if not hasattr(self, '_chroma_lock'):
                self._chroma_lock = ChromaDBLock(self.path, timeout)
            
            with self._chroma_lock:
                return func(self, *args, **kwargs)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator


def with_retry(max_attempts: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """Decorator for retrying operations on failure."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except (sqlite3.OperationalError, IOError) as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {current_delay}s...")
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"All {max_attempts} attempts failed")
                        
            raise last_exception
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except (sqlite3.OperationalError, IOError) as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {current_delay}s...")
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(f"All {max_attempts} attempts failed")
                        
            raise last_exception
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
            
    return decorator


class ConcurrentChromaDBWrapper:
    """Wrapper for ChromaDB operations with concurrent access management."""
    
    def __init__(self, chroma_storage):
        self.storage = chroma_storage
        self.lock = ChromaDBLock(chroma_storage.path)
        self.request_queue = RequestQueue()
        self.request_queue.start_processing()
        
    async def store(self, *args, **kwargs):
        """Store operation with lock."""
        with self.lock:
            return await self.storage.store(*args, **kwargs)
    
    async def retrieve(self, *args, **kwargs):
        """Retrieve operation with lock for write consistency."""
        # Reads can be concurrent, but we still lock to ensure consistency
        with self.lock:
            return await self.storage.retrieve(*args, **kwargs)
    
    async def delete(self, *args, **kwargs):
        """Delete operation with lock."""
        with self.lock:
            return await self.storage.delete(*args, **kwargs)
    
    def get_lock_stats(self) -> dict:
        """Get lock statistics."""
        return self.lock.get_stats()
    
    def __getattr__(self, name):
        """Proxy other methods to the wrapped storage."""
        attr = getattr(self.storage, name)
        
        if asyncio.iscoroutinefunction(attr):
            async def locked_method(*args, **kwargs):
                with self.lock:
                    return await attr(*args, **kwargs)
            return locked_method
        elif callable(attr):
            def locked_method(*args, **kwargs):
                with self.lock:
                    return attr(*args, **kwargs)
            return locked_method
        else:
            return attr