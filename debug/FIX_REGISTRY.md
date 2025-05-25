# MCP Memory Service - Fix Registry

This registry tracks all fixes applied to the MCP Memory Service to resolve issues and improve functionality.

## Fix Index

| Fix ID | Date | Issue | File(s) Modified | Status |
|--------|------|-------|------------------|--------|
| 001 | 2025-01-24 | AsyncIO Create Task Error in Enhanced Server | `src/mcp_memory_service/enhanced_server.py` | Applied |

## Fix Details

### Fix 001: AsyncIO Create Task Error
- **Problem**: Server failed to start due to `asyncio.create_task()` being called before event loop
- **Solution**: Deferred task creation to after event loop initialization
- **Details**: [fix_001_asyncio_create_task.md](./fix_001_asyncio_create_task.md)

## How to Use This Registry

1. When encountering an issue, check this registry first
2. Each fix has a detailed markdown file with:
   - Issue description
   - Root cause analysis
   - Solution implementation
   - Files modified
   - Testing notes
3. Fixes are numbered sequentially (001, 002, etc.)
4. Status can be: Applied, Testing, Reverted

## Adding New Fixes

When documenting a new fix:
1. Create a new file: `fix_XXX_short_description.md`
2. Add an entry to this registry
3. Include:
   - Clear problem statement
   - Root cause analysis
   - Solution with code snippets
   - List of modified files
   - Testing/verification steps