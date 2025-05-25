# Concurrent Access Troubleshooting Guide

## Quick Diagnosis

Run this command to check concurrent access health:
```bash
python -c "
import asyncio
from src.mcp_memory_service.storage.chroma import ChromaMemoryStorage
from src.mcp_memory_service.config import CHROMA_PATH

async def check():
    storage = ChromaMemoryStorage(CHROMA_PATH)
    if hasattr(storage, '_chroma_lock'):
        stats = storage._chroma_lock.get_stats()
        print('Concurrent Access Status: ENABLED')
        print(f'Total acquisitions: {stats[\"total_acquisitions\"]}')
        print(f'Failed acquisitions: {stats[\"failed_acquisitions\"]}')
        print(f'Average wait time: {stats[\"average_wait_time\"]:.3f}s')
    else:
        print('Concurrent Access Status: NOT AVAILABLE')

asyncio.run(check())
"
```

## Common Issues and Solutions

### 1. Lock Acquisition Timeout

**Symptoms:**
```
Error: Failed to acquire ChromaDB lock after 30s
TimeoutError: Could not acquire ChromaDB lock within 30s
```

**Causes:**
- Another process crashed while holding the lock
- Long-running operation blocking the lock
- Stale lock file from terminated process

**Solutions:**

1. **Check for hung processes:**
   ```bash
   # Linux/macOS
   ps aux | grep -E "mcp|memory|python.*server.py"
   
   # Windows
   tasklist | findstr "python"
   ```

2. **Remove stale lock file (if no active processes):**
   ```bash
   # Find lock file location
   find ~/.local/share/mcp-memory -name "*.lock" 2>/dev/null
   
   # Remove if stale
   rm ~/.local/share/mcp-memory/chroma_db/.chroma.lock
   ```

3. **Increase timeout for slow systems:**
   ```python
   # In your code
   @with_chroma_lock(timeout=60.0)  # Increase to 60 seconds
   ```

### 2. High Lock Contention

**Symptoms:**
- Slow operations
- High average wait times in statistics
- Frequent retry attempts in logs

**Diagnosis:**
```bash
# Check lock statistics
echo '{"tool": "get_concurrent_access_stats"}' | python -m mcp_memory_service
```

**Solutions:**

1. **Reduce concurrent operations:**
   - Limit number of Claude Code instances
   - Stagger heavy operations (like repository indexing)
   - Use batch operations instead of individual stores

2. **Optimize operations:**
   ```python
   # Bad: Individual operations
   for item in items:
       await storage.store(item)
   
   # Good: Batch operations
   await storage.store_batch(items)
   ```

3. **Adjust thread pool size:**
   ```python
   # Increase workers for better throughput
   self._executor = ThreadPoolExecutor(max_workers=8)
   ```

### 3. Windows-Specific Issues

**Symptoms:**
```
PermissionError: [WinError 32] The process cannot access the file
OSError: [Errno 13] Permission denied
```

**Causes:**
- Windows file locking is more restrictive
- Antivirus software interference
- File permissions issues

**Solutions:**

1. **Add exclusions to antivirus:**
   - Add ChromaDB path to Windows Defender exclusions
   - Exclude `.lock` files from real-time scanning

2. **Run with appropriate permissions:**
   ```bash
   # Run as administrator if needed
   runas /user:Administrator "python scripts/run_memory_server.py"
   ```

3. **Check file permissions:**
   ```powershell
   # Check permissions
   Get-Acl "~/.local/share/mcp-memory/chroma_db"
   
   # Grant full control to current user
   icacls "~/.local/share/mcp-memory/chroma_db" /grant %USERNAME%:F
   ```

### 4. Database Corruption from Concurrent Access

**Symptoms:**
```
sqlite3.DatabaseError: database disk image is malformed
ChromaDB error: Collection corrupted
Segmentation fault during query
```

**Prevention:**
- Always use the MCP interface (never bypass locking)
- Ensure proper shutdown of services
- Regular backups

**Recovery:**

1. **Use the repair script:**
   ```bash
   python scripts/rebuild_database.py
   ```

2. **Restore from backup:**
   ```bash
   # List available backups
   ls -la ~/.local/share/mcp-memory/backups/
   
   # Restore specific backup
   python scripts/restore_memories.py --backup-date 2025-01-25
   ```

3. **Export and reimport:**
   ```bash
   # Export to JSON
   python extract_chromadb_data.py
   
   # Create fresh database
   mv ~/.local/share/mcp-memory/chroma_db ~/.local/share/mcp-memory/chroma_db.old
   
   # Import clean data
   python import_clean_data.py
   ```

### 5. Performance Degradation

**Symptoms:**
- Operations taking longer over time
- Memory usage increasing
- CPU usage staying high

**Diagnosis:**
```bash
# Check metrics
echo '{"tool": "get_performance_metrics", "metric_type": "summary"}' | python -m mcp_memory_service

# Check system health
echo '{"tool": "get_system_health"}' | python -m mcp_memory_service
```

**Solutions:**

1. **Clean up old metrics:**
   ```bash
   echo '{"tool": "cleanup_metrics"}' | python -m mcp_memory_service
   ```

2. **Optimize database:**
   ```bash
   python scripts/cleanup_duplicates.py
   ```

3. **Restart with fresh thread pool:**
   ```bash
   # Restart the service
   pkill -f "mcp.*memory"
   python scripts/run_memory_server.py
   ```

## Debug Mode

Enable detailed logging to diagnose issues:

```bash
# Set debug logging
export LOG_LEVEL=DEBUG

# Run with debug output
python scripts/run_memory_server.py 2>&1 | tee debug.log

# Search for lock-related issues
grep -i "lock\|concurrent\|retry\|timeout" debug.log
```

## Lock File Locations

Default lock file locations by platform:

- **Linux/macOS**: `~/.local/share/mcp-memory/chroma_db/.chroma.lock`
- **Windows**: `%LOCALAPPDATA%\mcp-memory\chroma_db\.chroma.lock`
- **Custom**: Set via `CHROMA_DB_PATH` environment variable

## Emergency Recovery

If all else fails, perform emergency recovery:

```bash
#!/bin/bash
# emergency_recovery.sh

# 1. Stop all processes
pkill -f "mcp.*memory"
sleep 2

# 2. Remove all lock files
find ~/.local/share/mcp-memory -name "*.lock" -delete

# 3. Backup current state
cp -r ~/.local/share/mcp-memory ~/.local/share/mcp-memory.backup.$(date +%Y%m%d_%H%M%S)

# 4. Verify database integrity
python -c "
from src.mcp_memory_service.utils.db_utils import validate_database
from src.mcp_memory_service.storage.chroma import ChromaMemoryStorage
from src.mcp_memory_service.config import CHROMA_PATH

storage = ChromaMemoryStorage(CHROMA_PATH)
is_valid, message = validate_database(storage)
print(f'Database valid: {is_valid}')
print(f'Message: {message}')
"

# 5. Restart service
python scripts/run_memory_server.py
```

## Monitoring Best Practices

1. **Regular Statistics Checks:**
   ```bash
   # Add to crontab
   0 * * * * echo '{"tool": "get_concurrent_access_stats"}' | python -m mcp_memory_service >> /var/log/mcp-stats.log
   ```

2. **Alert on High Failure Rate:**
   ```python
   stats = storage._chroma_lock.get_stats()
   failure_rate = stats['failed_acquisitions'] / max(1, stats['total_acquisitions'])
   if failure_rate > 0.05:  # 5% failure rate
       print("WARNING: High lock failure rate detected")
   ```

3. **Track Wait Times:**
   ```python
   if stats['max_wait_time'] > 5.0:  # 5 seconds
       print("WARNING: Long lock wait times detected")
   ```

## Getting Help

If you continue to experience issues:

1. **Collect diagnostics:**
   ```bash
   python scripts/verify_environment_enhanced.py > diagnostics.txt
   echo '{"tool": "get_concurrent_access_stats"}' >> diagnostics.txt
   echo '{"tool": "get_system_health"}' >> diagnostics.txt
   ```

2. **Check existing issues:**
   - [GitHub Issues](https://github.com/doobidoo/mcp-memory-service/issues)

3. **Report new issue with:**
   - Diagnostics output
   - Error messages
   - Steps to reproduce
   - System information