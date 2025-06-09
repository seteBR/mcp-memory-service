# Fix 015: Code Intelligence Blocking Issue

## Issue Description
After calling any code intelligence tool (sync_repository, batch_analyze_repository, etc.), all subsequent memory tool calls hang and don't complete. This is a critical blocking issue preventing proper operation of the MCP memory service.

## Root Cause Analysis

### 1. Async Repository Sync Returns Immediately
The `AsyncRepositorySync.sync_repository` method returns immediately with a partial result (0 files) while spawning background tasks:

```python
# From async_repository_sync.py lines 201-213
# Start async file scanning
scan_task = asyncio.create_task(self._scan_repository_async(repo_path))

# Return immediately with initial result
# The background worker will continue processing
asyncio.create_task(self._complete_sync(
    repository_name, repo_path, scan_task, result, 
    incremental, force_full, start_time
))

# Return partial result immediately
result.sync_duration = time.time() - start_time
return result
```

This creates orphaned background tasks that may be holding locks or resources.

### 2. ChromaDB Lock Mechanism
The code uses a file-based lock mechanism for ChromaDB operations. If a background task holds this lock, subsequent operations will block:

```python
# From chroma_lock.py
@with_chroma_lock
@with_retry(max_retries=3, delay=1.0)
async def store_memory(self, memory: Memory) -> str:
    # This will block if lock is held by background task
```

### 3. Thread Pool Exhaustion
The async repository sync uses ThreadPoolExecutor:

```python
# From async_repository_sync.py line 298
with ThreadPoolExecutor(max_workers=4) as executor:
    return await loop.run_in_executor(
        executor, 
        self._scan_repository_sync, 
        repo_path
    )
```

If these threads are not properly cleaned up, they may exhaust the thread pool.

## Evidence of Blocking

1. `batch_analyze_repository` returns without output
2. `get_repository_status` shows 0 files after sync
3. Subsequent memory tool calls hang indefinitely
4. No progress tracking available during sync

## Potential Fixes

### Fix 1: Implement Proper Task Tracking
Track all background tasks and ensure they complete or are cancelled:

```python
class AsyncRepositorySync:
    def __init__(self, storage_backend):
        self.storage = storage_backend
        self.background_tasks = []
        self.sync_lock = asyncio.Lock()
    
    async def cleanup_tasks(self):
        """Cancel all background tasks"""
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.background_tasks, return_exceptions=True)
        self.background_tasks.clear()
```

### Fix 2: Use Context Managers for Lock Management
Ensure locks are always released:

```python
async def sync_repository(self, ...):
    async with self.sync_lock:
        # Do sync work
        pass
    # Lock automatically released
```

### Fix 3: Implement Synchronous Option
Add option for synchronous execution when progress tracking is needed:

```python
async def sync_repository(self, ..., wait_for_completion=False):
    if wait_for_completion:
        # Execute synchronously and return complete result
        files = await self._scan_repository_async(repo_path)
        result = await self._process_files_async(files)
        return result
    else:
        # Current async behavior
        ...
```

### Fix 4: Add Progress Tracking API
Implement proper progress tracking that doesn't rely on shared state:

```python
class SyncProgressTracker:
    def __init__(self):
        self.progress = {}
    
    async def get_progress(self, repository_name):
        """Get current sync progress without blocking"""
        return self.progress.get(repository_name, {
            'status': 'idle',
            'files_processed': 0,
            'total_files': 0
        })
```

## Immediate Workaround

Until fixed, avoid using code intelligence tools in the same session as memory tools. If you must use them:

1. Use code intelligence tools first
2. Restart the MCP server
3. Then use memory tools

## Test Case

```python
# This sequence causes blocking:
await mcp.sync_repository("/path/to/repo", "repo-name")
await mcp.store_memory("test")  # This will hang

# Expected: Both operations complete
# Actual: store_memory hangs indefinitely
```

## Impact

- **Severity**: HIGH - Completely blocks memory service functionality
- **Affected Tools**: All memory tools after any code intelligence tool
- **Workaround**: Restart MCP server between code intelligence and memory operations

## Next Steps

1. Implement proper task lifecycle management
2. Add timeout to all async operations
3. Ensure all locks are released properly
4. Add integration tests for mixed tool usage
5. Consider making code intelligence tools fully synchronous until async issues are resolved