# Fix 009: Async Repository Sync - Non-blocking Operations

## Issue
When using the `sync_repository` MCP tool, the entire memory service would become unresponsive. All other MCP operations would hang until the sync completed, making the service unusable during repository synchronization.

## Root Cause
The `RepositorySync` class was processing files synchronously within the async context. When storing chunks to ChromaDB, it would acquire a lock and process each file sequentially, blocking the entire async event loop. This prevented any other MCP tools from executing.

## Solution
Implemented `AsyncRepositorySync` class that:
1. Uses a background worker thread with a queue for chunk processing
2. Returns immediately from `sync_repository` with initial status
3. Processes files and chunks asynchronously in the background
4. Provides real-time progress tracking via `get_sync_status`

## Changes Made

### 1. Created `AsyncRepositorySync` class
- **File**: `src/mcp_memory_service/code_intelligence/sync/async_repository_sync.py`
- Uses `queue.Queue` for chunk processing
- Background worker thread processes chunks in batches
- Non-blocking file scanning using ThreadPoolExecutor
- Real-time sync status tracking

### 2. Updated `EnhancedMemoryServer`
- **File**: `src/mcp_memory_service/enhanced_server.py`
- Added logic to use AsyncRepositorySync by default (controlled by `USE_ASYNC_SYNC` env var)
- Updated `_handle_get_repository_status` to show real-time progress for async syncs
- Added cleanup method to properly shutdown background workers

### 3. Created Debug Scripts
- `scripts/debug_sync.py` - Detailed sync debugging with lock monitoring
- `scripts/debug_sync_simple.py` - Simple test to verify sync doesn't block
- `scripts/test_sync_mcp.py` - Direct MCP client test for sync operations

## Testing
After restarting Claude Desktop with the new code:

1. Start a repository sync:
   ```
   sync_repository("/path/to/large/repo", "repo-name")
   ```

2. While sync is running, test other operations:
   ```
   store_memory("test", {"tags": "test"})
   retrieve_memory("test")
   get_repository_status("repo-name")  # Shows real-time progress
   ```

3. All operations should work without blocking.

## Configuration
The following environment variables control the async sync behavior:
- `USE_ASYNC_SYNC` - Enable async sync (default: "true")
- `SYNC_QUEUE_SIZE` - Max items in processing queue (default: "10000")
- `SYNC_BATCH_SIZE` - Chunks to process per batch (default: "100")

## Implementation Details

### Queue-based Processing
- Files are scanned and chunked immediately
- Chunks are queued for background processing
- Worker thread processes chunks in batches
- Prevents memory bloat with queue size limits

### Progress Tracking
- Active syncs tracked in `active_syncs` dictionary
- Real-time metrics updated as chunks are processed
- Status available via `get_repository_status` during sync

### Error Handling
- Errors logged but don't stop the sync
- Failed chunks can be requeued
- Sync results include error list

## Benefits
1. Memory service remains responsive during sync
2. Multiple syncs can run concurrently
3. Progress monitoring during long operations
4. Graceful error handling
5. Proper cleanup on shutdown

## Future Improvements
- Persistent queue for crash recovery
- Parallel chunk processing workers
- Chunk deduplication before storage
- Resume interrupted syncs