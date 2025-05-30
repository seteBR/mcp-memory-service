# MCP Memory Service Troubleshooting Guide

This guide covers common issues and their solutions when working with the MCP Memory Service.

## Code Intelligence Troubleshooting

### Code Intelligence Not Working

#### Symptoms
- Missing code intelligence tools in Claude Desktop (search_code, analyze_security, etc.)
- Basic memory operations work but no code analysis features
- "Code intelligence not enabled" messages

#### Solutions

1. **Verify Enhanced Server is Used**
   ```json
   // CORRECT - uses enhanced server
   "args": ["run", "mcp_memory_service.enhanced_server"]
   
   // INCORRECT - uses basic server without code intelligence
   "args": ["run", "memory"]
   ```

2. **Check Environment Variable**
   ```json
   "env": {
     "ENABLE_CODE_INTELLIGENCE": "true"  // Must be string "true", not boolean
   }
   ```

3. **Restart Claude Desktop Completely**
   - Close Claude Desktop
   - Check system tray and end any Claude processes
   - Start Claude Desktop fresh

4. **Verify Installation**
   ```bash
   # In your mcp-memory-service directory
   python -c "from mcp_memory_service.enhanced_server import EnhancedMemoryServer; print('Enhanced server available')"
   ```

### Auto-Sync Not Working

#### Symptoms
- Repositories not being discovered automatically
- File changes not being detected
- Auto-sync status shows as disabled

#### Solutions

1. **Enable Auto-Sync in Configuration**
   ```json
   "env": {
     "AUTO_SYNC_ENABLED": "true",
     "ENABLE_FILE_WATCHING": "true",
     "AUTO_SYNC_PATHS": "/path/to/projects,/another/path"
   }
   ```

2. **Check Permissions**
   - Ensure the service has read access to configured paths
   - For WSL, verify Windows filesystem access

3. **Verify Background Tasks**
   - Auto-sync starts 5 seconds after server initialization
   - Check logs for auto-sync startup messages

## Common Installation Issues

[Content from installation.md's troubleshooting section - already well documented]

## MCP Protocol Issues

### Method Not Found Errors

If you're seeing "Method not found" errors or JSON error popups in Claude Desktop:

#### Symptoms
- "Method not found" errors in logs
- JSON error popups in Claude Desktop
- Connection issues between Claude Desktop and the memory service

#### Solution
1. Ensure you have the latest version of the MCP Memory Service
2. Verify your server implements all required MCP protocol methods:
   - resources/list
   - resources/read
   - resource_templates/list
3. Update your Claude Desktop configuration using the provided template

[Additional content from MCP_PROTOCOL_FIX.md]

## Windows-Specific Issues

[Content from WINDOWS_JSON_FIX.md and windows-specific sections]

## Performance Optimization

### Memory Issues
[Content from installation.md's performance section]

### Acceleration Issues
[Content from installation.md's acceleration section]

## Debugging Tools

[Content from installation.md's debugging section]

## Getting Help

[Content from installation.md's help section]
