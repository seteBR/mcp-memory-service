#!/usr/bin/env python3
"""
Simple debug script for MCP memory sync - tracks what happens during sync.
"""

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug_sync_simple.log', mode='w')
    ]
)

logger = logging.getLogger(__name__)

async def monitor_chromadb_lock(duration: int = 30):
    """Monitor ChromaDB lock file for a specified duration."""
    lock_path = Path.home() / '.local' / 'share' / 'mcp-memory' / 'chroma_db' / '.chroma.lock'
    logger.info(f"Monitoring lock file: {lock_path}")
    
    start_time = time.time()
    
    while time.time() - start_time < duration:
        if lock_path.exists():
            try:
                stat = lock_path.stat()
                # Check if file is locked
                with open(lock_path, 'r') as f:
                    import fcntl
                    try:
                        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                        lock_status = "NOT LOCKED"
                    except IOError:
                        lock_status = "LOCKED"
                
                logger.info(f"Lock file: EXISTS - Size: {stat.st_size} - Status: {lock_status}")
            except Exception as e:
                logger.error(f"Error checking lock: {e}")
        else:
            logger.info("Lock file: DOES NOT EXIST")
        
        await asyncio.sleep(1)

async def test_mcp_sync():
    """Test memory sync via direct MCP call."""
    import subprocess
    
    # Start monitoring in background
    monitor_task = asyncio.create_task(monitor_chromadb_lock(60))
    
    # Prepare test repository
    test_repo = sys.argv[1] if len(sys.argv) > 1 else "/home/felipe/mcp-memory-service"
    repo_name = Path(test_repo).name
    
    logger.info(f"Testing sync for: {test_repo}")
    
    # Create a simple Python script that calls MCP memory sync
    test_script = f"""
import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    # Connect to memory server
    server_params = StdioServerParameters(
        command="uv",
        args=["--directory", "/home/felipe/mcp-memory-service", "run", "memory"],
        env=None
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List repositories before
            print("BEFORE:", await session.call_tool("list_repositories", {{}}))
            
            # Try to sync
            print("Starting sync...")
            try:
                result = await asyncio.wait_for(
                    session.call_tool("sync_repository", {{
                        "repository_path": "{test_repo}",
                        "repository_name": "{repo_name}",
                        "incremental": True
                    }}),
                    timeout=30
                )
                print("SYNC RESULT:", result)
            except asyncio.TimeoutError:
                print("SYNC TIMEOUT after 30 seconds")
            
            # List repositories after
            print("AFTER:", await session.call_tool("list_repositories", {{}}))

asyncio.run(main())
"""
    
    # Write test script
    test_script_path = Path("test_sync_runner.py")
    test_script_path.write_text(test_script)
    
    # Run the test script in a subprocess
    logger.info("Running MCP sync test...")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        str(test_script_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    
    # Wait for completion or timeout
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=45)
        logger.info(f"Test completed with code: {proc.returncode}")
        logger.info(f"STDOUT:\n{stdout.decode()}")
        if stderr:
            logger.error(f"STDERR:\n{stderr.decode()}")
    except asyncio.TimeoutError:
        logger.error("Test script timed out after 45 seconds")
        proc.terminate()
        await proc.wait()
    
    # Stop monitoring
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        pass
    
    # Cleanup
    test_script_path.unlink(missing_ok=True)

async def check_processes():
    """Check for memory-related processes."""
    proc = await asyncio.create_subprocess_exec(
        'ps', 'aux',
        stdout=asyncio.subprocess.PIPE
    )
    stdout, _ = await proc.communicate()
    
    logger.info("Memory-related processes:")
    for line in stdout.decode().split('\n'):
        if 'memory' in line and 'grep' not in line:
            logger.info(f"  {line.strip()}")

async def main():
    """Main debug function."""
    logger.info("="*60)
    logger.info("MCP Memory Sync Debug Tool")
    logger.info("="*60)
    
    # Check processes
    await check_processes()
    
    # Run sync test
    await test_mcp_sync()
    
    # Final process check
    logger.info("\nFinal process check:")
    await check_processes()
    
    logger.info("\nDebug session complete. Check debug_sync_simple.log for details.")

if __name__ == "__main__":
    asyncio.run(main())