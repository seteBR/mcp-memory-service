#!/usr/bin/env python3
"""Debug script to test enhanced server startup."""

import asyncio
import logging
import sys
import time
from pathlib import Path

# Setup logging to see what's happening
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

async def test_enhanced_server():
    """Test enhanced server startup."""
    print("Starting enhanced server test...")
    start_time = time.time()
    
    try:
        from mcp_memory_service.enhanced_server import EnhancedMemoryServer
        
        print(f"[{time.time() - start_time:.2f}s] Importing EnhancedMemoryServer completed")
        
        # Create server instance
        print(f"[{time.time() - start_time:.2f}s] Creating server instance...")
        server = EnhancedMemoryServer(
            enable_code_intelligence=True,
            enable_file_watching=False,  # Disable to reduce complexity
            enable_metrics=True
        )
        print(f"[{time.time() - start_time:.2f}s] Server instance created")
        
        # Register handlers
        print(f"[{time.time() - start_time:.2f}s] Registering handlers...")
        server.register_handlers()
        print(f"[{time.time() - start_time:.2f}s] Handlers registered")
        
        # Test get_system_health
        print(f"[{time.time() - start_time:.2f}s] Testing get_system_health...")
        result = await server._handle_get_system_health({})
        print(f"[{time.time() - start_time:.2f}s] get_system_health completed")
        print("Result:", result[0].text[:200] + "..." if len(result[0].text) > 200 else result[0].text)
        
        # Wait a bit to see if auto-sync starts
        print(f"[{time.time() - start_time:.2f}s] Waiting for auto-sync to start...")
        await asyncio.sleep(10)
        print(f"[{time.time() - start_time:.2f}s] Auto-sync status: {server._should_start_auto_sync}")
        
        print(f"\n✅ Test completed successfully in {time.time() - start_time:.2f}s")
        
    except Exception as e:
        print(f"\n❌ Error after {time.time() - start_time:.2f}s: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_enhanced_server())