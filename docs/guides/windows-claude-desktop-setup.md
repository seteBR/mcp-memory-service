# Windows Setup Guide for Claude Desktop with Code Intelligence

This guide specifically covers setting up the MCP Memory Service with Code Intelligence on Windows for use with Claude Desktop.

## Prerequisites

- Windows 10/11
- Claude Desktop installed
- Python 3.8+ (either native Windows or WSL)
- Git

## Installation Options

### Option 1: Using WSL (Recommended)

#### Step 1: Install WSL and Dependencies

```bash
# In PowerShell as Administrator
wsl --install

# Inside WSL
sudo apt update
sudo apt install python3-pip python3-venv git
```

#### Step 2: Clone and Install Memory Service

```bash
# In WSL terminal
cd ~
git clone https://github.com/seteBR/mcp-memory-service.git
cd mcp-memory-service

# Install using the automated script
python3 install.py

# Or use uv (recommended)
pip install uv
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

#### Step 3: Configure Claude Desktop

1. Open the configuration file:
   - Location: `C:\Users\YOUR_USERNAME\AppData\Roaming\Claude\claude_desktop_config.json`
   - You can open it by pressing `Win+R` and typing: `%APPDATA%\Claude\claude_desktop_config.json`

2. Add the memory service configuration:

```json
{
  "mcpServers": {
    "memory": {
      "command": "uv",
      "args": [
        "--directory",
        "/home/YOUR_WSL_USERNAME/mcp-memory-service",
        "run",
        "mcp_memory_service.enhanced_server"
      ],
      "env": {
        "MCP_MEMORY_CHROMA_PATH": "/home/YOUR_WSL_USERNAME/.local/share/mcp-memory/chroma_db",
        "MCP_MEMORY_BACKUPS_PATH": "/home/YOUR_WSL_USERNAME/.local/share/mcp-memory/backups",
        "ENABLE_CODE_INTELLIGENCE": "true",
        "CODE_INTELLIGENCE_WORKERS": "4",
        "CODE_INTELLIGENCE_CACHE_SIZE": "1000",
        "CODE_INTELLIGENCE_LANGUAGES": "python,javascript,typescript,go,rust,java,cpp,c",
        "ENABLE_FILE_WATCHING": "true",
        "AUTO_SYNC_ENABLED": "true"
      }
    }
  }
}
```

### Option 2: Native Windows Installation

#### Step 1: Install Python and Dependencies

```powershell
# Install Python from python.org or Microsoft Store
# Then in PowerShell:
cd C:\Users\YOUR_USERNAME\Documents
git clone https://github.com/seteBR/mcp-memory-service.git
cd mcp-memory-service

# Run Windows-specific installation
python scripts\install_windows.py
```

#### Step 2: Configure Claude Desktop

```json
{
  "mcpServers": {
    "memory": {
      "command": "python",
      "args": [
        "C:\\Users\\YOUR_USERNAME\\Documents\\mcp-memory-service\\memory_wrapper.py"
      ],
      "env": {
        "MCP_MEMORY_CHROMA_PATH": "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\mcp-memory\\chroma_db",
        "MCP_MEMORY_BACKUPS_PATH": "C:\\Users\\YOUR_USERNAME\\AppData\\Local\\mcp-memory\\backups",
        "ENABLE_CODE_INTELLIGENCE": "true",
        "CODE_INTELLIGENCE_WORKERS": "4",
        "ENABLE_FILE_WATCHING": "true"
      }
    }
  }
}
```

## Verifying the Setup

### Step 1: Restart Claude Desktop

1. Completely close Claude Desktop (check system tray)
2. Start Claude Desktop again
3. The memory service should initialize automatically

### Step 2: Check Code Intelligence is Active

In Claude Desktop, you should now have access to these additional tools:
- `search_code` - Semantic code search
- `analyze_security` - Security vulnerability detection
- `sync_repository` - Repository synchronization
- `batch_analyze_repository` - Full repository analysis
- And many more...

### Step 3: Test the Features

Try these commands in Claude:
1. "Analyze the code in C:\MyProject for security issues"
2. "Search for authentication functions in my codebase"
3. "Show me repository statistics"

## Troubleshooting

### Common Issues

#### 1. "Memory service not found" error
- Ensure the paths in your config file are correct
- For WSL paths, use forward slashes: `/home/username/...`
- For Windows paths, use double backslashes: `C:\\Users\\...`

#### 2. "Code intelligence not enabled" 
- Verify `ENABLE_CODE_INTELLIGENCE` is set to `"true"` (as a string, not boolean)
- Ensure you're using `enhanced_server` not just `server`
- Check that the environment variables are in the `env` section

#### 3. WSL-specific issues
- If using WSL paths from Windows, ensure WSL is running
- You might need to use `wsl` as the command:
  ```json
  "command": "wsl",
  "args": ["--", "uv", "--directory", "/home/username/mcp-memory-service", "run", "mcp_memory_service.enhanced_server"]
  ```

#### 4. Permission errors
- Ensure the ChromaDB and backup directories exist and are writable
- For WSL, create directories: `mkdir -p ~/.local/share/mcp-memory/{chroma_db,backups}`

### Checking Logs

To debug issues:

1. Enable debug logging by adding to the env section:
   ```json
   "LOG_LEVEL": "DEBUG"
   ```

2. Check Claude Desktop logs:
   - Windows: `%APPDATA%\Claude\logs\`

3. Test the server directly in terminal:
   ```bash
   # WSL or PowerShell
   cd /path/to/mcp-memory-service
   ENABLE_CODE_INTELLIGENCE=true python -m mcp_memory_service.enhanced_server
   ```

## Performance Tips

### For Large Codebases

1. Adjust worker count based on your CPU:
   ```json
   "CODE_INTELLIGENCE_WORKERS": "8"  // For 8+ core CPUs
   ```

2. Increase cache size if you have RAM:
   ```json
   "CODE_INTELLIGENCE_CACHE_SIZE": "2000"
   ```

3. Limit languages to what you need:
   ```json
   "CODE_INTELLIGENCE_LANGUAGES": "python,javascript,typescript"
   ```

### Resource Management

Monitor resource usage and adjust:
- Reduce workers if CPU usage is too high
- Disable file watching if not needed: `"ENABLE_FILE_WATCHING": "false"`
- Disable auto-sync for manual control: `"AUTO_SYNC_ENABLED": "false"`

## Next Steps

1. **Analyze Your First Repository**: Ask Claude to analyze a local project
2. **Set Up Auto-Sync**: Configure paths for automatic repository discovery
3. **Explore Security Analysis**: Use the security scanning features
4. **Read the Full Guide**: See [Getting Started with Code Intelligence](../code_intelligence/getting_started.md)

## Getting Help

- Check the [Troubleshooting Guide](./troubleshooting.md)
- Review [Code Intelligence Documentation](../code_intelligence/getting_started.md)
- Report issues on [GitHub](https://github.com/seteBR/mcp-memory-service/issues)