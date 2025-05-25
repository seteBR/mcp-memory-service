# MCP Memory Service - Development Guidelines

This file provides guidance to Claude Code (claude.ai/code) when working with the MCP Memory Service repository.

## Build Commands
- **Development**: `python scripts/run_memory_server.py` (run server)
- **Testing**: `pytest tests/` (all tests), `pytest tests/test_file.py::test_function_name` (single test)
- **Installation**: `python install.py` (cross-platform), `python scripts/install_windows.py` (Windows)
- **Package**: `python -m build` (build distribution)
- **Environment**: `python scripts/verify_environment_enhanced.py` (verify setup)

## Testing
- **Unit tests**: `pytest tests/test_memory_ops.py -v`
- **Integration tests**: `pytest tests/test_semantic_search.py -v`
- **Concurrent access**: `python tests/test_concurrent_access.py`
- **Code intelligence**: `pytest tests/test_code_intelligence.py -v`

## Linting and Code Quality
- **Format**: `black src/ tests/ scripts/` (auto-format)
- **Imports**: `isort src/ tests/ scripts/` (sort imports)
- **Type check**: `mypy src/` (type validation)
- **Lint**: `flake8 src/ tests/` (style checking)
- **Pre-commit**: `pre-commit run --all-files` (all checks)

## Code Style Guidelines
- **Python**: Black formatting (88 chars), typed function signatures with type hints
- **Async**: Use async/await for all I/O operations, properly handle exceptions
- **Models**: Use dataclasses with proper type annotations (see `models/memory.py`)
- **Logging**: Use appropriate log levels (DEBUG, INFO, WARNING, ERROR)
- **Docstrings**: Triple-quoted docstrings for all modules, classes, and functions
- **Error handling**: Specific exception types with descriptive messages
- **Naming**: snake_case for functions/variables, PascalCase for classes

## Project Organization
- MCP server implementation using the Model Context Protocol
- ChromaDB for vector storage with sentence-transformers embeddings
- Async operations with proper concurrency control (file locking)
- Code intelligence features in `enhanced_server.py`
- Platform-specific optimizations for Windows, macOS, Linux

### Critical Rules - DO NOT VIOLATE

- **NEVER bypass the file locking mechanism** - always use the proper storage interface
- **NEVER create simplified versions** of existing complex components - fix the actual issue
- **ALWAYS handle platform differences** - test on Windows (WSL), macOS, and Linux
- **ALWAYS use async/await properly** - don't block the event loop
- **ALWAYS check for existing implementations** before creating new utilities
- **ALWAYS run tests** before considering any code changes complete
- **ALWAYS update documentation** when changing public APIs or adding features

### Installation and Platform Support

- **WSL/Linux**: Standard installation with `install.py`
- **Windows**: Use `scripts/install_windows.py` for PyTorch compatibility
- **macOS**: Ensure ARM64 Python for Apple Silicon, Intel works with x86_64
- **Docker**: Multiple compose files for different scenarios
- **UV**: Optional package manager with better performance

### Concurrent Access and Performance

- **File locking**: Automatic cross-platform locking for safe concurrent access
- **Thread pool**: 4 workers by default for ChromaDB operations
- **Retry logic**: Automatic retries with exponential backoff
- **Monitoring**: Use `get_concurrent_access_stats` tool for diagnostics
- **Non-blocking**: All database operations run in thread pool executor

## Memory MCP Usage - Permanent Searchable Memory

The memory MCP tool is available and should be used as permanent searchable memory for this project.

### When to Store Memories
- Store implementation decisions and architectural choices
- Save complex bug fixes and their root causes
- Record performance optimizations and benchmarks
- Keep track of platform-specific workarounds
- Store configuration patterns and deployment notes
- Save integration examples with Claude Code

### Standardized Tagging Strategy
Use consistent tags for better searchability:
- **Project tag**: Always include `mcp-memory-service` as the first tag
- **Component tags**: `storage`, `server`, `utils`, `models`, `code-intelligence`, `docker`
- **Feature tags**: `concurrent-access`, `async`, `locking`, `embeddings`, `search`
- **Platform tags**: `windows`, `macos`, `linux`, `wsl`, `apple-silicon`
- **Issue tags**: `bug-fix`, `performance`, `security`, `compatibility`
- **Type tags**: `implementation`, `pattern`, `configuration`, `troubleshooting`

### Memory Format Templates

#### Bug Fix Format
```
Title: [Component] Issue - Status
PROJECT: mcp-memory-service
PROBLEM: Brief description of the issue
ROOT CAUSE: Technical explanation of why it happened
SOLUTION: Step-by-step implementation details
CODE: Key code snippets or configuration changes
TESTING: How to verify the fix works
RELATED: Reference other memory hashes if applicable
Tags: mcp-memory-service, bug-fix, [component], [platform], [status]
```

#### Feature Implementation Format
```
Title: [Feature Name] - [Status]
PROJECT: mcp-memory-service
PURPOSE: User benefit and use case
IMPLEMENTATION: Technical approach and architecture
API: New MCP tools or methods added
CODE: Key implementations with file paths
TESTING: Test cases and validation steps
DOCS: Documentation updates made
Tags: mcp-memory-service, feature, [component], [status]
```

#### Pattern Format
```
Title: [Pattern Name] - [Use Case]
PROJECT: mcp-memory-service
PATTERN: Description of the pattern
USE CASE: When to apply this pattern
IMPLEMENTATION: Code example with explanation
BENEFITS: Why this pattern is useful
CAVEATS: Things to watch out for
Tags: mcp-memory-service, pattern, [component], [tech]
```

### How to Use Memory MCP

1. **Store information immediately**:
   ```python
   mcp__memory__store_memory(
       content="Title: Concurrent Access Implementation - Completed\nPROJECT: mcp-memory-service\n...",
       metadata={"tags": "mcp-memory-service,feature,concurrent-access,async,completed", "type": "implementation"}
   )
   ```

2. **Retrieve relevant memories**:
   - Semantic search: `mcp__memory__retrieve_memory("chromadb locking concurrent")`
   - Tag search: `mcp__memory__search_by_tag(["mcp-memory-service", "concurrent-access"])`
   - Time search: `mcp__memory__recall_memory("yesterday's async improvements")`

3. **Maintain memory quality**:
   - Use consistent project name in tags and content
   - Update status tags as work progresses
   - Link related memories using hashes
   - Clean duplicates periodically

## Git Workflow and Source Control

### Branching Strategy
- **Main branch**: `main` - stable, production-ready code
- **Feature branches**: `feature/feature-name` - new capabilities
- **Fix branches**: `fix/issue-name` - bug fixes
- **Docs branches**: `docs/description` - documentation updates

### Commit Guidelines

1. **Semantic commit format**:
   ```
   type(scope): Brief description
   
   - Detailed change 1
   - Detailed change 2
   - Fixes #issue-number
   ```
   
   Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`

2. **Examples**:
   ```
   feat(storage): Add concurrent access support with file locking
   
   - Implement ChromaDBLock class with cross-platform support
   - Add retry decorators for transient failures
   - Create thread pool for async operations
   - Add get_concurrent_access_stats MCP tool
   ```

### Working with Code Intelligence Features

When code intelligence is enabled:
- Auto-sync manager requires single instance (process lock)
- File watching uses debouncing for efficiency
- Batch processing for large repositories
- Security analysis integrated with storage

### Common Development Tasks

#### Adding a new MCP tool:
1. Add tool definition in `server.py` or `enhanced_server.py`
2. Implement handler method
3. Add tests in appropriate test file
4. Update documentation
5. Store memory about the new tool

#### Debugging concurrent access:
1. Enable debug logging: `export LOG_LEVEL=DEBUG`
2. Check lock statistics: `get_concurrent_access_stats`
3. Monitor thread pool: Check active workers
4. Review lock file: `.chroma.lock` in data directory

#### Platform-specific testing:
1. **WSL**: Test both Windows and Linux paths
2. **Windows**: Verify PyTorch CUDA support
3. **macOS**: Test both Intel and Apple Silicon
4. **Docker**: Verify volume permissions

### Emergency Procedures

If database corruption occurs:
1. Stop all instances: `pkill -f mcp.*memory`
2. Backup current state: `cp -r ~/.local/share/mcp-memory ~/.local/share/mcp-memory.backup`
3. Run repair: `python scripts/rebuild_database.py`
4. If repair fails, restore from backup: `python scripts/restore_memories.py`

### Security Considerations

- Never store credentials in memories
- ChromaDB files contain embeddings of all stored content
- Lock files should be excluded from version control
- Use appropriate file permissions on data directories

## Troubleshooting Quick Reference

- **Windows installation**: `python scripts/install_windows.py`
- **WSL path issues**: Use `/mnt/c/` for Windows paths
- **Apple Silicon**: Ensure ARM64 Python, set `PYTORCH_ENABLE_MPS_FALLBACK=1`
- **Concurrent access**: Check lock stats, remove stale locks
- **Memory not found**: Verify ChromaDB path, check embeddings model
- **Import errors**: Run `python scripts/fix_sitecustomize.py`

## Project Dependencies
- ChromaDB (0.5.23) - Vector database
- sentence-transformers (>=2.2.2) - Embeddings
- PyTorch (platform-specific) - Neural network backend
- MCP (>=1.0.0, <2.0.0) - Protocol implementation
- asyncio - Async operations
- ThreadPoolExecutor - Concurrent ChromaDB access