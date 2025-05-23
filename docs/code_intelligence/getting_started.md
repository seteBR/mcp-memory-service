# Getting Started with Code Intelligence

Welcome to the enhanced MCP Memory Service with Code Intelligence! This guide will help you quickly set up and start using the powerful code analysis features.

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- 4GB+ RAM recommended
- Git for repository operations

### Installation

```bash
# Clone the enhanced repository
git clone https://github.com/seteBR/mcp-memory-service.git
cd mcp-memory-service

# Run the installation script (handles platform-specific dependencies)
python install.py

# Verify installation
python cli.py --help
```

The installation script will automatically:
- Detect your system architecture and hardware accelerators
- Install the appropriate PyTorch version for your platform
- Install all required dependencies
- Configure optimal settings for your environment

### Alternative Installation Methods

#### Using Docker
```bash
# Build and run with Docker
docker build -t mcp-code-intelligence .
docker run -v $(pwd):/workspace -p 8000:8000 mcp-code-intelligence
```

#### Manual Installation
```bash
# Install dependencies manually
pip install -r requirements.txt
pip install psutil  # For system monitoring

# Initialize the system
python cli.py batch-analyze ./examples/sample-code test-repo --workers 2
```

## 📝 Basic Usage

### 1. Analyze Your First Repository

Start by analyzing a local repository to see the code intelligence in action:

```bash
# Comprehensive repository analysis
python cli.py batch-analyze ./my-project project-name --workers 4

# Example output:
# 🔄 Starting batch analysis of repository 'project-name'...
# ✅ 156 files processed in 8.2s (19.0 files/sec)
# 📊 892 code chunks created
# 🔒 12 security issues found (2 high, 6 medium, 4 low)
# 📊 Comprehensive analysis report stored in memory.
```

This command will:
- Parse all supported code files in your repository
- Extract semantic code chunks (functions, classes, methods)
- Detect security vulnerabilities
- Store everything in the vector database for searching

### 2. Search Your Code Semantically

Once your code is indexed, you can search using natural language:

```bash
# Find authentication-related code
python cli.py search "user authentication middleware" --repository project-name

# Find database operations
python cli.py search "database connection pool" --repository project-name

# Language-specific search
python cli.py search "async function error handling" --language python
```

Example search results:
```
🔍 Search Results for "user authentication middleware":

1. src/auth/middleware.py:15-45 (Score: 0.89)
   Function: authenticate_user
   Type: function
   
   def authenticate_user(request, token):
       """Middleware for user authentication using JWT tokens"""
       if not token:
           return JsonResponse({'error': 'Token required'}, status=401)
       ...

2. src/middleware/auth.py:78-102 (Score: 0.82)
   Class: AuthenticationMiddleware
   Type: class
   
   class AuthenticationMiddleware:
       """Django middleware for handling user authentication"""
       def __init__(self, get_response):
           self.get_response = get_response
       ...
```

### 3. Enable Real-time Repository Sync

Set up automatic synchronization to keep your code index up-to-date:

```bash
# Enable file watching for automatic updates
python cli.py sync-repository ./my-project project-name

# Check synchronization status
python cli.py repository-status project-name

# List all tracked repositories
python cli.py list-repositories
```

Example sync output:
```
📁 Repository Status: project-name

Path: /home/user/my-project
Total Files: 156
Cached Files: 156
Total Chunks: 892
Last Sync: 2024-05-23 15:30:22
Sync Type: incremental
File Watching: Enabled ✅
```

### 4. Monitor Performance and System Health

Keep track of system performance and usage analytics:

```bash
# View comprehensive metrics summary
python cli.py metrics --type summary

# Check system resource usage
python cli.py system-health --history

# View detailed performance metrics
python cli.py metrics --type performance --hours 24
```

Example metrics output:
```
📊 Code Intelligence Metrics Report (Summary)
Time Range: Last 24 hours

📊 Overview:
  • Total Operations: 45
  • Commands Used: 8
  • Errors: 0
  • Security Issues: 12

🔧 Top Commands:
  • batch-analyze: 5 uses
  • search: 18 uses
  • sync-repository: 3 uses

⚡ Performance:
  • Average Duration: 0.234s
  • Total Processing Time: 10.53s

🔒 Security Issues:
  • HIGH: 2 issues
  • MEDIUM: 6 issues
  • LOW: 4 issues
```

### 5. Generate Analysis Reports

Create comprehensive reports of your repository analysis:

```bash
# Generate markdown report
python cli.py batch-report project-name --format markdown --output analysis-report.md

# Generate JSON report for programmatic access
python cli.py batch-report project-name --format json --output data.json
```

## 🔧 MCP Integration with Claude Desktop

### Configuration

Add the code intelligence server to your Claude Desktop configuration. The configuration file location depends on your operating system:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

#### Standard Configuration (with uv)

```json
{
  "mcpServers": {
    "memory": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/mcp-memory-service",
        "run",
        "mcp_memory_service.enhanced_server"
      ],
      "env": {
        "MCP_MEMORY_CHROMA_PATH": "/path/to/chroma_db",
        "MCP_MEMORY_BACKUPS_PATH": "/path/to/backups",
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

#### Windows with WSL Configuration

For Windows users running the memory service in WSL:

```json
{
  "mcpServers": {
    "memory": {
      "command": "wsl",
      "args": [
        "--",
        "uv",
        "--directory",
        "/home/username/mcp-memory-service",
        "run",
        "mcp_memory_service.enhanced_server"
      ],
      "env": {
        "MCP_MEMORY_CHROMA_PATH": "/home/username/.local/share/mcp-memory/chroma_db",
        "MCP_MEMORY_BACKUPS_PATH": "/home/username/.local/share/mcp-memory/backups",
        "ENABLE_CODE_INTELLIGENCE": "true",
        "CODE_INTELLIGENCE_WORKERS": "4",
        "ENABLE_FILE_WATCHING": "true",
        "AUTO_SYNC_ENABLED": "true"
      }
    }
  }
}
```

#### Direct Python Configuration

If not using uv:

```json
{
  "mcpServers": {
    "memory": {
      "command": "python",
      "args": [
        "-m",
        "mcp_memory_service.enhanced_server"
      ],
      "cwd": "/path/to/mcp-memory-service",
      "env": {
        "MCP_MEMORY_CHROMA_PATH": "/path/to/chroma_db",
        "ENABLE_CODE_INTELLIGENCE": "true",
        "ENABLE_METRICS": "true",
        "ENABLE_FILE_WATCHING": "true"
      }
    }
  }
}
```

### Verifying Code Intelligence is Active

After updating your configuration and restarting Claude Desktop:

1. Check if the enhanced server is running with code intelligence enabled
2. Look for the additional MCP tools in Claude (like `search_code`, `analyze_security`, etc.)
3. Try analyzing a repository to confirm functionality

### Important Notes

- **Enhanced Server Required**: You must use `mcp_memory_service.enhanced_server` (not just `server`) to enable code intelligence features
- **Environment Variable**: `ENABLE_CODE_INTELLIGENCE` must be set to `"true"` (as a string)
- **Restart Required**: Claude Desktop must be completely restarted after configuration changes
- **Backward Compatibility**: The enhanced server maintains 100% backward compatibility with existing memory operations

### Available MCP Tools

Once configured, you'll have access to these tools in Claude:

#### **Code Analysis**
- `ingest_code_file` - Parse and store individual code files
- `search_code` - Semantic search across your codebase
- `get_code_stats` - Repository statistics and insights
- `analyze_security` - Security vulnerability detection

#### **Repository Management**
- `sync_repository` - Synchronize repositories with file watching
- `list_repositories` - View all tracked repositories
- `get_repository_status` - Detailed repository information
- `batch_analyze_repository` - Comprehensive repository analysis

#### **Monitoring & Reports**
- `get_performance_metrics` - Performance and usage analytics
- `get_system_health` - System resource monitoring
- `get_batch_analysis_report` - Generate detailed reports
- `cleanup_metrics` - Database maintenance

## 🐍 Python API Usage

### Basic Code Analysis

```python
import asyncio
from mcp_memory_service.enhanced_server import EnhancedMemoryServer
from mcp_memory_service.code_intelligence.chunker.factory import ChunkerFactory
from mcp_memory_service.security.analyzer import SecurityAnalyzer

async def analyze_code_file(file_path, repository_name):
    # Initialize the enhanced server
    server = EnhancedMemoryServer(enable_code_intelligence=True)
    
    # Get chunker for the file
    factory = ChunkerFactory()
    chunker = factory.get_chunker(file_path)
    
    # Read and chunk the file
    with open(file_path, 'r') as f:
        content = f.read()
    
    chunks = chunker.chunk_content(content, file_path, repository_name)
    
    # Analyze security
    security_analyzer = SecurityAnalyzer()
    security_issues = security_analyzer.analyze_code(content, 'python')
    
    # Store chunks
    for chunk in chunks:
        chunk.repository = repository_name
        chunk.security_issues = security_issues
        memory = chunk.to_memory()
        await server.storage.store(memory)
    
    return chunks, security_issues

# Usage
async def main():
    chunks, issues = await analyze_code_file('src/auth.py', 'my-project')
    print(f"Created {len(chunks)} chunks, found {len(issues)} security issues")

asyncio.run(main())
```

### Batch Processing

```python
from mcp_memory_service.code_intelligence.batch.batch_processor import BatchProcessor

async def batch_analyze_repository(repo_path, repo_name):
    # Initialize batch processor
    server = EnhancedMemoryServer(enable_code_intelligence=True)
    batch_processor = BatchProcessor(storage=server.storage)
    
    # Process repository with progress tracking
    def progress_callback(progress):
        print(f"Progress: {progress.progress_percentage:.1f}% "
              f"({progress.processed_files}/{progress.total_files} files)")
    
    result = await batch_processor.process_repository(
        repository_path=repo_path,
        repository_name=repo_name,
        progress_callback=progress_callback,
        store_results=True
    )
    
    # Generate report
    report = batch_processor.generate_report(result)
    print(report)
    
    return result

# Usage
result = asyncio.run(batch_analyze_repository('./my-project', 'my-project'))
```

### Search and Retrieval

```python
async def search_codebase(query, repository=None, language=None):
    server = EnhancedMemoryServer(enable_code_intelligence=True)
    
    # Search using the enhanced server
    request = {
        "query": query,
        "repository": repository,
        "language": language,
        "n_results": 10
    }
    
    results = await server._handle_search_code(request)
    
    # Parse and display results
    for result in results:
        print(result.text)

# Usage
asyncio.run(search_codebase("authentication middleware", repository="my-project"))
```

## ⚙️ Configuration

### Environment Variables

```bash
# Core settings
export ENABLE_CODE_INTELLIGENCE=true
export ENABLE_FILE_WATCHING=true
export ENABLE_METRICS=true

# Database paths
export MCP_MEMORY_CHROMA_PATH=./chroma_db
export METRICS_DB_PATH=./code_intelligence_metrics.db

# Performance tuning
export MAX_WORKERS=4
export CHUNK_SIZE=100
export CACHE_SIZE=1000

# Monitoring
export METRICS_RETENTION_DAYS=30
export SYSTEM_MONITOR_INTERVAL=30
```

### Configuration File

Create a `config.yaml` file for advanced configuration:

```yaml
code_intelligence:
  enabled: true
  file_watching: true
  max_workers: 4
  
storage:
  vector_db_path: "./chroma_db"
  metrics_db_path: "./metrics.db"
  cache_size: 1000
  
languages:
  python:
    enabled: true
    chunker: "ast"
  javascript:
    enabled: true
    chunker: "regex"
  typescript:
    enabled: true
    chunker: "regex"
  go:
    enabled: true
    chunker: "regex"
  rust:
    enabled: true
    chunker: "regex"
    
security:
  enabled: true
  min_severity: "medium"
  patterns:
    sql_injection: true
    xss: true
    command_injection: true
    path_traversal: true
    
monitoring:
  enabled: true
  retention_days: 30
  system_monitoring: true
  interval_seconds: 30
```

## 🛠️ Supported Languages

The code intelligence system supports the following programming languages:

### **AST-Based Parsing (High Accuracy)**
- **Python** - Functions, classes, methods, decorators

### **Regex-Based Parsing (Good Accuracy)**
- **JavaScript/TypeScript** - Functions, classes, methods, arrow functions
- **Go** - Functions, structs, interfaces, methods
- **Rust** - Functions, structs, enums, traits, impl blocks
- **Java** - Classes, methods, interfaces
- **C/C++** - Functions, classes, structs

### **Generic Support (Basic Parsing)**
- PHP, Ruby, Swift, Kotlin, Scala, C#, Perl, R, MATLAB, Shell scripts, and more

### **Adding New Languages**

```python
from mcp_memory_service.code_intelligence.chunker.base import ChunkerBase
from mcp_memory_service.code_intelligence.chunker.factory import ChunkerFactory

class KotlinChunker(ChunkerBase):
    def __init__(self):
        super().__init__()
        self.supported_extensions = {'.kt', '.kts'}
        self.language_name = "kotlin"
    
    def chunk_content(self, content: str, file_path: str, repository: str = None):
        # Implementation for Kotlin parsing
        pass

# Register the new chunker
factory = ChunkerFactory()
factory.register_chunker("kotlin", KotlinChunker())
```

## 🔒 Security Analysis

### Security Patterns

The system detects common vulnerability patterns:

- **SQL Injection** - String concatenation in queries
- **Cross-Site Scripting** - User input in HTML context
- **Command Injection** - Shell command execution
- **Path Traversal** - File system access vulnerabilities
- **Insecure Cryptography** - Weak algorithms, hardcoded keys
- **Authentication Issues** - Session management problems

### Running Security Analysis

```bash
# Analyze all repositories
python cli.py analyze-security --severity medium

# Focus on specific repository
python cli.py analyze-security --repository my-api --severity high

# Filter by language
python cli.py analyze-security --language python --severity low
```

## 📊 Performance Optimization

### Tips for Large Repositories

1. **Use More Workers**: Increase parallel processing
   ```bash
   python cli.py batch-analyze ./large-repo repo-name --workers 8
   ```

2. **Enable Incremental Sync**: Only process changed files
   ```bash
   python cli.py sync-repository ./large-repo repo-name
   ```

3. **Monitor Resource Usage**: Track system performance
   ```bash
   python cli.py system-health --history
   ```

4. **Optimize Cache Settings**: Adjust cache size for your memory
   ```bash
   export CACHE_SIZE=2000  # Increase for more RAM
   ```

### Memory Management

For memory-constrained environments:

```bash
# Reduce batch size
export CHUNK_SIZE=50

# Reduce worker count
export MAX_WORKERS=2

# Use smaller cache
export CACHE_SIZE=500
```

## 🚦 Troubleshooting

### Common Issues

#### **Installation Problems**
```bash
# Verify PyTorch installation
python -c "import torch; print(torch.__version__)"

# Check system compatibility
python scripts/verify_environment.py

# Re-run installation with force
python install.py --force
```

#### **Memory Issues**
```bash
# Check system resources
python cli.py system-health

# Reduce resource usage
export MAX_WORKERS=2
export CHUNK_SIZE=25
```

#### **Search Not Working**
```bash
# Verify repository is indexed
python cli.py repository-status my-project

# Re-index repository
python cli.py batch-analyze ./my-project my-project --workers 2
```

#### **Metrics Not Showing**
```bash
# Check metrics database
python cli.py metrics --type summary

# Clean up old metrics
python cli.py cleanup-metrics
```

### Debugging

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
python cli.py batch-analyze ./test-repo test --workers 1
```

Check database health:

```bash
# Verify ChromaDB
python -c "from mcp_memory_service.storage.chroma import ChromaMemoryStorage; import asyncio; asyncio.run(ChromaMemoryStorage().check_health())"

# Check metrics database
python cli.py metrics --type summary
```

## 🎯 Next Steps

### Learn More
- [Architecture Overview](../technical/architecture.md) - System design and components
- [Security Analysis Guide](../guides/security_analysis.md) - Vulnerability detection patterns
- [Performance Tuning](../guides/performance_tuning.md) - Optimization strategies
- [API Reference](../api/) - Complete programmatic interface

### Examples and Tutorials
- [Basic Examples](../../examples/basic/) - Common workflows
- [Advanced Integration](../../examples/advanced/) - Complex use cases
- [Custom Chunkers](../../examples/chunkers/) - Adding language support

### Contributing
- [Contributing Guide](../CONTRIBUTING.md) - How to contribute
- [Development Setup](../guides/development.md) - Development environment
- [Testing Guide](../guides/testing.md) - Running and writing tests

---

🎉 **Congratulations!** You now have a powerful code intelligence system up and running. Start by analyzing your first repository and exploring the semantic search capabilities. The system will learn and improve as you use it more.

Happy coding! 🚀