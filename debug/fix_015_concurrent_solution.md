# Fix 015: Concurrent Operations Solution

## Solution: Allow Memory Operations During Sync

To enable memory tools to work while syncing, we implement a concurrent sync approach with these key features:

## Key Design Elements

### 1. Read-Write Lock Pattern
```python
@asynccontextmanager
async def _read_lock(self):
    """Allows concurrent reads with memory operations."""
    # Multiple readers can access concurrently
    # Writers wait for all readers to finish

@asynccontextmanager  
async def _write_lock(self):
    """Exclusive access for chunk storage."""
    # Only one writer at a time
```

### 2. Batch Processing with Pauses
```python
# Process files in batches
batch_size = 10  # Process 10 files at a time

for i in range(0, len(files_to_process), batch_size):
    batch = files_to_process[i:i + batch_size]
    
    # Process batch with read lock
    async with self._read_lock():
        await process_batch(batch)
    
    # Brief pause to allow memory operations
    await asyncio.sleep(0.1)
```

### 3. Background Option with Tracking
```python
async def sync_repository(
    self,
    repository_path: str,
    repository_name: str,
    background: bool = False  # Can run in background
) -> SyncResult:
    
    if background:
        # Start sync and return immediately
        # Memory operations can run concurrently
        return partial_result
    else:
        # Wait for completion (default)
        await sync_task
        return complete_result
```

### 4. Progress Monitoring and Cancellation
```python
# Check sync progress without blocking
status = sync.get_sync_status('repo-name')
print(f"Progress: {status['progress']['percentage']:.1f}%")

# Cancel if needed
await sync.cancel_sync('repo-name')
```

## Benefits

1. **Non-blocking Memory Operations**
   - Memory tools work during sync
   - Read operations are always fast
   - Write operations use brief exclusive locks

2. **Flexible Sync Modes**
   - `background=False`: Wait for completion (default, safe)
   - `background=True`: Return immediately (for long syncs)

3. **Resource Management**
   - Batched processing prevents resource exhaustion
   - Pauses between batches allow other operations
   - Proper task lifecycle management

4. **Observable Progress**
   - Real-time progress tracking
   - Can cancel long-running syncs
   - No orphaned background tasks

## Usage Examples

### Example 1: Safe Synchronous Sync
```python
# Default behavior - waits for completion
result = await sync_repository("/repo", "my-repo")
print(f"Synced {result.processed_files} files")

# Memory operations work immediately after
await store_memory("test")  # No blocking!
```

### Example 2: Background Sync with Concurrent Operations
```python
# Start background sync
result = await sync_repository("/repo", "my-repo", background=True)

# Memory operations work during sync
await store_memory("memory 1")  # Works!
await retrieve_memory("search")  # Works!

# Check progress
status = get_sync_status("my-repo")
print(f"Sync {status['progress']['percentage']:.1f}% complete")
```

### Example 3: Long Repository Sync
```python
# For very large repositories
result = await sync_repository("/large-repo", "big-project", background=True)

# Continue using memory tools while it syncs
for i in range(100):
    await store_memory(f"Note {i}")
    
    # Periodically check sync progress
    if i % 10 == 0:
        status = get_sync_status("big-project")
        print(f"Sync progress: {status['progress']['percentage']:.1f}%")
```

## Implementation Strategy

1. **Phase 1**: Implement read-write lock pattern
2. **Phase 2**: Batch processing with pauses
3. **Phase 3**: Progress tracking API
4. **Phase 4**: Cancellation support

## Summary

This solution provides the best of both worlds:
- **Default safety**: Sync completes before returning (no blocking issues)
- **Flexibility**: Can run in background for long syncs
- **Concurrency**: Memory operations work during sync
- **Control**: Monitor progress and cancel if needed

The key insight is using a read-write lock pattern that allows multiple concurrent readers (memory operations) while ensuring exclusive access for writers (chunk storage).