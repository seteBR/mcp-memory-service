#!/usr/bin/env python3
"""
Test script to demonstrate Claude Code path detection for auto-sync.
"""
import asyncio
import os
import sys
from pathlib import Path

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_memory_service.code_intelligence.sync.auto_sync_manager import AutoSyncManager

async def test_path_detection():
    """Test the Claude Code path detection methods."""
    
    print("Testing Claude Code Path Detection for Auto-Sync")
    print("=" * 50)
    
    # Create a minimal auto-sync manager instance
    class MockStorage:
        async def query(self, *args, **kwargs):
            return []
    
    manager = AutoSyncManager(
        repository_sync=None,  # Not needed for this test
        storage_backend=MockStorage(),
        metrics_collector=None
    )
    
    # Test different scenarios
    print("\n1. Current Environment Variables:")
    print(f"   AUTO_SYNC_PATHS: {os.getenv('AUTO_SYNC_PATHS', '(not set)')}")
    print(f"   CLAUDE_CODE_ALLOWED_PATHS: {os.getenv('CLAUDE_CODE_ALLOWED_PATHS', '(not set)')}")
    print(f"   Current Working Directory: {os.getcwd()}")
    
    # Get detected paths
    print("\n2. Detecting Claude Code Paths...")
    paths = await manager._get_claude_code_permitted_paths()
    
    if paths:
        print(f"\n✅ Found {len(paths)} path(s):")
        for i, path in enumerate(paths, 1):
            print(f"   {i}. {path}")
            # Check if it's a repository
            path_obj = Path(path)
            if path_obj.exists():
                markers = []
                if (path_obj / '.git').exists():
                    markers.append('.git')
                if (path_obj / 'package.json').exists():
                    markers.append('package.json')
                if (path_obj / 'requirements.txt').exists():
                    markers.append('requirements.txt')
                if markers:
                    print(f"      Repository markers: {', '.join(markers)}")
    else:
        print("\n❌ No paths detected")
        print("\n   To enable auto-detection, try one of:")
        print("   - Set CLAUDE_CODE_ALLOWED_PATHS=/path/to/projects")
        print("   - Run from within a git repository")
        print("   - Create ~/.claude/config.json with allowed_paths")
    
    # Test with simulated Claude Code environment
    print("\n3. Simulating Claude Code Environment:")
    os.environ['CLAUDE_CODE_ALLOWED_PATHS'] = '/home/user/project1,/home/user/project2'
    
    paths = await manager._get_claude_code_permitted_paths()
    print(f"\n✅ With CLAUDE_CODE_ALLOWED_PATHS set:")
    for path in paths:
        print(f"   - {path}")
    
    # Clean up
    del os.environ['CLAUDE_CODE_ALLOWED_PATHS']
    
    print("\n4. Testing Override:")
    os.environ['AUTO_SYNC_PATHS'] = '/my/custom/path'
    
    # Check what the actual start method would use
    scan_paths = os.getenv('AUTO_SYNC_PATHS', '').split(',')
    scan_paths = [p.strip() for p in scan_paths if p.strip()]
    
    if scan_paths:
        print(f"   AUTO_SYNC_PATHS is set, will use: {scan_paths}")
        print("   (This overrides Claude Code detection)")
    
    # Clean up
    del os.environ['AUTO_SYNC_PATHS']

if __name__ == "__main__":
    asyncio.run(test_path_detection())