# Auto-Sync Implementation for Code Intelligence System

## Overview

This document outlines the implementation plan for adding automatic repository synchronization to the MCP Code Intelligence System. The auto-sync feature will automatically discover, index, and maintain code repositories without manual intervention.

## Goals

1. **Zero-Configuration Setup**: Automatically discover and sync repositories in configured paths
2. **Smart Detection**: Identify code repositories using multiple indicators
3. **Incremental Updates**: Efficiently handle both initial sync and updates
4. **Background Processing**: Non-blocking sync operations
5. **Configurable Behavior**: Fine-grained control over what gets synced

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Auto-Sync System                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  ┌─────────────────┐    ┌──────────────────┐          │
│  │   Discovery     │───▶│   Repository     │          │
│  │    Engine       │    │   Detector       │          │
│  └─────────────────┘    └──────────────────┘          │
│           │                      │                      │
│           ▼                      ▼                      │
│  ┌─────────────────┐    ┌──────────────────┐          │
│  │  Sync Manager   │───▶│  Sync Scheduler  │          │
│  └─────────────────┘    └──────────────────┘          │
│           │                      │                      │
│           ▼                      ▼                      │
│  ┌─────────────────┐    ┌──────────────────┐          │
│  │ Repository Sync │───▶│  File Watcher    │          │
│  │   (existing)    │    │   (existing)     │          │
│  └─────────────────┘    └──────────────────┘          │
└─────────────────────────────────────────────────────────┘
```

## Implementation Plan

### Phase 1: Repository Discovery Module

#### File: `src/mcp_memory_service/code_intelligence/sync/auto_discovery.py`

```python
"""
Automatic repository discovery and detection system.
"""
import os
import json
import asyncio
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import git  # GitPython for repository detection
import logging

logger = logging.getLogger(__name__)

@dataclass
class RepositoryInfo:
    """Information about a discovered repository."""
    path: str
    name: str
    type: str  # git, svn, mercurial
    language: str  # primary language detected
    size: int  # in bytes
    last_modified: datetime
    indicators: List[str]  # what made us identify this as a repo
    
    def to_dict(self) -> dict:
        return {
            'path': self.path,
            'name': self.name,
            'type': self.type,
            'language': self.language,
            'size': self.size,
            'last_modified': self.last_modified.isoformat(),
            'indicators': self.indicators
        }

class RepositoryDiscovery:
    """Discovers code repositories in specified paths."""
    
    # Repository indicators by priority
    REPO_INDICATORS = {
        'git': ['.git'],
        'build': ['package.json', 'pom.xml', 'build.gradle', 'Cargo.toml', 
                  'go.mod', 'requirements.txt', 'Gemfile', 'composer.json'],
        'project': ['.project', '.vscode', '.idea', '*.sln', 'Makefile'],
        'docs': ['README.md', 'README.rst', 'README.txt']
    }
    
    # Language detection based on files
    LANGUAGE_INDICATORS = {
        'python': ['*.py', 'requirements.txt', 'setup.py', 'pyproject.toml'],
        'javascript': ['*.js', '*.jsx', 'package.json'],
        'typescript': ['*.ts', '*.tsx', 'tsconfig.json'],
        'java': ['*.java', 'pom.xml', 'build.gradle'],
        'go': ['*.go', 'go.mod'],
        'rust': ['*.rs', 'Cargo.toml'],
        'ruby': ['*.rb', 'Gemfile'],
        'php': ['*.php', 'composer.json'],
        'csharp': ['*.cs', '*.csproj'],
        'cpp': ['*.cpp', '*.h', '*.cc', 'CMakeLists.txt']
    }
    
    def __init__(self, 
                 scan_paths: List[str],
                 exclude_patterns: List[str] = None,
                 max_depth: int = 5,
                 min_files: int = 3):
        """
        Initialize repository discovery.
        
        Args:
            scan_paths: List of paths to scan for repositories
            exclude_patterns: Patterns to exclude (e.g., node_modules)
            max_depth: Maximum directory depth to scan
            min_files: Minimum number of code files to consider a repository
        """
        self.scan_paths = [Path(p).resolve() for p in scan_paths]
        self.exclude_patterns = exclude_patterns or [
            'node_modules', '.git', '__pycache__', 'venv', 'env',
            'build', 'dist', 'target', '.pytest_cache', '.tox'
        ]
        self.max_depth = max_depth
        self.min_files = min_files
        self._discovered_repos: Dict[str, RepositoryInfo] = {}
    
    async def discover_repositories(self) -> List[RepositoryInfo]:
        """
        Discover all repositories in configured paths.
        
        Returns:
            List of discovered repositories
        """
        logger.info(f"Starting repository discovery in {len(self.scan_paths)} paths")
        
        tasks = []
        for scan_path in self.scan_paths:
            if scan_path.exists() and scan_path.is_dir():
                tasks.append(self._scan_directory(scan_path))
        
        if tasks:
            await asyncio.gather(*tasks)
        
        # Sort by size (larger repos first)
        repositories = sorted(
            self._discovered_repos.values(),
            key=lambda r: r.size,
            reverse=True
        )
        
        logger.info(f"Discovered {len(repositories)} repositories")
        return repositories
    
    async def _scan_directory(self, path: Path, depth: int = 0) -> None:
        """Recursively scan directory for repositories."""
        if depth > self.max_depth:
            return
        
        # Check if this path should be excluded
        if any(pattern in str(path) for pattern in self.exclude_patterns):
            return
        
        try:
            # Check if this is a repository
            repo_info = await self._detect_repository(path)
            if repo_info:
                self._discovered_repos[str(path)] = repo_info
                # Don't scan subdirectories of repositories
                return
            
            # Scan subdirectories
            subdirs = []
            for item in path.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    subdirs.append(item)
            
            # Process subdirectories in parallel
            if subdirs:
                tasks = [
                    self._scan_directory(subdir, depth + 1)
                    for subdir in subdirs[:50]  # Limit parallel tasks
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
                
        except PermissionError:
            logger.debug(f"Permission denied: {path}")
        except Exception as e:
            logger.error(f"Error scanning {path}: {e}")
    
    async def _detect_repository(self, path: Path) -> Optional[RepositoryInfo]:
        """
        Detect if a directory is a code repository.
        
        Returns:
            RepositoryInfo if detected, None otherwise
        """
        indicators = []
        
        # Check for version control
        if (path / '.git').exists():
            indicators.append('.git')
            repo_type = 'git'
        else:
            repo_type = 'unknown'
        
        # Check for build/project files
        for indicator_type, files in self.REPO_INDICATORS.items():
            for file_pattern in files:
                if any(path.glob(file_pattern)):
                    indicators.append(file_pattern)
        
        # Need at least one indicator
        if not indicators:
            return None
        
        # Detect primary language and count code files
        language_scores = {}
        code_files = []
        
        for lang, patterns in self.LANGUAGE_INDICATORS.items():
            count = 0
            for pattern in patterns:
                files = list(path.rglob(pattern))
                # Exclude files in excluded directories
                files = [
                    f for f in files
                    if not any(exc in str(f) for exc in self.exclude_patterns)
                ]
                count += len(files)
                code_files.extend(files[:100])  # Limit for performance
            
            if count > 0:
                language_scores[lang] = count
        
        # Need minimum number of code files
        if len(code_files) < self.min_files:
            return None
        
        # Determine primary language
        primary_language = max(language_scores, key=language_scores.get) if language_scores else 'unknown'
        
        # Calculate repository size
        total_size = sum(f.stat().st_size for f in code_files if f.exists())
        
        # Get last modified time
        last_modified = datetime.fromtimestamp(
            max(f.stat().st_mtime for f in code_files if f.exists())
        )
        
        # Generate repository name
        repo_name = self._generate_repo_name(path, repo_type)
        
        return RepositoryInfo(
            path=str(path),
            name=repo_name,
            type=repo_type,
            language=primary_language,
            size=total_size,
            last_modified=last_modified,
            indicators=indicators
        )
    
    def _generate_repo_name(self, path: Path, repo_type: str) -> str:
        """Generate a meaningful repository name."""
        if repo_type == 'git':
            try:
                import git
                repo = git.Repo(path)
                # Try to get repo name from remote
                if repo.remotes:
                    remote_url = repo.remotes[0].url
                    # Extract repo name from URL
                    if '/' in remote_url:
                        repo_name = remote_url.split('/')[-1]
                        if repo_name.endswith('.git'):
                            repo_name = repo_name[:-4]
                        return repo_name
            except:
                pass
        
        # Fallback to directory name
        return path.name
```

### Phase 2: Auto-Sync Manager

#### File: `src/mcp_memory_service/code_intelligence/sync/auto_sync_manager.py`

```python
"""
Manages automatic synchronization of discovered repositories.
"""
import asyncio
import json
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
        
        import os
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
        import os
        scan_paths = os.getenv('AUTO_SYNC_PATHS', '').split(',')
        scan_paths = [p.strip() for p in scan_paths if p.strip()]
        
        if not scan_paths:
            logger.warning("No AUTO_SYNC_PATHS configured")
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
```

### Phase 3: Enhanced Server Integration

#### Updates to `src/mcp_memory_service/enhanced_server.py`

```python
# Add to imports
from code_intelligence.sync.auto_sync_manager import AutoSyncManager

# Add to EnhancedMCPServer class
class EnhancedMCPServer(Server):
    def __init__(self, storage: ChromaStorage):
        super().__init__("mcp-memory-enhanced")
        self.storage = storage
        
        # Existing initialization...
        
        # Initialize auto-sync manager
        self.auto_sync_manager = AutoSyncManager(
            repository_sync=self.repository_sync,
            storage_backend=self.storage,
            metrics_collector=self.metrics_collector
        )
        
        # Start auto-sync on server start
        asyncio.create_task(self._start_auto_sync())
    
    async def _start_auto_sync(self):
        """Start auto-sync after server initialization."""
        await asyncio.sleep(5)  # Wait for server to fully initialize
        await self.auto_sync_manager.start()
    
    # Add new MCP tools
    async def handle_call_tool(self, request_id: int, name: str, arguments: dict):
        """Handle tool calls with auto-sync tools."""
        
        # Existing tool handling...
        
        # Auto-sync tools
        if name == "configure_auto_sync":
            return await self._handle_configure_auto_sync(arguments)
        elif name == "get_auto_sync_status":
            return await self._handle_get_auto_sync_status()
        elif name == "trigger_repository_scan":
            return await self._handle_trigger_scan()
        elif name == "pause_auto_sync":
            return await self._handle_pause_auto_sync()
        elif name == "resume_auto_sync":
            return await self._handle_resume_auto_sync()
    
    async def _handle_configure_auto_sync(self, args: dict) -> CallToolResult:
        """Configure auto-sync settings."""
        try:
            config = self.auto_sync_manager.config
            
            # Update configuration
            if 'scan_paths' in args:
                os.environ['AUTO_SYNC_PATHS'] = ','.join(args['scan_paths'])
            if 'exclude_patterns' in args:
                os.environ['AUTO_SYNC_EXCLUDE'] = ','.join(args['exclude_patterns'])
            if 'scan_interval' in args:
                config.scan_interval = args['scan_interval']
            if 'max_concurrent' in args:
                config.max_concurrent_syncs = args['max_concurrent']
            if 'priority_languages' in args:
                config.priority_languages = args['priority_languages']
            
            # Restart auto-sync with new config
            await self.auto_sync_manager.stop()
            self.auto_sync_manager = AutoSyncManager(
                repository_sync=self.repository_sync,
                storage_backend=self.storage,
                metrics_collector=self.metrics_collector
            )
            await self.auto_sync_manager.start()
            
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text="Auto-sync configuration updated successfully"
                )]
            )
            
        except Exception as e:
            logger.error(f"Failed to configure auto-sync: {e}")
            return CallToolResult(
                content=[TextContent(
                    type="text",
                    text=f"Error configuring auto-sync: {str(e)}"
                )]
            )
```

### Phase 4: CLI Integration

#### Updates to `cli.py`

```python
# Add new commands
@app.command()
def auto_sync_config(
    scan_paths: List[str] = typer.Option(None, "--path", "-p", help="Paths to scan for repositories"),
    exclude: List[str] = typer.Option(None, "--exclude", "-e", help="Patterns to exclude"),
    scan_interval: int = typer.Option(None, "--scan-interval", help="Scan interval in seconds"),
    enabled: bool = typer.Option(None, "--enabled/--disabled", help="Enable or disable auto-sync")
):
    """Configure automatic repository synchronization."""
    config_updates = {}
    
    if scan_paths:
        config_updates['AUTO_SYNC_PATHS'] = ','.join(scan_paths)
    if exclude:
        config_updates['AUTO_SYNC_EXCLUDE'] = ','.join(exclude)
    if scan_interval is not None:
        config_updates['AUTO_SYNC_SCAN_INTERVAL'] = str(scan_interval)
    if enabled is not None:
        config_updates['AUTO_SYNC_ENABLED'] = 'true' if enabled else 'false'
    
    # Write to .env file
    env_file = Path('.env')
    lines = []
    
    if env_file.exists():
        with open(env_file, 'r') as f:
            lines = f.readlines()
    
    # Update or add configuration
    for key, value in config_updates.items():
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                found = True
                break
        
        if not found:
            lines.append(f"{key}={value}\n")
    
    with open(env_file, 'w') as f:
        f.writelines(lines)
    
    typer.echo("✅ Auto-sync configuration updated")
    typer.echo("\nCurrent configuration:")
    for key, value in config_updates.items():
        typer.echo(f"  {key}: {value}")

@app.command()
def auto_sync_status():
    """Check automatic sync status."""
    asyncio.run(_auto_sync_status())

async def _auto_sync_status():
    """Get auto-sync status."""
    try:
        async with get_client() as (client, session):
            result = await client.call_tool(
                "get_auto_sync_status",
                {}
            )
            
            if hasattr(result, 'content') and result.content:
                status = json.loads(result.content[0].text)
                
                typer.echo("\n🔄 Auto-Sync Status")
                typer.echo("=" * 50)
                
                typer.echo(f"Enabled: {'✅' if status['enabled'] else '❌'}")
                typer.echo(f"Running: {'✅' if status['running'] else '❌'}")
                
                if status['last_scan']:
                    typer.echo(f"Last Scan: {status['last_scan']}")
                
                typer.echo(f"\nQueued Repositories: {status['queued_repos']}")
                typer.echo(f"Active Syncs: {status['active_syncs']}")
                typer.echo(f"Synced Repositories: {status['synced_repos']}")
                
                typer.echo("\nConfiguration:")
                config = status['config']
                typer.echo(f"  Scan Interval: {config['scan_interval']}s")
                typer.echo(f"  Sync Interval: {config['sync_interval']}s")
                typer.echo(f"  Max Concurrent: {config['max_concurrent']}")
                
    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}", err=True)
        raise typer.Exit(code=1)

@app.command()
def auto_sync_scan():
    """Manually trigger repository scan."""
    asyncio.run(_trigger_scan())

async def _trigger_scan():
    """Trigger repository scan."""
    try:
        async with get_client() as (client, session):
            typer.echo("🔍 Triggering repository scan...")
            
            result = await client.call_tool(
                "trigger_repository_scan",
                {}
            )
            
            if hasattr(result, 'content') and result.content:
                stats = json.loads(result.content[0].text)
                
                typer.echo("\n✅ Scan triggered successfully")
                typer.echo(f"Repositories queued: {stats['queued']}")
                typer.echo(f"Active syncs: {stats['active']}")
                typer.echo(f"Total synced: {stats['synced']}")
                
    except Exception as e:
        typer.echo(f"❌ Error: {str(e)}", err=True)
        raise typer.Exit(code=1)
```

### Phase 5: Environment Configuration

#### `.env.example` additions:

```bash
# Auto-Sync Configuration
AUTO_SYNC_ENABLED=true
AUTO_SYNC_PATHS=/home/user/projects,/opt/repos
AUTO_SYNC_EXCLUDE=node_modules,.git,venv,__pycache__,build,dist
AUTO_SYNC_SCAN_INTERVAL=3600  # 1 hour
AUTO_SYNC_INTERVAL=300  # 5 minutes
AUTO_SYNC_MAX_CONCURRENT=3
AUTO_SYNC_PRIORITY_LANGUAGES=python,javascript,typescript
AUTO_SYNC_SIZE_THRESHOLD=104857600  # 100MB
AUTO_SYNC_AUTO_WATCH=true
AUTO_SYNC_ON_STARTUP=true
```

### Phase 6: MCP Tool Definitions

Add to the tools list in `enhanced_server.py`:

```python
types.Tool(
    name="configure_auto_sync",
    description="Configure automatic repository synchronization settings",
    inputSchema={
        "type": "object",
        "properties": {
            "scan_paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Paths to scan for repositories"
            },
            "exclude_patterns": {
                "type": "array", 
                "items": {"type": "string"},
                "description": "Patterns to exclude from scanning"
            },
            "scan_interval": {
                "type": "number",
                "description": "Scan interval in seconds"
            },
            "max_concurrent": {
                "type": "number",
                "description": "Maximum concurrent sync operations"
            },
            "priority_languages": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Languages to prioritize"
            }
        }
    }
),
types.Tool(
    name="get_auto_sync_status",
    description="Get current status of automatic repository synchronization",
    inputSchema={
        "type": "object",
        "properties": {}
    }
),
types.Tool(
    name="trigger_repository_scan",
    description="Manually trigger a scan for new repositories",
    inputSchema={
        "type": "object",
        "properties": {}
    }
),
types.Tool(
    name="pause_auto_sync",
    description="Temporarily pause automatic synchronization",
    inputSchema={
        "type": "object",
        "properties": {}
    }
),
types.Tool(
    name="resume_auto_sync",
    description="Resume automatic synchronization",
    inputSchema={
        "type": "object",
        "properties": {}
    }
)
```

## Usage Examples

### Initial Setup
```bash
# Configure auto-sync
python cli.py auto-sync-config \
  --path ~/projects \
  --path /opt/workspace \
  --exclude node_modules \
  --exclude .git \
  --scan-interval 3600 \
  --enabled

# Check status
python cli.py auto-sync-status

# Manually trigger scan
python cli.py auto-sync-scan
```

### Claude Desktop Integration
```javascript
// In Claude Desktop
await use_mcp_tool("configure_auto_sync", {
  scan_paths: ["/home/user/projects", "/opt/repos"],
  exclude_patterns: ["node_modules", ".git", "build"],
  priority_languages: ["python", "javascript"]
});

// Check status
const status = await use_mcp_tool("get_auto_sync_status", {});
```

## Benefits

1. **Zero-Configuration**: Just set paths and the system discovers everything
2. **Intelligent Prioritization**: Syncs important repos first
3. **Resource Efficient**: Configurable concurrency and size limits
4. **Continuous Updates**: Automatic file watching after initial sync
5. **Flexible Control**: Manual triggers and pause/resume capabilities

## Testing

### Test Scripts

#### `test_auto_discovery.py`:
```python
import asyncio
from pathlib import Path
from mcp_memory_service.code_intelligence.sync.auto_discovery import RepositoryDiscovery

async def test_discovery():
    discovery = RepositoryDiscovery(
        scan_paths=["/home/user/test-projects"],
        exclude_patterns=["node_modules", ".git"]
    )
    
    repos = await discovery.discover_repositories()
    
    print(f"Found {len(repos)} repositories:")
    for repo in repos:
        print(f"  - {repo.name} ({repo.language}): {repo.path}")
        print(f"    Size: {repo.size / 1024 / 1024:.2f} MB")
        print(f"    Indicators: {', '.join(repo.indicators)}")

if __name__ == "__main__":
    asyncio.run(test_discovery())
```

## Security Considerations

1. **Path Validation**: Only scan configured paths
2. **Size Limits**: Prevent scanning huge repositories
3. **Resource Limits**: Configurable concurrent operations
4. **Permission Handling**: Gracefully handle permission errors
5. **State Persistence**: Secure storage of sync state

## Performance Optimization

1. **Parallel Discovery**: Async scanning of directories
2. **Incremental Sync**: Only sync changed files
3. **Priority Queue**: Important repos first
4. **Resource Pooling**: Limited concurrent operations
5. **Caching**: Remember synced repositories

## Monitoring

The system integrates with existing metrics:
- Repository discovery statistics
- Sync performance metrics  
- Error tracking and reporting
- Resource utilization monitoring

## Future Enhancements

1. **Smart Detection**: ML-based repository importance scoring
2. **Dependency Analysis**: Sync dependent repos together
3. **Team Sync**: Shared repository lists for teams
4. **Cloud Integration**: Sync from GitHub/GitLab/Bitbucket
5. **Scheduled Sync**: Different schedules for different repos