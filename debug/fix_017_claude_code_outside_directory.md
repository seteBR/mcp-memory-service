# Fix 017: Claude Code Outside Directory Issue

## Problem
When running Claude Code from a directory outside the MCP memory service directory (e.g., `/mnt/c/Users/silva/OneDrive/OLDFiles/Documentos/Projects/sbtracker`), the memory MCP server fails to connect with error: "MCP error -32000: Connection closed".

## Root Cause
1. The `claude_code_config.json` was using a relative path for the autostart script
2. When Claude Code runs from a different directory, it cannot find `claude_code_autostart.py` 
3. The process fails immediately, causing the connection error

## Solution
1. Updated `claude_code_autostart.py` to:
   - Store and log the original working directory
   - Set proper environment variables for PYTHONPATH
   - Run the subprocess with explicit environment

2. Updated `claude_code_config.json` to use absolute path:
   ```json
   {
       "mcpServers": {
           "memory": {
               "command": "python3",
               "args": ["/home/felipe/mcp-memory-service/claude_code_autostart.py"],
               "cwd": "/home/felipe/mcp-memory-service"
           }
       }
   }
   ```

3. Updated `memory_wrapper_uv.py` to:
   - Check for MCP_MEMORY_SERVICE_DIR environment variable
   - Use the correct directory when running with UV

## Testing
Created test scripts to verify:
- `test_outside_directory.py` - Tests running from different directory
- `test_outside_directory_verbose.py` - Verbose output for debugging
- `test_claude_code_simulation.py` - Simulates Claude Code startup

All tests pass successfully.

## Key Changes

### claude_code_autostart.py
- No longer changes working directory with `os.chdir()`
- Stores original working directory for logging
- Sets PYTHONPATH and MCP_MEMORY_SERVICE_DIR environment variables

### claude_code_config.json
- Uses absolute path for the autostart script
- Maintains the cwd setting for the subprocess

### memory_wrapper_uv.py
- Respects MCP_MEMORY_SERVICE_DIR environment variable
- Properly handles running from different directories

## Verification
To verify the fix works:
1. Navigate to any directory outside mcp-memory-service
2. Run `claude` command
3. Check MCP server status with `/mcp` command
4. Memory server should show as "connected" instead of "failed"

## Related Issues
- This fixes the issue where Claude Code could only work when started from within the mcp-memory-service directory
- Enables true system-wide usage of the memory MCP server
- Maintains compatibility with existing setups

## Status
✅ Fixed and tested