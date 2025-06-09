# Fix 013: Async Repository Sync Blocking Issues Resolved

**Date**: 2025-05-25
**Issue**: Repository sync operations were blocking the memory service
**Status**: FIXED

## Problem Details

The async repository sync implementation had multiple blocking patterns that could cause the memory service to become unresponsive:

1. **Worker thread blocking**: Used `loop.run_until_complete()` in a thread
2. **Storage layer error**: `run_in_executor()` called with keyword arguments
3. **Missing chunk count tracking**: Repository metadata not updated properly

## Root Cause Analysis

### 1. Worker Thread Blocking
The `_worker_loop` method created its own event loop and used `run_until_complete()` to process batches. This blocked the worker thread and defeated the purpose of async processing.

### 2. Storage Layer Issue
The `_run_async` method in ChromaMemoryStorage was passing keyword arguments directly to `run_in_executor()`, which doesn't support them:
```python
# This caused: BaseEventLoop.run_in_executor() got an unexpected keyword argument 'where'
await loop.run_in_executor(self._executor, func, *args, **kwargs)
```

### 3. Metadata Tracking
The chunk count was tracked in the sync result but not persisted to the repository metadata, causing incorrect status reporting.

## Solution Implemented

### 1. Async Worker Pattern
```python
# async_repository_sync.py - lines 56-111
def _worker_loop(self):
    """Background worker loop for processing chunks."""
    try:
        asyncio.run(self._async_worker_loop())
    except Exception as e:
        logger.error(f"Worker loop error: {e}")

async def _async_worker_loop(self):
    """Async implementation of the worker loop."""
    # Fully async processing without blocking
```

### 2. Fixed Storage Async Handling
```python
# chroma.py - lines 216-225
async def _run_async(self, func, *args, **kwargs):
    """Run a synchronous function asynchronously in the thread pool."""
    from functools import partial
    loop = asyncio.get_event_loop()
    if kwargs:
        # Use partial to handle keyword arguments
        func_with_kwargs = partial(func, *args, **kwargs)
        return await loop.run_in_executor(self._executor, func_with_kwargs)
    else:
        return await loop.run_in_executor(self._executor, func, *args)
```

### 3. Proper Metadata Updates
```python
# async_repository_sync.py - lines 142-144
# Update repository metadata
if repo_name in self.repositories:
    self.repositories[repo_name]['total_chunks'] = \
        self.repositories[repo_name].get('total_chunks', 0) + stored
```

## Testing Results

Test output showing successful non-blocking sync:
```
Testing sync for repository: /home/felipe/mcp-memory-service/scripts
Scanned 36 total files, found 29 matching files
Processing batch of 100 chunks
Stored 100/100 chunks for mcp-memory-service
Progress: 29/29 files, 206 chunks, 0 errors
Final repository status:
  Files: 29
  Chunks: 206
```

## Impact

- Repository sync no longer blocks the memory service
- Code intelligence features can run in background
- Progress tracking works correctly
- No more "BaseEventLoop.run_in_executor() got an unexpected keyword argument" errors

## Files Modified

1. `/src/mcp_memory_service/code_intelligence/sync/async_repository_sync.py`
   - Changed worker loop to use `asyncio.run()`
   - Added `_async_worker_loop()` method
   - Fixed chunk count tracking
   - Added comprehensive logging

2. `/src/mcp_memory_service/storage/chroma.py`
   - Fixed `_run_async()` to handle keyword arguments with `functools.partial`

3. `/src/mcp_memory_service/enhanced_server.py`
   - No changes needed - already using async properly

## Verification Steps

1. Start memory service with code intelligence enabled
2. Trigger repository sync
3. Verify service remains responsive during sync
4. Check progress updates work correctly
5. Confirm chunk counts are accurate

## Lessons Learned

1. Always use `asyncio.run()` for running async code in threads
2. `run_in_executor()` requires special handling for keyword arguments
3. Metadata updates must be synchronized across async operations
4. Comprehensive logging is essential for debugging async issues