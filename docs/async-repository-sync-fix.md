# Async Repository Sync - Non-blocking Implementation

## Overview

The async repository sync feature was experiencing blocking issues that could cause the memory service to become unresponsive during code intelligence operations. This document describes the fixes implemented to resolve these issues.

## Problem Statement

The original implementation had several blocking patterns:
1. The worker thread used `loop.run_until_complete()` which blocked the thread
2. The storage layer incorrectly passed keyword arguments to `run_in_executor()`
3. Repository sync operations could block the main MCP service

## Solution Implementation

### 1. Non-blocking Worker Thread

**Before:**
```python
def _worker_loop(self):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # ...
    loop.run_until_complete(self._process_batch(batch))  # BLOCKING!
```

**After:**
```python
def _worker_loop(self):
    # Use asyncio.run for clean async execution
    try:
        asyncio.run(self._async_worker_loop())
    except Exception as e:
        logger.error(f"Worker loop error: {e}")

async def _async_worker_loop(self):
    # Fully async implementation
    while self.worker_running:
        await asyncio.sleep(0.01)  # Yield to prevent busy waiting
        # ... process batches asynchronously
        await self._process_batch(batch)
```

### 2. Fixed Storage Layer Async Operations

**Problem:** `run_in_executor()` doesn't accept keyword arguments directly

**Solution:**
```python
async def _run_async(self, func, *args, **kwargs):
    from functools import partial
    loop = asyncio.get_event_loop()
    if kwargs:
        # Use partial to handle keyword arguments
        func_with_kwargs = partial(func, *args, **kwargs)
        return await loop.run_in_executor(self._executor, func_with_kwargs)
    else:
        return await loop.run_in_executor(self._executor, func, *args)
```

### 3. Enhanced Logging and Monitoring

Added comprehensive logging to track sync progress:
```python
logger.info(f"Scanning repository at {repo_path} for extensions: {supported_extensions}")
logger.info(f"Scanned {total_files_scanned} total files, found {len(files)} matching files")
logger.debug(f"Created {len(chunks)} chunks for file {file_path}")
logger.debug(f"Stored {stored}/{len(chunks)} chunks for {repo_name}")
```

### 4. Proper Metadata Tracking

Fixed chunk count tracking in repository metadata:
```python
# Update repository metadata when chunks are stored
if repo_name in self.repositories:
    self.repositories[repo_name]['total_chunks'] = \
        self.repositories[repo_name].get('total_chunks', 0) + stored
```

## Usage

### Testing the Implementation

```python
# Test script to verify non-blocking behavior
from src.mcp_memory_service.code_intelligence.sync.async_repository_sync import AsyncRepositorySync
from src.mcp_memory_service.storage.chroma import ChromaMemoryStorage

# Initialize storage
storage = ChromaMemoryStorage("/path/to/chromadb")

# Create async sync
sync = AsyncRepositorySync(storage)

# Start sync (returns immediately)
result = await sync.sync_repository(
    repository_path="/path/to/repo",
    repository_name="my-repo",
    incremental=False,
    force_full=True
)

# Check status while sync runs in background
status = sync.get_sync_status("my-repo")
print(f"Active: {status['active']}")
print(f"Progress: {status['progress']['processed_files']}/{status['progress']['total_files']}")
```

### Integration with MCP Server

The enhanced_server.py uses the async repository sync:

```python
async def _handle_sync_repository(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
    # This now returns immediately with initial status
    result = await self.repository_sync.sync_repository(
        repository_path=repository_path,
        repository_name=repository_name,
        incremental=incremental,
        force_full=force_full
    )
    # Sync continues in background
```

## Performance Characteristics

- **Non-blocking**: Repository sync operations return immediately
- **Background processing**: Files are processed in batches of 100 chunks
- **Thread pool**: Uses 4 workers for file I/O operations
- **Memory efficient**: Queue-based processing prevents memory bloat
- **Progress tracking**: Real-time status updates available

## File Type Support

Supported file extensions:
- Python: `.py`, `.pyw`
- JavaScript/TypeScript: `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`
- Go: `.go`
- Rust: `.rs`

## Monitoring and Debugging

### Check Sync Status
```python
# Get real-time sync status
status = sync.get_sync_status("repository-name")
if status['active']:
    print(f"Processing: {status['progress']['processed_files']} files")
    print(f"Chunks: {status['progress']['total_chunks']}")
    print(f"Errors: {status['progress']['errors']}")
```

### Enable Debug Logging
```bash
export LOG_LEVEL=DEBUG
python scripts/run_memory_server.py
```

## Error Handling

The implementation includes:
- Automatic retry on transient failures
- Queue overflow protection
- File access error handling
- Graceful shutdown support

## Future Improvements

1. **Configurable batch size**: Allow tuning based on system resources
2. **Priority queue**: Process recently modified files first
3. **Incremental chunk updates**: Update only changed chunks
4. **Parallel file processing**: Use multiple workers for file reading
5. **Progress persistence**: Resume interrupted syncs

## Related Files

- `/src/mcp_memory_service/code_intelligence/sync/async_repository_sync.py` - Main implementation
- `/src/mcp_memory_service/storage/chroma.py` - Storage layer fixes
- `/src/mcp_memory_service/enhanced_server.py` - MCP integration
- `/debug/fix_012_async_sync_blocking.md` - Detailed fix notes