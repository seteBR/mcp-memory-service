# Fix 004: Server Communication Issue

## Summary
The memory MCP server starts successfully but Claude Desktop cannot communicate with it. The server is waiting for stdio input/output but the connection times out.

## Key Findings

1. **Server Starts Successfully**
   - Prints system diagnostics
   - Initializes ChromaDB and models
   - Reaches stdio server initialization
   - Waits for MCP protocol messages

2. **No Actual Hang**
   - Server is not hanging, it's waiting for input
   - This is expected behavior for an MCP stdio server
   - The issue is communication between Claude Desktop and the server

3. **Environment Issues**
   - Virtual environment mismatch warning (VIRTUAL_ENV vs .venv)
   - Server runs from WSL but Claude Desktop is on Windows
   - Path translation issues between Windows and WSL

## Root Cause
The issue is likely the path configuration in Claude Desktop config:
- Config uses WSL path: `/home/felipe/mcp-memory-service`
- But Claude Desktop on Windows cannot directly execute WSL commands
- Need to use `wsl.exe` wrapper or Windows-compatible paths

## Solution
Update the Claude Desktop configuration to properly invoke WSL commands from Windows:
```json
"memory": {
  "command": "wsl.exe",
  "args": [
    "-e",
    "bash",
    "-c",
    "cd /home/felipe/mcp-memory-service && uv run memory"
  ],
  "env": {
    // ... existing env vars ...
  }
}
```

## Date: 2025-01-24