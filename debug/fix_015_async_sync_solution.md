# Fix 015: Async Sync Solution

## Solution: Make Repository Sync Truly Async

Instead of spawning untracked background tasks, we can fix the blocking issue by making the sync operation properly async with a `wait_for_completion` parameter.

## Key Changes

### 1. Add `wait_for_completion` Parameter
```python
async def sync_repository(
    self,
    repository_path: str,
    repository_name: str,
    incremental: bool = True,
    force_full: bool = False,
    wait_for_completion: bool = True  # NEW: Default to waiting
) -> SyncResult:
```

### 2. Process Files with Proper Async/Await
Instead of creating untracked background tasks:
```python
# OLD: Creates orphaned background task
asyncio.create_task(self._complete_sync(...))
return result  # Returns immediately with 0 files
```

Do this:
```python
# NEW: Actually wait for completion
if wait_for_completion:
    await self._process_files_async(repository_name, files, result, incremental)
    # Returns with complete result
```

### 3. Use Semaphore for Concurrency Control
```python
# Limit concurrent file processing
semaphore = asyncio.Semaphore(4)

async def process_file(file_info):
    async with semaphore:
        # Process file
        chunks = await self._process_single_file(...)
```

### 4. Proper Async File I/O
```python
# Read file asynchronously
loop = asyncio.get_event_loop()
content = await loop.run_in_executor(
    None, 
    Path(file_path).read_text, 
    'utf-8'
)
```

## Benefits

1. **No Blocking**: Operations complete before returning, no orphaned tasks
2. **Progress Tracking**: Get real-time progress since we're awaiting completion
3. **Resource Control**: Semaphore limits concurrent operations
4. **Backward Compatible**: Can still use `wait_for_completion=False` for old behavior
5. **Clean State**: No background tasks holding locks or resources

## Implementation Steps

1. Update `AsyncRepositorySync` to use the new pattern
2. Default `wait_for_completion=True` in all MCP tool handlers
3. Remove the `_complete_sync` background task pattern
4. Add proper progress tracking that works with sync completion

## Testing

```python
# This should work without blocking:
result = await sync_repository("/path/to/repo", "repo-name")
print(f"Processed {result.processed_files} files")  # Shows actual count

# Memory operations work immediately after:
await store_memory("test")  # No blocking!
```

## Summary

By making the async operations truly async (waiting for completion), we avoid:
- Orphaned background tasks
- Lock contention
- Thread pool exhaustion
- Unpredictable state

The key insight is that "async" doesn't mean "fire and forget" - it means "non-blocking but coordinated".