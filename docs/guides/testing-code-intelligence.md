# Testing Code Intelligence Integration with Claude Desktop

This guide provides comprehensive instructions for testing the Code Intelligence features before merging the PR.

## Prerequisites

1. **Install Dependencies**
   ```bash
   pip install -r requirements-code-intelligence.txt
   ```

2. **Set Environment Variables**
   ```bash
   export ENABLE_CODE_INTELLIGENCE=true
   export ENABLE_FILE_WATCHING=true
   export CODE_INTELLIGENCE_WORKERS=4
   ```

## Testing Steps

### 1. Basic Server Test

Test that the enhanced server loads correctly:

```bash
# Set environment and run server
export ENABLE_CODE_INTELLIGENCE=true
python -m mcp_memory_service.server
```

Expected output should include:
- `Code Intelligence: Enabled` in the diagnostics
- `Code Intelligence features enabled - using EnhancedMemoryServer` in the logs

### 2. Claude Desktop Configuration

Add this configuration to your Claude Desktop settings:

```json
{
  "memory": {
    "command": "uv",
    "args": [
      "--directory",
      "/path/to/mcp-memory-service",
      "run",
      "memory"
    ],
    "env": {
      "MCP_MEMORY_CHROMA_PATH": "$HOME/.local/share/mcp-memory/chroma_db",
      "MCP_MEMORY_BACKUPS_PATH": "$HOME/.local/share/mcp-memory/backups",
      "ENABLE_CODE_INTELLIGENCE": "true",
      "CODE_INTELLIGENCE_WORKERS": "4",
      "CODE_INTELLIGENCE_CACHE_SIZE": "1000",
      "CODE_INTELLIGENCE_LANGUAGES": "python,javascript,typescript,go,rust,java,cpp,c",
      "ENABLE_FILE_WATCHING": "true",
      "AUTO_SYNC_ENABLED": "true"
    }
  }
}
```

### 3. Test MCP Tools in Claude Desktop

Once configured, restart Claude Desktop and test these commands:

#### Memory Tools (should work as before):
- "Remember that the project uses Python 3.12"
- "What do you remember about the project?"
- "Search your memory for Python"

#### Code Intelligence Tools (new):
- "Sync the repository at /path/to/your/project"
- "Search for authentication functions in the codebase"
- "Analyze security vulnerabilities in the repository"
- "Show code statistics for the project"

### 4. CLI Testing

Test the CLI interface directly:

```bash
# Analyze a repository
python -m mcp_memory_service.cli batch-analyze /path/to/repo repo-name

# Search code
python -m mcp_memory_service.cli search "class Database" --repository repo-name

# Get statistics
python -m mcp_memory_service.cli stats --repository repo-name
```

### 5. Integration Test Script

Run the provided test script:

```bash
python test_enhanced_server.py
```

This should show:
- ✅ Server instance created
- ✅ Server initialized
- ✅ Found X tools (should include both memory and code tools)
- ✅ Memory stored
- ✅ Repository sync available

### 6. Verify Features

Check that these features work:

1. **Repository Synchronization**
   - Ingest a code repository
   - Verify chunks are created
   - Check incremental updates work

2. **Code Search**
   - Search for functions by name
   - Search for patterns
   - Filter by language/repository

3. **Security Analysis**
   - Run security scan on repository
   - Check vulnerability detection
   - Verify severity filtering

4. **Monitoring**
   - Check metrics are collected
   - Verify performance tracking
   - Review system health

## Troubleshooting

### Server doesn't show "Code Intelligence: Enabled"

1. Check environment variable:
   ```bash
   echo $ENABLE_CODE_INTELLIGENCE
   ```

2. Verify the server.py has the code intelligence check:
   ```python
   if enable_code_intelligence:
       from .enhanced_server import EnhancedMemoryServer
       memory_server = EnhancedMemoryServer(...)
   ```

### Import errors

Ensure all modules are present:
```bash
ls -la src/mcp_memory_service/code_intelligence/
ls -la src/mcp_memory_service/models/code.py
ls -la src/mcp_memory_service/performance/
```

### Claude Desktop doesn't show new tools

1. Restart Claude Desktop after configuration changes
2. Check Claude Desktop logs for errors
3. Verify the server is running with code intelligence enabled

## Expected MCP Tools

With code intelligence enabled, you should see these additional tools:

- `ingest_code_file` - Parse and store code files
- `search_code` - Semantic code search
- `get_code_stats` - Repository statistics
- `analyze_security` - Security vulnerability analysis
- `sync_repository` - Full repository synchronization
- `list_repositories` - List synchronized repositories
- `get_repository_status` - Repository sync status
- `batch_analyze_repository` - Batch analysis with progress
- `get_batch_analysis_report` - Retrieve analysis reports

## Performance Expectations

- File processing: 25-50 files/second
- Search latency: < 100ms
- Memory usage: ~1.5MB per 1000 code chunks
- Initial repository sync: Depends on size (1000 files ≈ 30-60 seconds)

## Next Steps

After successful testing:
1. Merge the PR
2. Update main documentation
3. Create user guides for code intelligence features
4. Set up monitoring dashboards