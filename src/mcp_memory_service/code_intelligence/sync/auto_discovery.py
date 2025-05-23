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
                # Try to get repo name from git config
                git_config = path / '.git' / 'config'
                if git_config.exists():
                    with open(git_config, 'r') as f:
                        content = f.read()
                        # Simple extraction of remote URL
                        if 'url = ' in content:
                            for line in content.split('\n'):
                                if 'url = ' in line:
                                    url = line.split('url = ')[1].strip()
                                    if '/' in url:
                                        repo_name = url.split('/')[-1]
                                        if repo_name.endswith('.git'):
                                            repo_name = repo_name[:-4]
                                        return repo_name
            except:
                pass
        
        # Fallback to directory name
        return path.name