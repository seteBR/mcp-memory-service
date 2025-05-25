# Fix 005: UV Path Issue in Claude Code

## Issue
The memory MCP server was failing to start because `uv` was not in the global PATH. Claude Code couldn't find the `uv` command when trying to execute the memory server.

## Root Cause
- `uv` was only installed in the project's virtual environment
- Claude Code doesn't activate the virtual environment before running MCP servers
- The global PATH didn't include `uv`

## Solution
1. Installed `uv` globally using the official installer:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Added `~/.local/bin` to PATH in `.bashrc`:
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

3. Now `uv` is available globally at `/home/felipe/.local/bin/uv`

## Verification
```bash
$ /home/felipe/.local/bin/uv --version
uv 0.7.8

$ /home/felipe/.local/bin/uv run memory --help
# Shows help output successfully
```

## Next Steps
- Restart Claude Code to pick up the new PATH
- Or update the Claude Desktop config to use the full path to uv:
  ```json
  "command": "/home/felipe/.local/bin/uv"
  ```

## Date: 2025-01-24