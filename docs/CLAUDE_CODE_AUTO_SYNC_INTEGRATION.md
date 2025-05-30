# Claude Code Integration for Auto-Sync

## Overview

The Auto-Sync system has been enhanced to automatically detect and use Claude Code's permitted directories when `AUTO_SYNC_PATHS` is not explicitly configured. This provides a zero-configuration experience for Claude Code users.

## How It Works

### Path Detection Priority

The system checks for paths in the following order:

1. **Explicitly Configured Paths** (highest priority)
   - Set via `AUTO_SYNC_PATHS` environment variable
   - Example: `AUTO_SYNC_PATHS=/home/user/projects,/opt/workspace`

2. **MCP Context from Claude Code**
   - Passed during MCP server initialization
   - Contains `allowed_paths` array

3. **Claude Code Environment Variable**
   - `CLAUDE_CODE_ALLOWED_PATHS` set by Claude Code
   - Comma-separated list of permitted directories

4. **Current Working Directory**
   - If CWD is a code repository (has .git, package.json, etc.)
   - Useful when Claude Code is opened in a specific project

5. **Claude Code Configuration Files**
   - Checks: `~/.claude/config.json`, `./.claude/config.json`
   - Looks for `allowed_paths` field

6. **Project Root Discovery**
   - Walks up from CWD to find project roots
   - Also checks sibling directories for related projects

### Implementation Details

```python
async def _get_claude_code_permitted_paths(self) -> List[str]:
    """
    Get permitted paths from Claude Code's permission system.
    
    Detection methods in priority order:
    1. MCP context allowed_paths
    2. CLAUDE_CODE_ALLOWED_PATHS environment variable
    3. Current working directory (if it's a repository)
    4. Claude Code config files
    5. Project root discovery
    """
```

### Configuration Examples

#### Zero Configuration (Recommended)
```bash
# Just enable auto-sync - paths will be auto-detected
export AUTO_SYNC_ENABLED=true

# The system will automatically use Claude Code's permitted directories
```

#### With Explicit Paths
```bash
# Override auto-detection with specific paths
export AUTO_SYNC_ENABLED=true
export AUTO_SYNC_PATHS=/my/projects,/shared/repos
```

#### Mixed Mode
```bash
# Use Claude Code paths but exclude certain patterns
export AUTO_SYNC_ENABLED=true
export AUTO_SYNC_EXCLUDE=experimental,archive,backup
```

### Claude Code Environment Setup

When Claude Code launches the MCP server, it can provide paths via:

1. **Environment Variable**
   ```bash
   CLAUDE_CODE_ALLOWED_PATHS=/home/user/project1,/home/user/project2
   ```

2. **MCP Context**
   ```json
   {
     "allowed_paths": [
       "/home/user/project1",
       "/home/user/project2"
     ]
   }
   ```

3. **Configuration File**
   Create `~/.claude/config.json`:
   ```json
   {
     "allowed_paths": [
       "/home/user/projects",
       "/opt/development"
     ]
   }
   ```

### Checking Active Paths

Use the new MCP tool to see which paths will be used:

```bash
# Via CLI
python cli.py get-auto-sync-paths

# Output:
{
  "configured_paths": [],  // Empty if not explicitly set
  "claude_code_paths": ["/home/user/project1", "/home/user/project2"],
  "active_paths": ["/home/user/project1", "/home/user/project2"],
  "source": "claude_code"  // Shows where paths came from
}
```

### Benefits

1. **Zero Configuration**: Works out of the box with Claude Code
2. **Permission Aware**: Only syncs directories Claude Code can access
3. **Flexible Override**: Can still manually configure if needed
4. **Smart Detection**: Multiple fallback methods ensure paths are found
5. **Project Discovery**: Finds related projects automatically

### Security Considerations

- Only syncs directories explicitly permitted by Claude Code
- Respects Claude Code's security model
- No access beyond what Claude Code already allows
- Explicit configuration always takes precedence

### Troubleshooting

If auto-sync isn't finding your repositories:

1. **Check active paths**:
   ```bash
   python cli.py get-auto-sync-paths
   ```

2. **Verify Claude Code permissions**:
   - Ensure Claude Code has access to the directories
   - Check if `CLAUDE_CODE_ALLOWED_PATHS` is set

3. **Manual override**:
   ```bash
   export AUTO_SYNC_PATHS=/path/to/your/projects
   ```

4. **Enable debug logging**:
   ```bash
   export LOG_LEVEL=DEBUG
   python -m mcp_memory_service.server
   ```

### Integration with Enhanced Server

The enhanced MCP server now accepts an MCP context during initialization:

```python
class EnhancedMCPServer(Server):
    def __init__(self, storage: ChromaStorage, mcp_context: dict = None):
        # ... initialization ...
        
        # Pass context to auto-sync manager
        if mcp_context:
            self.auto_sync_manager._mcp_context = mcp_context
```

This allows Claude Code to pass permitted paths directly to the auto-sync system during server startup.