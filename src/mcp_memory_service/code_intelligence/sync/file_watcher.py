# src/mcp_memory_service/code_intelligence/sync/file_watcher.py
"""
File watching for real-time code intelligence updates.
Enhanced for ConnectivityTestingTool MCP Code Intelligence project.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional, Callable, Dict, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent

logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Types of file system changes."""
    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"


@dataclass
class FileChangeEvent:
    """Represents a file change event."""
    path: str
    change_type: ChangeType
    timestamp: float
    old_path: Optional[str] = None  # For move events
    
    @property
    def is_code_file(self) -> bool:
        """Check if this is a code file based on extension."""
        code_extensions = {'.py', '.js', '.jsx', '.ts', '.tsx', '.go', '.rs', '.java', '.cpp', '.c', '.h', '.hpp'}
        return Path(self.path).suffix.lower() in code_extensions


class DebouncedFileHandler(FileSystemEventHandler):
    """File system event handler with debouncing to prevent duplicate events."""
    
    def __init__(self, callback: Callable[[FileChangeEvent], None], debounce_delay: float = 0.5):
        super().__init__()
        self.callback = callback
        self.debounce_delay = debounce_delay
        self.pending_events: Dict[str, FileChangeEvent] = {}
        self.timer_tasks: Dict[str, asyncio.Task] = {}
        
    def on_created(self, event: FileSystemEvent):
        """Handle file creation events."""
        if not event.is_directory:
            self._schedule_event(FileChangeEvent(
                path=event.src_path,
                change_type=ChangeType.CREATED,
                timestamp=time.time()
            ))
    
    def on_modified(self, event: FileSystemEvent):
        """Handle file modification events."""
        if not event.is_directory:
            self._schedule_event(FileChangeEvent(
                path=event.src_path,
                change_type=ChangeType.MODIFIED,
                timestamp=time.time()
            ))
    
    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion events."""
        if not event.is_directory:
            self._schedule_event(FileChangeEvent(
                path=event.src_path,
                change_type=ChangeType.DELETED,
                timestamp=time.time()
            ))
    
    def on_moved(self, event: FileSystemEvent):
        """Handle file move/rename events."""
        if not event.is_directory:
            self._schedule_event(FileChangeEvent(
                path=event.dest_path,
                change_type=ChangeType.MOVED,
                timestamp=time.time(),
                old_path=event.src_path
            ))
    
    def _schedule_event(self, event: FileChangeEvent):
        """Schedule event with debouncing."""
        # Cancel existing timer for this path
        if event.path in self.timer_tasks:
            self.timer_tasks[event.path].cancel()
        
        # Store the latest event for this path
        self.pending_events[event.path] = event
        
        # Schedule new timer
        loop = asyncio.get_event_loop()
        task = loop.call_later(
            self.debounce_delay,
            self._fire_event,
            event.path
        )
        self.timer_tasks[event.path] = task
    
    def _fire_event(self, path: str):
        """Fire the debounced event."""
        if path in self.pending_events:
            event = self.pending_events.pop(path)
            self.timer_tasks.pop(path, None)
            
            # Only process code files
            if event.is_code_file:
                logger.debug(f"File change detected: {event.change_type.value} {event.path}")
                self.callback(event)


class FileWatcher:
    """Watches file system changes in code repositories."""
    
    def __init__(self, debounce_delay: float = 0.5):
        self.observer = Observer()
        self.debounce_delay = debounce_delay
        self.watched_paths: Dict[str, str] = {}  # path -> repository_name
        self.change_callbacks: List[Callable[[FileChangeEvent, str], None]] = []
        self.is_running = False
        
        # Set up the event handler
        self.handler = DebouncedFileHandler(
            callback=self._handle_change_event,
            debounce_delay=debounce_delay
        )
    
    def add_repository(self, repository_path: str, repository_name: str, recursive: bool = True):
        """Add a repository to watch for changes."""
        path = Path(repository_path).resolve()
        
        if not path.exists():
            raise ValueError(f"Repository path does not exist: {repository_path}")
        
        if not path.is_dir():
            raise ValueError(f"Repository path is not a directory: {repository_path}")
        
        path_str = str(path)
        
        # Check if already watching this path
        if path_str in self.watched_paths:
            logger.info(f"Already watching repository: {repository_name} at {path_str}")
            return
        
        # Add to observer
        watch = self.observer.schedule(
            event_handler=self.handler,
            path=path_str,
            recursive=recursive
        )
        
        self.watched_paths[path_str] = repository_name
        logger.info(f"Added repository to watch: {repository_name} at {path_str}")
    
    def remove_repository(self, repository_path: str):
        """Remove a repository from watching."""
        path_str = str(Path(repository_path).resolve())
        
        if path_str not in self.watched_paths:
            logger.warning(f"Repository not being watched: {repository_path}")
            return
        
        # Find and remove the watch
        for watch in self.observer.emitters:
            if watch.watch.path == path_str:
                self.observer.unschedule(watch.watch)
                break
        
        repository_name = self.watched_paths.pop(path_str)
        logger.info(f"Removed repository from watch: {repository_name}")
    
    def add_change_callback(self, callback: Callable[[FileChangeEvent, str], None]):
        """Add a callback to be called when files change."""
        self.change_callbacks.append(callback)
    
    def remove_change_callback(self, callback: Callable[[FileChangeEvent, str], None]):
        """Remove a change callback."""
        if callback in self.change_callbacks:
            self.change_callbacks.remove(callback)
    
    def start(self):
        """Start watching for file changes."""
        if self.is_running:
            logger.warning("File watcher is already running")
            return
        
        self.observer.start()
        self.is_running = True
        logger.info("File watcher started")
    
    def stop(self):
        """Stop watching for file changes."""
        if not self.is_running:
            return
        
        self.observer.stop()
        self.observer.join()
        self.is_running = False
        logger.info("File watcher stopped")
    
    def _handle_change_event(self, event: FileChangeEvent):
        """Handle a file change event."""
        # Find which repository this file belongs to
        repository_name = self._find_repository_for_path(event.path)
        
        if repository_name:
            # Notify all callbacks
            for callback in self.change_callbacks:
                try:
                    callback(event, repository_name)
                except Exception as e:
                    logger.error(f"Error in change callback: {e}")
    
    def _find_repository_for_path(self, file_path: str) -> Optional[str]:
        """Find which repository a file path belongs to."""
        file_path = str(Path(file_path).resolve())
        
        # Find the most specific (longest) matching repository path
        best_match = None
        best_match_len = 0
        
        for repo_path, repo_name in self.watched_paths.items():
            if file_path.startswith(repo_path):
                if len(repo_path) > best_match_len:
                    best_match = repo_name
                    best_match_len = len(repo_path)
        
        return best_match
    
    def get_watched_repositories(self) -> Dict[str, str]:
        """Get a dictionary of watched repository paths and names."""
        return self.watched_paths.copy()
    
    def is_watching(self, repository_path: str) -> bool:
        """Check if a repository is being watched."""
        path_str = str(Path(repository_path).resolve())
        return path_str in self.watched_paths
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()