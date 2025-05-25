#!/usr/bin/env python3
"""
Test script to debug MCP memory sync operations using the MCP client.
This simulates what happens when sync_repository is called via MCP.
"""

import asyncio
import json
import logging
import signal
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_sync_mcp.log', mode='w')
    ]
)

logger = logging.getLogger(__name__)

class MCPSyncTester:
    """Test MCP memory sync operations."""
    
    def __init__(self):
        self.session = None
        self.interrupted = False
        
    async def connect_to_memory_server(self):
        """Connect to the memory MCP server."""
        logger.info("Connecting to memory MCP server...")
        
        # Find the memory server command
        memory_cmd = ["uv", "--directory", "/home/felipe/mcp-memory-service", "run", "memory"]
        
        server_params = StdioServerParameters(
            command=memory_cmd[0],
            args=memory_cmd[1:],
            env=None
        )
        
        # Start client connection
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                self.session = session
                
                # Initialize
                await session.initialize()
                logger.info("Connected to memory server")
                
                # List available tools
                tools = await session.list_tools()
                logger.info(f"Available tools: {[t.name for t in tools.tools]}")
                
                # Keep session alive for testing
                return session
    
    async def test_sync_with_timeout(self, repo_path: str, repo_name: str, timeout: int = 30):
        """Test sync operation with timeout and monitoring."""
        logger.info(f"Testing sync for {repo_name} at {repo_path} with {timeout}s timeout")
        
        try:
            # First check system health
            logger.info("Checking system health...")
            health_result = await asyncio.wait_for(
                self.session.call_tool("get_system_health", {"include_history": False}),
                timeout=5
            )
            logger.info(f"System health: {health_result}")
            
            # List current repositories
            logger.info("Listing current repositories...")
            repos_result = await asyncio.wait_for(
                self.session.call_tool("list_repositories", {}),
                timeout=5
            )
            logger.info(f"Current repositories: {repos_result}")
            
            # Start sync with monitoring
            logger.info(f"Starting repository sync...")
            start_time = time.time()
            
            # Create a task for the sync
            sync_task = asyncio.create_task(
                self.session.call_tool("sync_repository", {
                    "repository_path": repo_path,
                    "repository_name": repo_name,
                    "incremental": True,
                    "force_full": False
                })
            )
            
            # Monitor progress
            monitor_interval = 2  # seconds
            elapsed = 0
            
            while not sync_task.done() and elapsed < timeout:
                await asyncio.sleep(monitor_interval)
                elapsed = time.time() - start_time
                logger.info(f"Sync in progress... ({elapsed:.1f}s elapsed)")
                
                # Check if we can get status (might timeout if sync is blocking)
                try:
                    status_task = asyncio.create_task(
                        self.session.call_tool("get_repository_status", {
                            "repository_name": repo_name
                        })
                    )
                    
                    # Wait briefly for status
                    done, pending = await asyncio.wait([status_task], timeout=1)
                    
                    if done:
                        status = await status_task
                        logger.info(f"Repository status: {status}")
                    else:
                        logger.warning("Status check timed out (sync might be blocking)")
                        status_task.cancel()
                        
                except Exception as e:
                    logger.debug(f"Could not get status: {e}")
            
            # Check if sync completed
            if sync_task.done():
                result = await sync_task
                logger.info(f"Sync completed in {elapsed:.1f}s")
                logger.info(f"Sync result: {result}")
            else:
                logger.warning(f"Sync did not complete within {timeout}s timeout")
                sync_task.cancel()
                
                try:
                    await sync_task
                except asyncio.CancelledError:
                    logger.info("Sync task cancelled")
            
            # Final status check
            final_repos = await self.session.call_tool("list_repositories", {})
            logger.info(f"Final repositories: {final_repos}")
            
        except asyncio.TimeoutError:
            logger.error("Operation timed out")
        except Exception as e:
            logger.error(f"Test failed: {e}")
            import traceback
            traceback.print_exc()

async def main():
    """Main test function."""
    if len(sys.argv) < 2:
        print("Usage: python test_sync_mcp.py <repository_path> [repository_name] [timeout]")
        sys.exit(1)
    
    repo_path = sys.argv[1]
    repo_name = sys.argv[2] if len(sys.argv) > 2 else Path(repo_path).name
    timeout = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    
    # Create tester
    tester = MCPSyncTester()
    
    # Set up signal handler for graceful shutdown
    def signal_handler(sig, frame):
        logger.info("Interrupt received, shutting down...")
        tester.interrupted = True
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        # Connect and test
        logger.info("Starting MCP sync test...")
        
        # Find the memory server command
        memory_cmd = ["uv", "--directory", "/home/felipe/mcp-memory-service", "run", "memory"]
        
        server_params = StdioServerParameters(
            command=memory_cmd[0],
            args=memory_cmd[1:],
            env=None
        )
        
        # Run test with server connection
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                tester.session = session
                
                # Initialize
                await session.initialize()
                logger.info("Connected to memory server")
                
                # Run sync test
                await tester.test_sync_with_timeout(repo_path, repo_name, timeout)
                
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())