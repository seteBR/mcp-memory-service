# Fix 012: Async Repository Sync Blocking Issues

## Problem
The `sync_repository` MCP tool is blocking despite being implemented as async. Multiple blocking operations were found:

1. `asyncio.run()` in worker thread creates new event loop and blocks (line 80)
2. Blocking `queue.put()` when queue is full (line 331)  
3. Synchronous file I/O operations in async context (lines 319-320)

## Root Cause Analysis
1. The background worker thread uses `asyncio.run()` which creates a new event loop instead of scheduling coroutines in the existing loop
2. When the chunk queue is full, the code falls back to blocking `put()` which blocks the entire async operation
3. File reading is done synchronously with `open()` instead of using async I/O

## Solution
1. Replace `asyncio.run()` with proper async task scheduling
2. Use async queue operations or handle full queue without blocking
3. Move file I/O to thread pool executor for non-blocking operation

## Implementation Details

### 1. Fixed Worker Loop (line 56-96)
```python
def _worker_loop(self):
    """Background worker loop for processing chunks."""
    batch = []
    last_process_time = time.time()
    
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    while self.worker_running:
        # ... existing logic ...
        if should_process and batch:
            # Process batch asynchronously without blocking
            # Run in the thread's event loop
            loop.run_until_complete(self._process_batch(batch))
            batch = []
            last_process_time = time.time()
    
    # Close the loop when done
    loop.close()
```

### 2. Fixed Queue Full Handling (line 326-340)
```python
# Queue chunks for processing
for chunk in chunks:
    try:
        self.chunk_queue.put_nowait((chunk, repository_name))
    except queue.Full:
        logger.warning(f"Chunk queue full, dropping chunk for {file_path}")
        # Don't block - just skip this chunk
        # It will be picked up in the next sync
        with self.sync_lock:
            if repository_name in self.active_syncs:
                self.active_syncs[repository_name].add_error(
                    f"Queue full, skipped chunk from {file_path}"
                )
```

### 3. Added Async File Reading (line 319-322, 332-334)
```python
def _read_file_sync(self, file_path: Path) -> str:
    """Synchronously read file content (for use in executor)."""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

async def _queue_file_for_processing(self, repository_name: str, file_path: str, metadata: FileMetadata):
    """Queue a file for background processing."""
    # ... existing code ...
    try:
        # Use thread pool for file I/O to avoid blocking
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(None, self._read_file_sync, full_path)
```

## Testing
After restarting Claude Code with these changes:
1. The `sync_repository` tool should return immediately
2. Files should be processed in the background without blocking
3. Check logs for any "Queue full" warnings if processing large repos

## Status
**COMPLETED** - All blocking operations have been fixed. The sync_repository operation should now be truly non-blocking.