# Concurrent Access Support for MCP Memory Service

## Overview

The MCP Memory Service now supports concurrent access from multiple Claude Code instances through a robust file-based locking mechanism. This ensures data integrity when multiple instances try to read/write to the ChromaDB database simultaneously.

## Features

### 1. File-Based Locking
- Cross-platform support (Windows, macOS, Linux)
- Automatic lock acquisition with configurable timeout (default: 30 seconds)
- Lock statistics tracking for monitoring

### 2. Automatic Retry Logic
- Operations automatically retry up to 3 times on failure
- Exponential backoff between retries
- Handles transient SQLite locking errors gracefully

### 3. Request Queuing
- Built-in request queue for serializing operations when needed
- Prevents overwhelming the database with concurrent requests

### 4. Monitoring
- New MCP tool: `get_concurrent_access_stats`
- Tracks lock acquisitions, wait times, and failures
- Provides insights into concurrent usage patterns

## Implementation Details

### Decorators

The implementation uses two key decorators:

```python
@with_chroma_lock(timeout=30.0)  # Ensures exclusive access
@with_retry(max_attempts=3, delay=1.0)  # Handles transient failures
async def store(self, memory: Memory) -> Tuple[bool, str]:
    # Implementation
```

### Lock Statistics

Access lock statistics through the MCP interface:
```json
{
  "tool": "get_concurrent_access_stats"
}
```

Returns:
- Total lock acquisitions
- Failed acquisitions
- Average and maximum wait times
- Currently active locks
- Last acquisition timestamp

## Testing

Run the concurrent access test:
```bash
python tests/test_concurrent_access.py
```

This test:
1. Spawns multiple processes storing memories concurrently
2. Tests concurrent retrieval operations
3. Displays lock statistics

## Configuration

The locking mechanism is automatically enabled when using ChromaDB storage. No additional configuration is required.

### Environment Variables

- `LOG_LEVEL`: Set to `DEBUG` to see detailed lock acquisition logs

## Troubleshooting

### Common Issues

1. **"Failed to acquire ChromaDB lock after 30s"**
   - Another process is holding the lock for too long
   - Check for hung processes
   - Consider increasing the timeout

2. **High number of failed acquisitions**
   - Too many concurrent instances
   - Consider implementing a queue or load balancer

3. **Windows-specific issues**
   - Ensure proper permissions on the ChromaDB directory
   - Check antivirus software isn't interfering with file locking

## Performance Considerations

- Lock acquisition adds minimal overhead (typically <10ms)
- Read operations still require locks to ensure consistency
- For read-heavy workloads, consider implementing read-write locks in the future

## Future Improvements

- Read-write lock implementation for better read concurrency
- Distributed locking for multi-machine deployments
- Connection pooling for ChromaDB client instances