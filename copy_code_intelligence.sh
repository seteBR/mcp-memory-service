#!/bin/bash
# Script to copy code intelligence modules from the complete implementation

SOURCE_DIR="/mnt/c/Users/silva/OneDrive/OLDFiles/Documentos/Projects/ConnectivityTestingTool/mcp-code-intelligence/src/mcp_memory_service"
DEST_DIR="/home/felipe/mcp-memory-service/src/mcp_memory_service"

echo "Copying code intelligence modules..."

# Copy models/code.py
echo "Copying models/code.py..."
cp -v "$SOURCE_DIR/models/code.py" "$DEST_DIR/models/"

# Copy entire code_intelligence directory (excluding what we already have)
echo "Copying code_intelligence modules..."
cp -r "$SOURCE_DIR/code_intelligence/batch" "$DEST_DIR/code_intelligence/"
cp -r "$SOURCE_DIR/code_intelligence/cache" "$DEST_DIR/code_intelligence/"
cp -r "$SOURCE_DIR/code_intelligence/chunker" "$DEST_DIR/code_intelligence/"
cp -r "$SOURCE_DIR/code_intelligence/monitoring" "$DEST_DIR/code_intelligence/"
cp -r "$SOURCE_DIR/code_intelligence/security" "$DEST_DIR/code_intelligence/"
cp -r "$SOURCE_DIR/code_intelligence/tools" "$DEST_DIR/code_intelligence/"
cp "$SOURCE_DIR/code_intelligence/__init__.py" "$DEST_DIR/code_intelligence/"

# Copy missing sync files
echo "Copying additional sync files..."
cp -v "$SOURCE_DIR/code_intelligence/sync/file_watcher.py" "$DEST_DIR/code_intelligence/sync/"
cp -v "$SOURCE_DIR/code_intelligence/sync/repository_sync.py" "$DEST_DIR/code_intelligence/sync/"
cp -v "$SOURCE_DIR/code_intelligence/sync/__init__.py" "$DEST_DIR/code_intelligence/sync/"

# Copy performance directory
echo "Copying performance modules..."
cp -r "$SOURCE_DIR/performance" "$DEST_DIR/"

# Copy security directory
echo "Copying security modules..."
cp -r "$SOURCE_DIR/security" "$DEST_DIR/"

# Copy CLI directory if needed
echo "Copying CLI modules..."
cp -r "$SOURCE_DIR/cli" "$DEST_DIR/" 2>/dev/null || true

# Copy the cli.py if it's different
echo "Copying cli.py..."
cp -v "$SOURCE_DIR/cli.py" "$DEST_DIR/"

# Copy requirements for code intelligence
echo "Copying requirements file..."
cp -v "/mnt/c/Users/silva/OneDrive/OLDFiles/Documentos/Projects/ConnectivityTestingTool/mcp-code-intelligence/requirements-code-intelligence.txt" "/home/felipe/mcp-memory-service/"

echo "Done! All code intelligence modules have been copied."
echo ""
echo "Next steps:"
echo "1. Install additional dependencies: pip install -r requirements-code-intelligence.txt"
echo "2. Set environment variable: export ENABLE_CODE_INTELLIGENCE=true"
echo "3. Run the server: uv run memory"