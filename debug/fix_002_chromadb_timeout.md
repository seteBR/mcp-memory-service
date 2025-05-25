# Fix 002: ChromaDB Initialization Timeout

## Issue
The memory MCP server is timing out during initialization when code intelligence is enabled. The server hangs after:
- Successfully loading the sentence transformer model
- Initializing ChromaDB
- Making a POST request to posthog telemetry

## Symptoms
- Server prints diagnostics but then hangs
- Claude Desktop shows "connecting..." then fails with 30s timeout
- Manual testing shows server stuck after ChromaDB initialization

## Investigation
1. Server starts successfully without code intelligence
2. With `ENABLE_CODE_INTELLIGENCE=true`, server hangs after:
   - Loading all-mpnet-base-v2 model
   - Creating ChromaDB client
   - Initializing collection
   - Starting MetricsCollector
   - Making posthog telemetry request

## Potential Causes
1. Deadlock in async initialization
2. ChromaDB hanging on network request
3. Issue with metrics collector background task
4. Problem with stdio server initialization

## Date: 2025-01-24