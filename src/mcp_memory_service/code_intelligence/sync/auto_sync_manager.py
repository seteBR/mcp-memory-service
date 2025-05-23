"""
Manages automatic synchronization of discovered repositories.
"""
import asyncio
import json
import os
from typing import Dict, List, Optional, Set
from datetime import datetime, timedelta
import logging
from pathlib import Path

from .auto_discovery import RepositoryDiscovery, RepositoryInfo
from .repository_sync import RepositorySync
from ..monitoring.metrics_collector import MetricsCollector

logger = logging.getLogger(__name__)

class AutoSyncConfig:
    """Configuration for auto-sync behavior."""
    
    def __init__(self):
        self.enabled = True
        self.scan_interval = 3600  # seconds (1 hour)
        self.sync_interval = 300   # seconds (5 minutes)
        self.max_concurrent_syncs = 3
        self.priority_languages = ['python', 'javascript', 'typescript']
        self.size_threshold = 100 * 1024 * 1024  # 100MB
        self.auto_watch = True
        self.sync_on_startup = True
        
    @classmethod
    def from_env(cls) -> 'AutoSyncConfig':
        """Load configuration from environment variables."""
        config = cls()
        
        config.enabled = os.getenv('AUTO_SYNC_ENABLED', 'true').lower() == 'true'
        config.scan_interval = int(os.getenv('AUTO_SYNC_SCAN_INTERVAL', '3600'))
        config.sync_interval = int(os.getenv('AUTO_SYNC_INTERVAL', '300'))
        config.max_concurrent_syncs = int(os.getenv('AUTO_SYNC_MAX_CONCURRENT', '3'))
        
        priority_langs = os.getenv('AUTO_SYNC_PRIORITY_LANGUAGES', '')
        if priority_langs:
            config.priority_languages = priority_langs.split(',')
        
        config.size_threshold = int(os.getenv('AUTO_SYNC_SIZE_THRESHOLD', str(100 * 1024 * 1024)))
        config.auto_watch = os.getenv('AUTO_SYNC_AUTO_WATCH', 'true').lower() == 'true'
        config.sync_on_startup = os.getenv('AUTO_SYNC_ON_STARTUP', 'true').lower() == 'true'
        
        return config

class AutoSyncManager:
    """Manages automatic repository synchronization."""
    
    def __init__(self, 
                 repository_sync: RepositorySync,
                 storage_backend,
                 metrics_collector: Optional[MetricsCollector] = None):
        """
        Initialize auto-sync manager.
        
        Args:
            repository_sync: Repository sync instance
            storage_backend: Storage backend for checking existing repos
            metrics_collector: Optional metrics collector
        """
        self.repository_sync = repository_sync
        self.storage = storage_backend
        self.metrics = metrics_collector
        self.config = AutoSyncConfig.from_env()
        
        # State management
        self._discovery: Optional[RepositoryDiscovery] = None
        self._sync_queue: asyncio.Queue = asyncio.Queue()
        self._active_syncs: Dict[str, asyncio.Task] = {}
        self._synced_repos: Set[str] = set()
        self._last_scan: Optional[datetime] = None
        self._running = False
        
        # Load state from persistence
        self._load_state()
    
    async def start(self) -> None:
        """Start auto-sync manager."""
        if not self.config.enabled:
            logger.info("Auto-sync is disabled")
            return
        
        logger.info("Starting auto-sync manager")
        self._running = True
        
        # Initialize discovery engine
        scan_paths = os.getenv('AUTO_SYNC_PATHS', '').split(',')
        scan_paths = [p.strip() for p in scan_paths if p.strip()]
        
        # If no explicit paths configured, try to get from Claude Code permissions
        if not scan_paths:
            scan_paths = await self._get_claude_code_permitted_paths()
            
        if not scan_paths:
            logger.warning("No AUTO_SYNC_PATHS configured and no Claude Code permissions found")
            return
        
        exclude_patterns = os.getenv('AUTO_SYNC_EXCLUDE', '').split(',')
        exclude_patterns = [p.strip() for p in exclude_patterns if p.strip()]
        
        self._discovery = RepositoryDiscovery(
            scan_paths=scan_paths,
            exclude_patterns=exclude_patterns or None
        )
        
        # Start background tasks
        asyncio.create_task(self._scan_loop())
        asyncio.create_task(self._sync_loop())
        
        # Initial sync if configured
        if self.config.sync_on_startup:
            await self._trigger_scan()
    
    async def stop(self) -> None:
        """Stop auto-sync manager."""
        logger.info("Stopping auto-sync manager")
        self._running = False
        
        # Cancel active syncs
        for task in self._active_syncs.values():
            task.cancel()
        
        # Wait for tasks to complete
        if self._active_syncs:
            await asyncio.gather(*self._active_syncs.values(), return_exceptions=True)
        
        # Save state
        self._save_state()
    
    async def _scan_loop(self) -> None:
        """Background loop for periodic repository scanning."""
        while self._running:
            try:
                # Wait for scan interval
                await asyncio.sleep(self.config.scan_interval)
                
                if self._running:
                    await self._trigger_scan()
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in scan loop: {e}")
                await asyncio.sleep(60)  # Back off on error
    
    async def _sync_loop(self) -> None:
        """Background loop for processing sync queue."""
        while self._running:
            try:
                # Get repository from queue (with timeout)
                repo_info = await asyncio.wait_for(
                    self._sync_queue.get(),
                    timeout=self.config.sync_interval
                )
                
                # Check if we can start a new sync
                if len(self._active_syncs) < self.config.max_concurrent_syncs:
                    task = asyncio.create_task(self._sync_repository(repo_info))
                    self._active_syncs[repo_info.path] = task
                else:
                    # Put back in queue
                    await self._sync_queue.put(repo_info)
                    await asyncio.sleep(10)
                    
            except asyncio.TimeoutError:
                # Check for completed syncs
                completed = []
                for path, task in self._active_syncs.items():
                    if task.done():
                        completed.append(path)
                
                for path in completed:
                    del self._active_syncs[path]
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in sync loop: {e}")
    
    async def _trigger_scan(self) -> None:
        """Trigger a repository scan."""
        if not self._discovery:
            return
        
        logger.info("Starting repository scan")
        self._last_scan = datetime.now()
        
        try:
            # Discover repositories
            repositories = await self._discovery.discover_repositories()
            
            # Filter out already synced repositories
            new_repos = []
            for repo in repositories:
                if not await self._is_repository_synced(repo):
                    new_repos.append(repo)
            
            logger.info(f"Found {len(new_repos)} new repositories to sync")
            
            # Prioritize repositories
            prioritized = self._prioritize_repositories(new_repos)
            
            # Add to sync queue
            for repo in prioritized:
                await self._sync_queue.put(repo)
            
            # Record metrics
            if self.metrics:
                self.metrics.track_usage_metric(
                    command='auto_scan',
                    duration=0,
                    metadata={
                        'total_found': len(repositories),
                        'new_found': len(new_repos)
                    }
                )
                
        except Exception as e:
            logger.error(f"Error during repository scan: {e}")
            if self.metrics:
                self.metrics.track_error(
                    operation='auto_scan',
                    error=e
                )
    
    async def _sync_repository(self, repo_info: RepositoryInfo) -> None:
        """Sync a single repository."""
        logger.info(f"Auto-syncing repository: {repo_info.name}")
        
        try:
            # Perform sync
            start_time = datetime.now()
            
            result = await self.repository_sync.sync_repository(
                repository_path=repo_info.path,
                repository_name=repo_info.name,
                incremental=False  # First sync is always full
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            # Mark as synced
            self._synced_repos.add(repo_info.path)
            
            # Enable file watching if configured
            if self.config.auto_watch and result.success_rate > 90:
                await self._enable_file_watching(repo_info)
            
            # Record metrics
            if self.metrics:
                self.metrics.track_usage_metric(
                    command='auto_sync',
                    duration=duration,
                    repository=repo_info.name,
                    success=True,
                    metadata={
                        'language': repo_info.language,
                        'size': repo_info.size,
                        'files_processed': result.files_processed,
                        'chunks_created': result.chunks_new
                    }
                )
            
            logger.info(f"Successfully synced {repo_info.name}: "
                       f"{result.files_processed} files, {result.chunks_new} chunks")
            
        except Exception as e:
            logger.error(f"Error syncing repository {repo_info.name}: {e}")
            
            if self.metrics:
                self.metrics.track_error(
                    operation='auto_sync',
                    error=e,
                    metadata={
                        'repository': repo_info.name,
                        'path': repo_info.path
                    }
                )
            
            # Retry later
            await asyncio.sleep(300)  # Wait 5 minutes
            await self._sync_queue.put(repo_info)
    
    async def _is_repository_synced(self, repo_info: RepositoryInfo) -> bool:
        """Check if a repository is already synced."""
        # Check in-memory cache first
        if repo_info.path in self._synced_repos:
            return True
        
        # Check storage backend
        try:
            # Query for repository metadata
            filter_dict = {"repository": repo_info.name}
            results = await self.storage.storage.query(
                collection_name="code_metadata",
                filter=filter_dict,
                limit=1
            )
            
            return len(results) > 0
            
        except Exception:
            # Collection might not exist yet
            return False
    
    def _prioritize_repositories(self, repositories: List[RepositoryInfo]) -> List[RepositoryInfo]:
        """
        Prioritize repositories for syncing.
        
        Priority based on:
        1. Language (priority languages first)
        2. Size (smaller repos first up to threshold)
        3. Recently modified
        """
        def priority_key(repo: RepositoryInfo) -> tuple:
            # Language priority (lower is better)
            lang_priority = 999
            if repo.language in self.config.priority_languages:
                lang_priority = self.config.priority_languages.index(repo.language)
            
            # Size priority (smaller is better, but exclude huge repos)
            if repo.size > self.config.size_threshold:
                size_priority = 999999999
            else:
                size_priority = repo.size
            
            # Recency priority (newer is better)
            recency = (datetime.now() - repo.last_modified).days
            
            return (lang_priority, size_priority, recency)
        
        return sorted(repositories, key=priority_key)
    
    async def _enable_file_watching(self, repo_info: RepositoryInfo) -> None:
        """Enable file watching for a repository."""
        try:
            # This would integrate with existing file watcher
            logger.info(f"Enabling file watching for {repo_info.name}")
            # Implementation depends on existing file watcher integration
            
        except Exception as e:
            logger.error(f"Failed to enable file watching for {repo_info.name}: {e}")
    
    def _load_state(self) -> None:
        """Load persisted state."""
        state_file = Path.home() / '.mcp' / 'auto_sync_state.json'
        
        try:
            if state_file.exists():
                with open(state_file, 'r') as f:
                    state = json.load(f)
                    self._synced_repos = set(state.get('synced_repos', []))
                    
                    last_scan = state.get('last_scan')
                    if last_scan:
                        self._last_scan = datetime.fromisoformat(last_scan)
                        
        except Exception as e:
            logger.error(f"Failed to load auto-sync state: {e}")
    
    def _save_state(self) -> None:
        """Save state to persistence."""
        state_file = Path.home() / '.mcp' / 'auto_sync_state.json'
        state_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            state = {
                'synced_repos': list(self._synced_repos),
                'last_scan': self._last_scan.isoformat() if self._last_scan else None,
                'saved_at': datetime.now().isoformat()
            }
            
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save auto-sync state: {e}")
    
    async def _get_claude_code_permitted_paths(self) -> List[str]:
        """
        Get permitted paths from Claude Code's permission system.
        
        Returns:
            List of permitted directory paths
        """
        permitted_paths = []
        
        try:
            # Method 1: Check MCP server context for allowed paths
            # This would be passed from Claude Code during MCP server initialization
            if hasattr(self, '_mcp_context') and self._mcp_context:
                allowed_paths = self._mcp_context.get('allowed_paths', [])
                if allowed_paths:
                    logger.info(f"Found {len(allowed_paths)} paths from MCP context")
                    return allowed_paths
            
            # Method 2: Check environment variable set by Claude Code
            # Claude Code might set this when launching the MCP server
            claude_paths = os.getenv('CLAUDE_CODE_ALLOWED_PATHS', '')
            if claude_paths:
                paths = [p.strip() for p in claude_paths.split(',') if p.strip()]
                if paths:
                    logger.info(f"Found {len(paths)} paths from CLAUDE_CODE_ALLOWED_PATHS")
                    return paths
            
            # Method 3: Check working directory as fallback
            # If Claude Code is running in a specific project, use that
            cwd = os.getcwd()
            if cwd and os.path.exists(cwd):
                # Check if it's a code repository
                if any(os.path.exists(os.path.join(cwd, indicator)) 
                       for indicator in ['.git', 'package.json', 'requirements.txt']):
                    logger.info(f"Using current working directory: {cwd}")
                    return [cwd]
            
            # Method 4: Check for Claude Code configuration file
            # Look for .claude/config.json or similar
            claude_config_paths = [
                Path.home() / '.claude' / 'config.json',
                Path.cwd() / '.claude' / 'config.json',
                Path('/') / 'etc' / 'claude' / 'config.json'
            ]
            
            for config_path in claude_config_paths:
                if config_path.exists():
                    try:
                        with open(config_path, 'r') as f:
                            config = json.load(f)
                            if 'allowed_paths' in config:
                                paths = config['allowed_paths']
                                if isinstance(paths, list) and paths:
                                    logger.info(f"Found {len(paths)} paths from {config_path}")
                                    return paths
                    except Exception as e:
                        logger.debug(f"Failed to read {config_path}: {e}")
            
            # Method 5: Look for project markers in parent directories
            # Walk up from CWD to find project roots
            current = Path.cwd()
            project_roots = []
            
            while current != current.parent:
                # Check if this directory has project markers
                if any((current / marker).exists() 
                       for marker in ['.git', 'package.json', 'pyproject.toml']):
                    project_roots.append(str(current))
                    # Also check sibling directories
                    parent = current.parent
                    for sibling in parent.iterdir():
                        if sibling.is_dir() and sibling != current:
                            if any((sibling / marker).exists() 
                                   for marker in ['.git', 'package.json', 'pyproject.toml']):
                                project_roots.append(str(sibling))
                    break
                current = current.parent
            
            if project_roots:
                logger.info(f"Found {len(project_roots)} project roots from filesystem scan")
                return project_roots
                
        except Exception as e:
            logger.error(f"Error getting Claude Code permitted paths: {e}")
        
        return permitted_paths
    
    # Public methods for manual control
    
    async def trigger_scan(self) -> Dict[str, int]:
        """Manually trigger a repository scan."""
        await self._trigger_scan()
        
        return {
            'queued': self._sync_queue.qsize(),
            'active': len(self._active_syncs),
            'synced': len(self._synced_repos)
        }
    
    async def get_status(self) -> Dict[str, any]:
        """Get current auto-sync status."""
        return {
            'enabled': self.config.enabled,
            'running': self._running,
            'last_scan': self._last_scan.isoformat() if self._last_scan else None,
            'queued_repos': self._sync_queue.qsize(),
            'active_syncs': len(self._active_syncs),
            'synced_repos': len(self._synced_repos),
            'config': {
                'scan_interval': self.config.scan_interval,
                'sync_interval': self.config.sync_interval,
                'max_concurrent': self.config.max_concurrent_syncs
            }
        }
    
    async def pause(self) -> None:
        """Pause auto-sync operations."""
        self.config.enabled = False
        logger.info("Auto-sync paused")
    
    async def resume(self) -> None:
        """Resume auto-sync operations."""
        self.config.enabled = True
        logger.info("Auto-sync resumed")