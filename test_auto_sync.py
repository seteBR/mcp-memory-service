#!/usr/bin/env python3
"""
Test script for auto-sync functionality.
"""
import asyncio
import os
import sys
import tempfile
import shutil
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_memory_service.code_intelligence.sync.auto_discovery import RepositoryDiscovery, RepositoryInfo
from mcp_memory_service.code_intelligence.sync.auto_sync_manager import AutoSyncManager, AutoSyncConfig

async def test_repository_discovery():
    """Test repository discovery functionality."""
    print("=== Testing Repository Discovery ===\n")
    
    # Create a temporary directory structure with fake repositories
    with tempfile.TemporaryDirectory() as temp_dir:
        # Create test repositories
        repos = {
            'python-project': ['main.py', 'requirements.txt', 'README.md'],
            'javascript-project': ['index.js', 'package.json', 'README.md'],
            'mixed-project': ['app.py', 'server.js', 'package.json', 'requirements.txt'],
            'not-a-repo': ['document.txt', 'image.png'],  # Should not be detected
        }
        
        for repo_name, files in repos.items():
            repo_path = Path(temp_dir) / repo_name
            repo_path.mkdir()
            
            # Add .git directory to real repos
            if repo_name != 'not-a-repo':
                (repo_path / '.git').mkdir()
            
            # Create files
            for file_name in files:
                (repo_path / file_name).write_text(f"# Content of {file_name}")
        
        # Test discovery
        discovery = RepositoryDiscovery(
            scan_paths=[temp_dir],
            exclude_patterns=['node_modules'],
            min_files=1
        )
        
        repositories = await discovery.discover_repositories()
        
        print(f"Found {len(repositories)} repositories:")
        for repo in repositories:
            print(f"\n  📁 {repo.name}")
            print(f"     Path: {repo.path}")
            print(f"     Type: {repo.type}")
            print(f"     Language: {repo.language}")
            print(f"     Size: {repo.size} bytes")
            print(f"     Indicators: {', '.join(repo.indicators)}")
        
        # Verify results
        assert len(repositories) == 3, f"Expected 3 repositories, found {len(repositories)}"
        
        # Check languages
        repo_languages = {r.name: r.language for r in repositories}
        assert repo_languages.get('python-project') == 'python'
        assert repo_languages.get('javascript-project') == 'javascript'
        assert repo_languages.get('mixed-project') in ['python', 'javascript']  # Could be either
        
        print("\n✅ Repository discovery test passed!")
        return repositories

async def test_claude_code_path_detection():
    """Test Claude Code path detection."""
    print("\n=== Testing Claude Code Path Detection ===\n")
    
    # Create a mock AutoSyncManager
    class MockStorage:
        async def query(self, *args, **kwargs):
            return []
    
    manager = AutoSyncManager(
        repository_sync=None,
        storage_backend=MockStorage(),
        metrics_collector=None
    )
    
    # Test 1: Environment variable
    original_env = os.environ.get('CLAUDE_CODE_ALLOWED_PATHS')
    try:
        os.environ['CLAUDE_CODE_ALLOWED_PATHS'] = '/test/path1,/test/path2'
        paths = await manager._get_claude_code_permitted_paths()
        
        print("Test 1 - Environment Variable:")
        print(f"  Set: CLAUDE_CODE_ALLOWED_PATHS=/test/path1,/test/path2")
        print(f"  Detected: {paths}")
        assert paths == ['/test/path1', '/test/path2'], "Failed to detect from env var"
        print("  ✅ Passed")
        
    finally:
        if original_env:
            os.environ['CLAUDE_CODE_ALLOWED_PATHS'] = original_env
        else:
            del os.environ['CLAUDE_CODE_ALLOWED_PATHS']
    
    # Test 2: Current working directory
    print("\nTest 2 - Current Working Directory:")
    cwd = os.getcwd()
    print(f"  CWD: {cwd}")
    
    # Check if CWD is a repository
    is_repo = any(os.path.exists(os.path.join(cwd, marker)) 
                  for marker in ['.git', 'package.json', 'requirements.txt'])
    print(f"  Is repository: {is_repo}")
    
    paths = await manager._get_claude_code_permitted_paths()
    if is_repo and paths:
        print(f"  Detected: {paths}")
        print("  ✅ CWD detected as repository")
    else:
        print("  ℹ️  CWD not detected (not a repository or other paths found)")
    
    # Test 3: MCP context
    print("\nTest 3 - MCP Context:")
    manager._mcp_context = {'allowed_paths': ['/mcp/path1', '/mcp/path2']}
    paths = await manager._get_claude_code_permitted_paths()
    print(f"  Set: MCP context with allowed_paths")
    print(f"  Detected: {paths}")
    assert paths == ['/mcp/path1', '/mcp/path2'], "Failed to detect from MCP context"
    print("  ✅ Passed")
    
    print("\n✅ Claude Code path detection tests completed!")

async def test_auto_sync_config():
    """Test auto-sync configuration."""
    print("\n=== Testing Auto-Sync Configuration ===\n")
    
    config = AutoSyncConfig()
    
    print("Default Configuration:")
    print(f"  Enabled: {config.enabled}")
    print(f"  Scan Interval: {config.scan_interval}s")
    print(f"  Sync Interval: {config.sync_interval}s")
    print(f"  Max Concurrent: {config.max_concurrent_syncs}")
    print(f"  Priority Languages: {config.priority_languages}")
    print(f"  Size Threshold: {config.size_threshold / 1024 / 1024}MB")
    print(f"  Auto Watch: {config.auto_watch}")
    print(f"  Sync on Startup: {config.sync_on_startup}")
    
    # Test environment configuration
    original_env = {}
    env_vars = {
        'AUTO_SYNC_ENABLED': 'false',
        'AUTO_SYNC_SCAN_INTERVAL': '7200',
        'AUTO_SYNC_MAX_CONCURRENT': '5',
        'AUTO_SYNC_PRIORITY_LANGUAGES': 'python,go,rust'
    }
    
    try:
        # Save original values
        for key in env_vars:
            original_env[key] = os.environ.get(key)
            os.environ[key] = env_vars[key]
        
        # Load from environment
        config = AutoSyncConfig.from_env()
        
        print("\nConfiguration from Environment:")
        print(f"  Enabled: {config.enabled}")
        print(f"  Scan Interval: {config.scan_interval}s")
        print(f"  Max Concurrent: {config.max_concurrent_syncs}")
        print(f"  Priority Languages: {config.priority_languages}")
        
        # Verify
        assert config.enabled == False
        assert config.scan_interval == 7200
        assert config.max_concurrent_syncs == 5
        assert config.priority_languages == ['python', 'go', 'rust']
        
        print("\n✅ Configuration test passed!")
        
    finally:
        # Restore environment
        for key, value in original_env.items():
            if value is None:
                if key in os.environ:
                    del os.environ[key]
            else:
                os.environ[key] = value

async def test_priority_sorting():
    """Test repository prioritization."""
    print("\n=== Testing Repository Prioritization ===\n")
    
    from datetime import datetime, timedelta
    
    # Create mock repositories
    repos = [
        RepositoryInfo(
            path="/path/large-java",
            name="large-java",
            type="git",
            language="java",
            size=200 * 1024 * 1024,  # 200MB
            last_modified=datetime.now() - timedelta(days=30),
            indicators=['.git']
        ),
        RepositoryInfo(
            path="/path/small-python",
            name="small-python",
            type="git",
            language="python",
            size=5 * 1024 * 1024,  # 5MB
            last_modified=datetime.now() - timedelta(days=1),
            indicators=['.git', 'requirements.txt']
        ),
        RepositoryInfo(
            path="/path/medium-javascript",
            name="medium-javascript",
            type="git",
            language="javascript",
            size=50 * 1024 * 1024,  # 50MB
            last_modified=datetime.now() - timedelta(days=7),
            indicators=['.git', 'package.json']
        ),
        RepositoryInfo(
            path="/path/tiny-typescript",
            name="tiny-typescript",
            type="git",
            language="typescript",
            size=1 * 1024 * 1024,  # 1MB
            last_modified=datetime.now() - timedelta(days=3),
            indicators=['.git', 'tsconfig.json']
        ),
    ]
    
    # Create manager with config
    class MockStorage:
        async def query(self, *args, **kwargs):
            return []
    
    manager = AutoSyncManager(
        repository_sync=None,
        storage_backend=MockStorage(),
        metrics_collector=None
    )
    
    # Prioritize
    prioritized = manager._prioritize_repositories(repos)
    
    print("Repository Priority Order:")
    for i, repo in enumerate(prioritized, 1):
        print(f"{i}. {repo.name} ({repo.language}, {repo.size / 1024 / 1024:.1f}MB)")
    
    # Verify priority order
    # Should prioritize: python/js/ts first, then smaller size, then recency
    assert prioritized[0].name == "small-python", "Python should be first"
    assert prioritized[1].name == "tiny-typescript", "TypeScript should be second"
    assert prioritized[2].name == "medium-javascript", "JavaScript should be third"
    assert prioritized[3].name == "large-java", "Large Java should be last"
    
    print("\n✅ Prioritization test passed!")

async def main():
    """Run all tests."""
    print("🧪 Auto-Sync Test Suite\n")
    
    try:
        # Run tests
        await test_repository_discovery()
        await test_claude_code_path_detection()
        await test_auto_sync_config()
        await test_priority_sorting()
        
        print("\n✅ All tests passed! 🎉")
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())