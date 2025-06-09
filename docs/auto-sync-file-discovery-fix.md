# Auto-Sync File Discovery Fix

## Problem
The auto-sync feature was finding 0 files when syncing repositories because it only supported a limited set of programming language file extensions by default (`.py`, `.js`, `.ts`, `.go`, `.rs`, etc.).

## Root Cause
1. The `ChunkerFactory` only registered chunkers for specific programming languages
2. The file scanner in `async_repository_sync.py` only included files with extensions returned by `ChunkerFactory.get_supported_extensions()`
3. Many common file types were excluded (`.md`, `.json`, `.yaml`, `.txt`, `.html`, `.css`, etc.)

## Solution
1. Created an `extended_factory.py` module that registers additional file types using the `GenericChunker`
2. Modified `async_repository_sync.py` to:
   - Import and initialize the extended file support
   - Add better logging to show why files are excluded
   - Handle files without extensions (like `Dockerfile`, `Makefile`)
   - Improve directory exclusion list

## Changes Made

### 1. New File: `src/mcp_memory_service/code_intelligence/chunker/extended_factory.py`
- Registers support for 40+ additional file types
- Uses `GenericChunker` for non-language-specific files
- Includes documentation, configuration, web, shell, and data files

### 2. Modified: `src/mcp_memory_service/code_intelligence/sync/async_repository_sync.py`
- Added import for extended factory initialization
- Enhanced logging to show scan statistics
- Added support for files without extensions
- Expanded excluded directory list
- Added detailed logging for debugging

## File Types Now Supported
- **Documentation**: `.md`, `.rst`, `.txt`
- **Configuration**: `.json`, `.yaml`, `.yml`, `.toml`, `.ini`, `.cfg`, `.conf`
- **Web**: `.html`, `.xml`, `.css`
- **Shell**: `.sh`, `.bash`, `.bat`, `.ps1`
- **Languages**: `.java`, `.c`, `.cpp`, `.h`, `.cs`, `.rb`, `.php`, `.swift`, `.kt`, `.scala`, `.r`, `.sql`
- **Build**: `Dockerfile`, `.dockerfile`
- And many more...

## Usage
The extended file support is automatically initialized when the async repository sync is imported. No configuration changes are needed.

## Testing
Use the `scripts/test_extended_scanning.py` script to verify file discovery is working correctly:

```bash
python scripts/test_extended_scanning.py
```

This will show:
- Number of supported extensions
- Files found during scanning
- File type distribution
- Example files discovered