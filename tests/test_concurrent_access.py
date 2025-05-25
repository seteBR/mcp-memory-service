"""Test concurrent access to the MCP Memory Service."""

import asyncio
import multiprocessing
import time
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.mcp_memory_service.models.memory import Memory
from src.mcp_memory_service.storage.chroma import ChromaMemoryStorage
from src.mcp_memory_service.utils.hashing import generate_content_hash
from src.mcp_memory_service.config import CHROMA_PATH


async def store_memories(process_id: int, num_memories: int = 10):
    """Store memories from a specific process."""
    storage = ChromaMemoryStorage(CHROMA_PATH)
    
    successes = 0
    failures = 0
    
    for i in range(num_memories):
        content = f"Process {process_id} - Memory {i} - Time {time.time()}"
        metadata = {
            "tags": f"process-{process_id},test",
            "type": "test"
        }
        
        memory = Memory(
            content=content,
            content_hash=generate_content_hash(content, metadata),
            tags=[f"process-{process_id}", "test"],
            memory_type="test",
            metadata=metadata,
            created_at=time.time(),
            created_at_iso=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )
        
        try:
            success, message = await storage.store(memory)
            if success:
                successes += 1
                print(f"Process {process_id}: Stored memory {i}")
            else:
                failures += 1
                print(f"Process {process_id}: Failed to store memory {i}: {message}")
        except Exception as e:
            failures += 1
            print(f"Process {process_id}: Error storing memory {i}: {e}")
        
        # Small delay to simulate real usage
        await asyncio.sleep(0.1)
    
    print(f"Process {process_id}: Completed - {successes} successes, {failures} failures")
    return successes, failures


def run_process(process_id: int):
    """Run the async store_memories function in a process."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(store_memories(process_id))


async def test_concurrent_retrieval(num_processes: int = 3):
    """Test concurrent retrieval operations."""
    storage = ChromaMemoryStorage(CHROMA_PATH)
    
    async def retrieve_task(task_id: int):
        """Retrieve memories concurrently."""
        results = []
        for i in range(5):
            try:
                memories = await storage.retrieve(f"Process {task_id % num_processes}", n_results=10)
                results.append(len(memories))
                print(f"Task {task_id}: Retrieved {len(memories)} memories")
            except Exception as e:
                print(f"Task {task_id}: Error retrieving: {e}")
                results.append(0)
            await asyncio.sleep(0.05)
        return results
    
    # Create multiple concurrent retrieval tasks
    tasks = [retrieve_task(i) for i in range(num_processes * 2)]
    results = await asyncio.gather(*tasks)
    
    print(f"\nRetrieval test completed. Total tasks: {len(tasks)}")
    for i, task_results in enumerate(results):
        print(f"Task {i}: Retrieved {sum(task_results)} total memories across {len(task_results)} queries")


async def check_lock_stats():
    """Check the lock statistics."""
    storage = ChromaMemoryStorage(CHROMA_PATH)
    if hasattr(storage, '_chroma_lock'):
        stats = storage._chroma_lock.get_stats()
        print("\n=== Lock Statistics ===")
        for key, value in stats.items():
            print(f"{key}: {value}")
        print("====================\n")


def main():
    """Main test function."""
    print("Testing concurrent access to MCP Memory Service")
    print("=" * 50)
    
    # Number of concurrent processes
    num_processes = 3
    
    print(f"\n1. Testing concurrent storage with {num_processes} processes...")
    
    # Create processes for concurrent storage
    with multiprocessing.Pool(processes=num_processes) as pool:
        results = pool.map(run_process, range(num_processes))
    
    # Print results
    total_successes = sum(r[0] for r in results)
    total_failures = sum(r[1] for r in results)
    print(f"\nStorage test completed:")
    print(f"  Total successes: {total_successes}")
    print(f"  Total failures: {total_failures}")
    
    # Test concurrent retrieval
    print(f"\n2. Testing concurrent retrieval...")
    asyncio.run(test_concurrent_retrieval(num_processes))
    
    # Check lock statistics
    print(f"\n3. Checking lock statistics...")
    asyncio.run(check_lock_stats())
    
    print("\nTest completed!")


if __name__ == "__main__":
    # Ensure multiprocessing works correctly on all platforms
    multiprocessing.set_start_method('spawn', force=True)
    main()