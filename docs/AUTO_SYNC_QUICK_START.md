# Auto-Sync Quick Start Guide

## Overview

The Auto-Sync feature automatically discovers and synchronizes code repositories without manual intervention. It intelligently uses Claude Code's permitted directories when available.

## Quick Start

### 1. Basic Setup (Zero Configuration)

```bash
# Just enable auto-sync - it will use Claude Code's permissions automatically
export AUTO_SYNC_ENABLED=true

# Start the server
python -m mcp_memory_service.enhanced_server
```

The system will:
- Automatically detect Claude Code's permitted directories
- Scan for code repositories
- Prioritize and sync them based on language and size
- Enable file watching for continuous updates

### 2. Check Status

```bash
# Using CLI
python cli.py auto-sync-status

# Output:
🔄 Auto-Sync Status
==================================================
Enabled: ✅
Running: ✅
Last Scan: 2025-05-23T14:30:00

Queued Repositories: 3
Active Syncs: 2
Synced Repositories: 15

Configuration:
  Scan Interval: 3600s
  Sync Interval: 300s
  Max Concurrent: 3
```

### 3. Manual Configuration (Optional)

```bash
# Configure specific paths
python cli.py auto-sync-config \
  --path ~/my-projects \
  --path /opt/workspace \
  --exclude test-data \
  --priority-languages python javascript \
  --scan-interval 1800

# Or use environment variables
export AUTO_SYNC_PATHS=/home/user/projects,/opt/repos
export AUTO_SYNC_PRIORITY_LANGUAGES=python,javascript,go
```

### 4. View Active Paths

```bash
python cli.py auto-sync-paths

# Output:
{
  "configured_paths": [],
  "claude_code_paths": [
    "/home/user/current-project",
    "/home/user/other-project"
  ],
  "active_paths": [
    "/home/user/current-project",
    "/home/user/other-project"
  ],
  "source": "claude_code"
}
```

### 5. Manual Operations

```bash
# Trigger immediate scan
python cli.py auto-sync-scan

# Pause auto-sync (via MCP tool in Claude)
# Resume auto-sync (via MCP tool in Claude)
```

## Configuration Options

### Environment Variables

```bash
# Core Settings
AUTO_SYNC_ENABLED=true              # Enable/disable auto-sync
AUTO_SYNC_ON_STARTUP=true          # Scan on server start

# Path Configuration (optional - uses Claude Code paths if not set)
AUTO_SYNC_PATHS=/path1,/path2      # Paths to scan
AUTO_SYNC_EXCLUDE=node_modules,build # Exclude patterns

# Timing
AUTO_SYNC_SCAN_INTERVAL=3600       # Scan for new repos (seconds)
AUTO_SYNC_INTERVAL=300             # Process sync queue (seconds)

# Behavior
AUTO_SYNC_MAX_CONCURRENT=3         # Parallel sync operations
AUTO_SYNC_PRIORITY_LANGUAGES=python,javascript
AUTO_SYNC_SIZE_THRESHOLD=104857600 # Skip large repos (bytes)
AUTO_SYNC_AUTO_WATCH=true          # Enable file watching
```

## How It Works

1. **Path Detection**:
   - First checks `AUTO_SYNC_PATHS` environment variable
   - If not set, uses Claude Code's permitted directories
   - Falls back to current working directory if it's a repository

2. **Repository Discovery**:
   - Scans paths recursively (respecting depth limits)
   - Identifies repos by markers (.git, package.json, etc.)
   - Detects primary language
   - Filters by size and file count

3. **Smart Prioritization**:
   - Priority languages sync first
   - Smaller repositories before larger ones
   - Recently modified repos get preference

4. **Continuous Sync**:
   - Initial full sync for new repositories
   - Incremental updates for existing ones
   - Automatic file watching after successful sync

## Troubleshooting

### No Repositories Found

```bash
# Check which paths are being used
python cli.py auto-sync-paths

# Verify Claude Code permissions
echo $CLAUDE_CODE_ALLOWED_PATHS

# Manually set paths if needed
export AUTO_SYNC_PATHS=/your/code/directory
```

### Sync Not Starting

```bash
# Check if enabled
python cli.py auto-sync-status

# Enable if needed
export AUTO_SYNC_ENABLED=true

# Restart server
```

### Large Repositories Skipped

```bash
# Increase size threshold (default 100MB)
export AUTO_SYNC_SIZE_THRESHOLD=524288000  # 500MB
```

## Best Practices

1. **Let Claude Code Decide**: Don't set `AUTO_SYNC_PATHS` unless necessary
2. **Exclude Wisely**: Add build artifacts and dependencies to exclude list
3. **Monitor Resources**: Use `system-health` to check resource usage
4. **Prioritize Languages**: Set your primary languages for faster initial sync

## Integration with Claude Desktop

When using with Claude Desktop, the auto-sync system automatically:
- Detects directories Claude has access to
- Syncs only permitted repositories
- Updates the index as you work
- Provides semantic search across all your code

No configuration needed - it just works!