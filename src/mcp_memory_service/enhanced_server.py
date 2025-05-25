"""
Enhanced MCP Memory Server with Code Intelligence.
Maintains backward compatibility while adding new features.
"""
import asyncio
import logging
import time
from datetime import datetime
from typing import Any, List, Dict
from mcp import types

from .server import MemoryServer
from .models.code import CodeChunk
from .code_intelligence.chunker.factory import ChunkerFactory
from .code_intelligence.sync.repository_sync import RepositorySync
from .code_intelligence.sync.auto_sync_manager import AutoSyncManager
from .code_intelligence.batch.batch_processor import BatchProcessor
from .code_intelligence.monitoring.metrics_collector import get_metrics_collector, initialize_metrics
from .performance.cache import cache_manager
from .security.analyzer import security_analyzer
from .utils.process_lock import ProcessLock

logger = logging.getLogger(__name__)

class EnhancedMemoryServer(MemoryServer):
    """Enhanced memory server with code intelligence capabilities."""
    
    def __init__(self, enable_code_intelligence: bool = True, enable_file_watching: bool = True, 
                 enable_metrics: bool = True, metrics_db_path: str = "code_intelligence_metrics.db",
                 mcp_context: dict = None):
        self.code_intelligence_enabled = enable_code_intelligence
        self.enable_file_watching = enable_file_watching
        self.enable_metrics = enable_metrics
        self._mcp_context = mcp_context  # Store MCP context from Claude Code
        self._parent_tools = None  # Store parent tools before overriding
        super().__init__()
        
        # Initialize metrics collection if enabled
        if self.enable_metrics:
            self.metrics_collector = initialize_metrics(db_path=metrics_db_path)
            logger.info(f"Metrics collection initialized: {metrics_db_path}")
        else:
            self.metrics_collector = None
        
        # Initialize repository sync and batch processor if code intelligence is enabled
        if self.code_intelligence_enabled:
            self.repository_sync = RepositorySync(
                storage_backend=self.storage,
                enable_file_watching=enable_file_watching
            )
            self.batch_processor = BatchProcessor(storage=self.storage)
            
            # Initialize auto-sync manager
            self.auto_sync_manager = AutoSyncManager(
                repository_sync=self.repository_sync,
                storage_backend=self.storage,
                metrics_collector=self.metrics_collector
            )
            
            # Pass MCP context to auto-sync if available
            if mcp_context:
                self.auto_sync_manager._mcp_context = mcp_context
            
            # Defer lock check to async startup to avoid blocking
            self._auto_sync_lock = None
            self._should_start_auto_sync = None
            self._auto_sync_task = None
        else:
            self.repository_sync = None
            self.batch_processor = None
            self.auto_sync_manager = None
            self._should_start_auto_sync = False
            self._auto_sync_lock = None
            
        logger.info(f"Enhanced Memory Server initialized (code intelligence: {enable_code_intelligence}, file watching: {enable_file_watching}, metrics: {enable_metrics})")
        
        # Override parent's list_tools handler to add our initialization
        self._original_list_tools = None
        self._init_complete = False
    
    def _check_auto_sync_lock(self) -> bool:
        """Check if we should acquire auto-sync lock."""
        try:
            self._auto_sync_lock = ProcessLock("mcp_auto_sync")
            if self._auto_sync_lock.acquire():
                logger.info("Auto-sync lock acquired - will start auto-sync")
                return True
            else:
                logger.info("Another instance is running auto-sync - skipping auto-sync startup")
                return False
        except Exception as e:
            logger.warning(f"Error checking auto-sync lock: {e}")
            return False
    
    async def _start_auto_sync(self):
        """Start auto-sync after server initialization."""
        try:
            await asyncio.sleep(5)  # Wait for server to fully initialize
            
            # Check lock asynchronously
            if not self.auto_sync_manager:
                return
                
            # Check if we should acquire the lock
            loop = asyncio.get_event_loop()
            self._should_start_auto_sync = await loop.run_in_executor(None, self._check_auto_sync_lock)
            
            if self._should_start_auto_sync and self._auto_sync_lock and self.auto_sync_manager:
                logger.info("Starting auto-sync manager...")
                # Add timeout to prevent hanging
                await asyncio.wait_for(self.auto_sync_manager.start(), timeout=30)
                logger.info("Auto-sync manager started successfully")
        except asyncio.TimeoutError:
            logger.error("Auto-sync startup timed out after 30 seconds")
            if self._auto_sync_lock:
                self._auto_sync_lock.release()
        except Exception as e:
            logger.error(f"Error starting auto-sync: {e}")
            if self._auto_sync_lock:
                self._auto_sync_lock.release()
    
    def __del__(self):
        """Cleanup on destruction."""
        if hasattr(self, '_auto_sync_lock') and self._auto_sync_lock:
            try:
                self._auto_sync_lock.release()
            except:
                pass  # Ignore errors during cleanup
    
    def get_parent_tools(self) -> List[types.Tool]:
        """Get the list of tools from parent class."""
        return [
            types.Tool(
                name="store_memory",
                description="""Store new information with optional tags.

                    Accepts two tag formats in metadata:
                    - Array: ["tag1", "tag2"]
                    - String: "tag1,tag2"

                   Examples:
                    # Using array format:
                    {
                        "content": "Memory content",
                        "metadata": {
                            "tags": ["important", "reference"],
                            "type": "note"
                        }
                    }

                    # Using string format(preferred):
                    {
                        "content": "Memory content",
                        "metadata": {
                            "tags": "important,reference",
                            "type": "note"
                        }
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "The memory content to store, such as a fact, note, or piece of information."
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Optional metadata about the memory, including tags and type.",
                            "properties": {
                                "tags": {
                                    "oneOf": [
                                        {"type": "array", "items": {"type": "string"}},
                                        {"type": "string"}
                                    ],
                                    "description": "Tags to categorize the memory. Can be a comma-separated string or an array of strings."
                                },
                                "type": {
                                    "type": "string",
                                    "description": "Optional type or category label for the memory, e.g., 'note', 'fact', 'reminder'."
                                }
                            }
                        }
                    },
                    "required": ["content"]
                }
            ),
            types.Tool(
                name="recall_memory",
                description="""Retrieve memories using natural language time expressions and optional semantic search.
                    
                    Supports various time-related expressions such as:
                    - "yesterday", "last week", "2 days ago"
                    - "last summer", "this month", "last January"
                    - "spring", "winter", "Christmas", "Thanksgiving"
                    - "morning", "evening", "yesterday afternoon"
                    
                    Examples:
                    {
                        "query": "recall what I stored last week"
                    }
                    
                    {
                        "query": "find information about databases from two months ago",
                        "n_results": 5
                    }
                    """,
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural language query specifying the time frame or content to recall, e.g., 'last week', 'yesterday afternoon', or a topic."
                        },
                        "n_results": {
                            "type": "number",
                            "default": 5,
                            "description": "Maximum number of results to return."
                        }
                    },
                    "required": ["query"]
                }
            ),
            types.Tool(
                name="retrieve_memory",
                description="""Find relevant memories based on query.

                    Example:
                    {
                        "query": "find this memory",
                        "n_results": 5
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query to find relevant memories based on content."
                        },
                        "n_results": {
                            "type": "number",
                            "default": 5,
                            "description": "Maximum number of results to return."
                        }
                    },
                    "required": ["query"]
                }
            ),
            types.Tool(
                name="search_by_tag",
                description="""Search memories by tags. Must use array format.
                    Returns memories matching ANY of the specified tags.

                    Example:
                    {
                        "tags": ["important", "reference"]
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tags to search for. Returns memories matching ANY of these tags."
                        }
                    },
                    "required": ["tags"]
                }
            ),
            types.Tool(
                name="delete_memory",
                description="""Delete a specific memory by its hash.

                    Example:
                    {
                        "content_hash": "a1b2c3d4..."
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content_hash": {
                            "type": "string",
                            "description": "Hash of the memory content to delete. Obtainable from memory metadata."
                        }
                    },
                    "required": ["content_hash"]
                }
            ),
            types.Tool(
                name="delete_by_tag",
                description="""Delete all memories with a specific tag.
                    WARNING: Deletes ALL memories containing the specified tag.

                    Example:
                    {
                        "tag": "temporary"
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "tag": {
                            "type": "string",
                            "description": "Tag label. All memories containing this tag will be deleted."
                        }
                    },
                    "required": ["tag"]
                }
            ),
            types.Tool(
                name="cleanup_duplicates",
                description="Find and remove duplicate entries",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            types.Tool(
                name="get_embedding",
                description="""Get raw embedding vector for content.

                    Example:
                    {
                        "content": "text to embed"
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Text content to generate an embedding vector for."
                        }
                    },
                    "required": ["content"]
                }
            ),
            types.Tool(
                name="check_embedding_model",
                description="Check if embedding model is loaded and working",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            types.Tool(
                name="debug_retrieve",
                description="""Retrieve memories with debug information.

                    Example:
                    {
                        "query": "debug this",
                        "n_results": 5,
                        "similarity_threshold": 0.0
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query for debugging retrieval, e.g., a phrase or keyword."
                        },
                        "n_results": {
                            "type": "number",
                            "default": 5,
                            "description": "Maximum number of results to return."
                        },
                        "similarity_threshold": {
                            "type": "number",
                            "default": 0.0,
                            "description": "Minimum similarity score threshold for results (0.0 to 1.0)."
                        }
                    },
                    "required": ["query"]
                }
            ),
            types.Tool(
                name="exact_match_retrieve",
                description="""Retrieve memories using exact content match.

                    Example:
                    {
                        "content": "find exactly this"
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "Exact content string to match against stored memories."
                        }
                    },
                    "required": ["content"]
                }
            ),
            types.Tool(
                name="check_database_health",
                description="Check database health and get statistics",
                inputSchema={
                    "type": "object",
                    "properties": {}
                }
            ),
            types.Tool(
                name="recall_by_timeframe",
                description="""Retrieve memories within a specific timeframe.

                    Example:
                    {
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-31",
                        "n_results": 5
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "format": "date",
                            "description": "Start date (inclusive) in YYYY-MM-DD format."
                        },
                        "end_date": {
                            "type": "string",
                            "format": "date",
                            "description": "End date (inclusive) in YYYY-MM-DD format."
                        },
                        "n_results": {
                            "type": "number",
                            "default": 5,
                            "description": "Maximum number of results to return."
                        }
                    },
                    "required": ["start_date"]
                }
            ),
            types.Tool(
                name="delete_by_timeframe",
                description="""Delete memories within a specific timeframe.
                    Optional tag parameter to filter deletions.

                    Example:
                    {
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-31",
                        "tag": "temporary"
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "start_date": {
                            "type": "string",
                            "format": "date",
                            "description": "Start date (inclusive) in YYYY-MM-DD format."
                        },
                        "end_date": {
                            "type": "string",
                            "format": "date",
                            "description": "End date (inclusive) in YYYY-MM-DD format."
                        },
                        "tag": {
                            "type": "string",
                            "description": "Optional tag to filter deletions. Only memories with this tag will be deleted."
                        }
                    },
                    "required": ["start_date"]
                }
            ),
            types.Tool(
                name="delete_before_date",
                description="""Delete memories before a specific date.
                    Optional tag parameter to filter deletions.

                    Example:
                    {
                        "before_date": "2024-01-01",
                        "tag": "temporary"
                    }""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "before_date": {"type": "string", "format": "date"},
                        "tag": {"type": "string"}
                    },
                    "required": ["before_date"]
                }
            )
        ]
    
    def register_handlers(self):
        """Override to add code intelligence tools while preserving existing ones."""
        # Call parent to register all existing handlers
        super().register_handlers()
        
        # Only add code intelligence tools if enabled
        if not self.code_intelligence_enabled:
            return

        # Override the list_tools handler to include code intelligence tools
        @self.server.list_tools()
        async def handle_list_tools() -> List[types.Tool]:
            # Initialize auto-sync on first call if not done yet
            if not self._init_complete and self.code_intelligence_enabled and self._auto_sync_task is None:
                self._init_complete = True
                self._auto_sync_task = asyncio.create_task(self._start_auto_sync())
            
            # Get all existing tools from parent
            existing_tools = self.get_parent_tools()
            
            # Add code intelligence tools
            code_tools = [
                types.Tool(
                    name="ingest_code_file",
                    description="Parse and store a code file as semantic chunks",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Path to the code file"},
                            "repository": {"type": "string", "description": "Repository name"}
                        },
                        "required": ["file_path", "repository"]
                    }
                ),
                types.Tool(
                    name="search_code",
                    description="Search code chunks using semantic similarity",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "n_results": {"type": "number", "default": 10, "description": "Max results"},
                            "repository": {"type": "string", "description": "Repository filter"},
                            "language": {"type": "string", "description": "Language filter"}
                        },
                        "required": ["query"]
                    }
                ),
                types.Tool(
                    name="get_code_stats",
                    description="Get statistics about stored code chunks",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repository": {"type": "string", "description": "Repository filter"}
                        }
                    }
                ),
                types.Tool(
                    name="analyze_security",
                    description="Analyze code for security vulnerabilities and patterns",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repository": {"type": "string", "description": "Repository filter"},
                            "severity": {"type": "string", "description": "Minimum severity (low, medium, high, critical)"},
                            "include_recommendations": {"type": "boolean", "default": True, "description": "Include security recommendations"}
                        }
                    }
                ),
                types.Tool(
                    name="sync_repository",
                    description="Synchronize a code repository with the intelligence system",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repository_path": {"type": "string", "description": "Path to the repository"},
                            "repository_name": {"type": "string", "description": "Name for the repository"},
                            "incremental": {"type": "boolean", "default": True, "description": "Use incremental sync"},
                            "force_full": {"type": "boolean", "default": False, "description": "Force full resync"}
                        },
                        "required": ["repository_path", "repository_name"]
                    }
                ),
                types.Tool(
                    name="list_repositories",
                    description="List all synchronized repositories and their status",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="get_repository_status",
                    description="Get detailed status for a specific repository",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repository_name": {"type": "string", "description": "Name of the repository"}
                        },
                        "required": ["repository_name"]
                    }
                ),
                types.Tool(
                    name="batch_analyze_repository",
                    description="Perform comprehensive batch analysis of an entire repository with parallel processing",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repository_path": {"type": "string", "description": "Path to the repository"},
                            "repository_name": {"type": "string", "description": "Name for the repository"},
                            "store_results": {"type": "boolean", "default": True, "description": "Store chunks in vector database"},
                            "max_workers": {"type": "number", "default": 4, "description": "Number of parallel workers"},
                            "generate_report": {"type": "boolean", "default": True, "description": "Generate analysis report"}
                        },
                        "required": ["repository_path", "repository_name"]
                    }
                ),
                types.Tool(
                    name="get_batch_analysis_report",
                    description="Generate and retrieve a comprehensive analysis report for a batch processed repository",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "repository_name": {"type": "string", "description": "Name of the repository"},
                            "output_format": {"type": "string", "default": "markdown", "description": "Report format (markdown, json)"}
                        },
                        "required": ["repository_name"]
                    }
                ),
                types.Tool(
                    name="get_performance_metrics",
                    description="Get performance metrics and analytics for code intelligence operations",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "hours": {"type": "number", "default": 24, "description": "Time range in hours for metrics"},
                            "metric_type": {"type": "string", "default": "summary", "description": "Type of metrics (summary, performance, usage, errors, security)"}
                        }
                    }
                ),
                types.Tool(
                    name="get_system_health",
                    description="Get current system health and resource utilization metrics",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "include_history": {"type": "boolean", "default": False, "description": "Include historical system metrics"}
                        }
                    }
                ),
                types.Tool(
                    name="cleanup_metrics",
                    description="Clean up old metrics data beyond retention period",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                # Auto-sync tools
                types.Tool(
                    name="configure_auto_sync",
                    description="Configure automatic repository synchronization settings",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "scan_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Paths to scan for repositories"
                            },
                            "exclude_patterns": {
                                "type": "array", 
                                "items": {"type": "string"},
                                "description": "Patterns to exclude from scanning"
                            },
                            "scan_interval": {
                                "type": "number",
                                "description": "Scan interval in seconds"
                            },
                            "max_concurrent": {
                                "type": "number",
                                "description": "Maximum concurrent sync operations"
                            },
                            "priority_languages": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Languages to prioritize"
                            }
                        }
                    }
                ),
                types.Tool(
                    name="get_auto_sync_status",
                    description="Get current status of automatic repository synchronization",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="trigger_repository_scan",
                    description="Manually trigger a scan for new repositories",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="pause_auto_sync",
                    description="Temporarily pause automatic synchronization",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="resume_auto_sync",
                    description="Resume automatic synchronization",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                ),
                types.Tool(
                    name="get_auto_sync_paths",
                    description="Get the paths that will be used for automatic repository synchronization",
                    inputSchema={
                        "type": "object",
                        "properties": {}
                    }
                )
            ]
            
            return existing_tools + code_tools

        # Override the call_tool handler to route to our new methods
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: dict | None) -> List[types.TextContent]:
            if arguments is None:
                arguments = {}

            # Route to parent methods for existing tools
            if name == "store_memory":
                return await self.handle_store_memory(arguments)
            elif name == "retrieve_memory":
                return await self.handle_retrieve_memory(arguments)
            elif name == "recall_memory":
                return await self.handle_recall_memory(arguments)
            elif name == "search_by_tag":
                return await self.handle_search_by_tag(arguments)
            elif name == "delete_memory":
                return await self.handle_delete_memory(arguments)
            elif name == "delete_by_tag":
                return await self.handle_delete_by_tag(arguments)
            elif name == "cleanup_duplicates":
                return await self.handle_cleanup_duplicates(arguments)
            elif name == "get_embedding":
                return await self.handle_get_embedding(arguments)
            elif name == "check_embedding_model":
                return await self.handle_check_embedding_model(arguments)
            elif name == "debug_retrieve":
                return await self.handle_debug_retrieve(arguments)
            elif name == "exact_match_retrieve":
                return await self.handle_exact_match_retrieve(arguments)
            elif name == "check_database_health":
                return await self.handle_check_database_health(arguments)
            elif name == "recall_by_timeframe":
                return await self.handle_recall_by_timeframe(arguments)
            elif name == "delete_by_timeframe":
                return await self.handle_delete_by_timeframe(arguments)
            elif name == "delete_before_date":
                return await self.handle_delete_before_date(arguments)
            
            # Handle our new code intelligence tools
            elif name == "ingest_code_file":
                return await self._handle_ingest_code_file(arguments)
            elif name == "search_code":
                return await self._handle_search_code(arguments)
            elif name == "get_code_stats":
                return await self._handle_get_code_stats(arguments)
            elif name == "analyze_security":
                return await self._handle_analyze_security(arguments)
            elif name == "sync_repository":
                return await self._handle_sync_repository(arguments)
            elif name == "list_repositories":
                return await self._handle_list_repositories(arguments)
            elif name == "get_repository_status":
                return await self._handle_get_repository_status(arguments)
            elif name == "batch_analyze_repository":
                return await self._handle_batch_analyze_repository(arguments)
            elif name == "get_batch_analysis_report":
                return await self._handle_get_batch_analysis_report(arguments)
            elif name == "get_performance_metrics":
                return await self._handle_get_performance_metrics(arguments)
            elif name == "get_system_health":
                return await self._handle_get_system_health(arguments)
            elif name == "cleanup_metrics":
                return await self._handle_cleanup_metrics(arguments)
            # Auto-sync tools
            elif name == "configure_auto_sync":
                return await self._handle_configure_auto_sync(arguments)
            elif name == "get_auto_sync_status":
                return await self._handle_get_auto_sync_status(arguments)
            elif name == "trigger_repository_scan":
                return await self._handle_trigger_repository_scan(arguments)
            elif name == "pause_auto_sync":
                return await self._handle_pause_auto_sync(arguments)
            elif name == "resume_auto_sync":
                return await self._handle_resume_auto_sync(arguments)
            elif name == "get_auto_sync_paths":
                return await self._handle_get_auto_sync_paths(arguments)
            else:
                raise ValueError(f"Unknown tool: {name}")
    
    async def _handle_ingest_code_file(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle code file ingestion."""
        file_path = arguments.get("file_path")
        language = arguments.get("language")
        repository = arguments.get("repository")
        
        if not file_path:
            return [types.TextContent(type="text", text="Error: file_path is required")]
        
        # Track performance metrics
        start_time = time.time()
        success = False
        error_msg = None
        chunks_created = 0
        
        try:
            # Chunk the file
            factory = ChunkerFactory()
            chunker = factory.get_chunker(file_path)
            
            # Read file content
            import os
            if not os.path.exists(file_path):
                return [types.TextContent(type="text", text=f"Error: File not found: {file_path}")]
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            chunks = chunker.chunk_content(content, file_path, repository or "unknown")
            
            if not chunks:
                return [types.TextContent(type="text", text=f"No code chunks found in {file_path}")]
            
            # Store chunks using existing memory infrastructure
            stored_count = 0
            duplicate_count = 0
            error_count = 0
            
            for chunk in chunks:
                memory = chunk.to_memory()
                success, message = await self.storage.store(memory)
                if success:
                    stored_count += 1
                elif "Duplicate content detected" in message:
                    duplicate_count += 1
                else:
                    error_count += 1
            
            # Create meaningful status message
            status_parts = []
            if stored_count > 0:
                status_parts.append(f"{stored_count} newly stored")
            if duplicate_count > 0:
                status_parts.append(f"{duplicate_count} already existed")
            if error_count > 0:
                status_parts.append(f"{error_count} failed")
            
            status_summary = ", ".join(status_parts) if status_parts else "No chunks processed"
            
            result = [
                f"Processed {len(chunks)} code chunks from {file_path}",
                f"Status: {status_summary}",
                "",
                "Chunks processed:"
            ]
            
            for i, chunk in enumerate(chunks[:5]):  # Show first 5
                result.append(f"  {i+1}. {chunk.chunk_type} at lines {chunk.start_line}-{chunk.end_line}")
            
            if len(chunks) > 5:
                result.append(f"  ... and {len(chunks) - 5} more")
            
            # Invalidate caches for this repository since we added new code
            cache_manager.invalidate_repository(repository or "unknown")
            
            # Record successful metrics
            success = True
            chunks_created = len(chunks)
            
            return [types.TextContent(type="text", text="\n".join(result))]
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error ingesting code file: {error_msg}")
            
            # Record error in metrics
            if self.metrics_collector:
                self.metrics_collector.record_error("ingest_code_file", e, 
                                                   file_path=file_path, 
                                                   repository=repository)
            
            return [types.TextContent(type="text", text=f"Error ingesting file: {error_msg}")]
        finally:
            # Record usage metrics
            if self.metrics_collector:
                duration = time.time() - start_time
                self.metrics_collector.record_usage(
                    command="ingest_code_file",
                    duration=duration,
                    repository=repository,
                    language=language,
                    files_processed=1,
                    chunks_created=chunks_created,
                    success=success,
                    error=error_msg
                )
    
    async def _handle_search_code(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle code search requests with caching."""
        query = arguments.get("query")
        repository = arguments.get("repository")
        language = arguments.get("language")
        n_results = arguments.get("n_results", 10)
        
        if not query:
            return [types.TextContent(type="text", text="Error: query is required")]
        
        try:
            # Check cache first
            cached_results = cache_manager.search_cache.get_search_results(
                query, repository, language, n_results
            )
            
            if cached_results is not None:
                logger.debug(f"Serving cached search results for '{query}'")
                code_results = cached_results
            else:
                # Use the basic query for semantic search
                search_query = query
                
                # Use existing retrieve method
                results = await self.storage.retrieve(search_query, n_results * 2)  # Get more to filter
                
                # Filter for code chunks only
                code_results = []
                for result in results:
                    # Check if this is a code chunk
                    if (result.memory.memory_type == "code_chunk" or
                        (result.memory.metadata and result.memory.metadata.get("code_chunk"))):
                        
                        # Apply additional filters
                        metadata = result.memory.metadata or {}
                        
                        # Repository filter
                        if repository:
                            if metadata.get("repository") != repository:
                                continue
                        
                        # Language filter
                        if language:
                            if metadata.get("language") != language:
                                continue
                        
                        # File pattern filter
                        if arguments.get("file_pattern"):
                            if arguments["file_pattern"] not in metadata.get("file_path", ""):
                                continue
                        
                        code_results.append(result)
                        
                        if len(code_results) >= n_results:
                            break
                
                # Cache the results for future use
                cache_manager.search_cache.cache_search_results(
                    query, code_results, repository, language, n_results
                )
            
            if not code_results:
                return [types.TextContent(type="text", text="No matching code chunks found")]
            
            # Format results
            formatted_results = []
            for i, result in enumerate(code_results, 1):
                memory = result.memory
                metadata = memory.metadata
                
                # Extract code preview
                code = CodeChunk._extract_code_from_content(memory.content)
                code_lines = code.split('\n')[:3]
                
                # Get filename from path
                file_path = metadata.get('file_path', 'unknown')
                filename = file_path.split('/')[-1] if file_path != 'unknown' else 'unknown'
                
                chunk_info = [
                    f"Result {i}:",
                    f"  File: {filename}",
                    f"  Type: {metadata.get('chunk_type', 'unknown')}",
                    f"  Lines: {metadata.get('start_line', '?')}-{metadata.get('end_line', '?')}",
                    f"  Language: {metadata.get('language', 'unknown')}",
                    f"  Repository: {metadata.get('repository', 'unknown')}",
                    f"  Relevance: {result.relevance_score:.2f}",
                    "",
                    "  Code preview:"
                ]
                
                for line in code_lines:
                    chunk_info.append(f"    {line}")
                
                if len(code.split('\n')) > 3:
                    chunk_info.append("    ...")
                
                chunk_info.append("---")
                formatted_results.append("\n".join(chunk_info))
            
            return [types.TextContent(
                type="text",
                text=f"Found {len(code_results)} code chunks:\n\n" + "\n".join(formatted_results)
            )]
            
        except Exception as e:
            logger.error(f"Error searching code: {str(e)}")
            return [types.TextContent(type="text", text=f"Error searching code: {str(e)}")]
    
    async def _handle_get_code_stats(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle code statistics requests with caching."""
        try:
            repository = arguments.get("repository")
            
            # Check cache first
            cached_stats = cache_manager.stats_cache.get_stats(repository)
            if cached_stats is not None:
                logger.debug(f"Serving cached stats for repository '{repository}'")
                # Convert cached stats back to text format
                return [types.TextContent(type="text", text=cached_stats['formatted_text'])]
            
            # Search for all code chunks using semantic search
            results = await self.storage.retrieve("code function class", 1000)  # Get a large number
            
            # Filter for code chunks only
            code_memories = []
            for result in results:
                memory = result.memory
                if (memory.memory_type == "code_chunk" or
                    (memory.metadata and memory.metadata.get("code_chunk"))):
                    
                    # Apply repository filter if specified
                    if repository:
                        metadata = memory.metadata or {}
                        if metadata.get("repository") != repository:
                            continue
                    
                    code_memories.append(memory)
            
            if not code_memories:
                return [types.TextContent(type="text", text="No code chunks found")]
            
            # Compute statistics
            stats = {
                "total_chunks": len(code_memories),
                "languages": {},
                "chunk_types": {},
                "files": set(),
                "repositories": set()
            }
            
            for memory in code_memories:
                metadata = memory.metadata
                
                # Language distribution
                lang = metadata.get("language", "unknown")
                stats["languages"][lang] = stats["languages"].get(lang, 0) + 1
                
                # Chunk type distribution
                chunk_type = metadata.get("chunk_type", "unknown")
                stats["chunk_types"][chunk_type] = stats["chunk_types"].get(chunk_type, 0) + 1
                
                # File and repository tracking
                if metadata.get("file_path"):
                    stats["files"].add(metadata["file_path"])
                if metadata.get("repository"):
                    stats["repositories"].add(metadata["repository"])
            
            stats["total_files"] = len(stats["files"])
            stats["total_repositories"] = len(stats["repositories"])
            
            # Format output
            result = ["Code Repository Statistics:", ""]
            
            if repository:
                result.append(f"Repository: {repository}")
            
            result.extend([
                f"Total Chunks: {stats['total_chunks']}",
                f"Total Files: {stats['total_files']}",
                f"Total Repositories: {stats['total_repositories']}",
                "",
                "Languages:"
            ])
            
            for lang, count in sorted(stats['languages'].items(), key=lambda x: x[1], reverse=True):
                percentage = (count / stats['total_chunks'] * 100) if stats['total_chunks'] > 0 else 0
                result.append(f"  {lang}: {count} ({percentage:.1f}%)")
            
            result.extend(["", "Chunk Types:"])
            for chunk_type, count in sorted(stats['chunk_types'].items(), key=lambda x: x[1], reverse=True):
                result.append(f"  {chunk_type}: {count}")
            
            formatted_text = "\n".join(result)
            
            # Cache the results
            cache_data = {
                'stats': stats,
                'formatted_text': formatted_text
            }
            cache_manager.stats_cache.cache_stats(cache_data, repository)
            
            return [types.TextContent(type="text", text=formatted_text)]
            
        except Exception as e:
            logger.error(f"Error getting code stats: {str(e)}")
            return [types.TextContent(type="text", text=f"Error getting stats: {str(e)}")]
    
    async def _handle_analyze_security(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle security analysis requests."""
        repository = arguments.get("repository")
        severity = arguments.get("severity", "medium")  # low, medium, high, critical
        language = arguments.get("language")
        limit = arguments.get("limit", 50)
        
        try:
            # Search for code chunks with security issues
            # Use the retrieve method to get all chunks, then filter by security issues
            
            search_query = "security vulnerability injection"
            if repository:
                search_query += f" {repository}"
            if language:
                search_query += f" {language}"
            
            # Get more results to filter through
            results = await self.storage.retrieve(search_query, limit * 3)
            
            # Filter for code chunks with security issues
            security_results = []
            severity_levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            min_severity = severity_levels.get(severity.lower(), 2)
            
            for result in results:
                memory = result.memory
                metadata = memory.metadata or {}
                
                # Check if this is a code chunk
                if not (memory.memory_type == "code_chunk" or metadata.get("code_chunk")):
                    continue
                
                # Apply repository filter
                if repository and metadata.get("repository") != repository:
                    continue
                
                # Apply language filter
                if language and metadata.get("language") != language:
                    continue
                
                # Check for security issues in metadata
                security_issues_raw = metadata.get("security_issues")
                if not security_issues_raw:
                    continue
                
                # Parse security issues from JSON string or list
                security_issues = []
                if isinstance(security_issues_raw, str):
                    try:
                        import json
                        security_issues = json.loads(security_issues_raw)
                    except json.JSONDecodeError:
                        # Fallback to comma-separated string format
                        security_issues = [{"type": issue.strip(), "severity": "medium"} 
                                         for issue in security_issues_raw.split(",")]
                elif isinstance(security_issues_raw, list):
                    security_issues = security_issues_raw
                
                if not security_issues:
                    continue
                
                # Filter by severity
                relevant_issues = []
                for issue in security_issues:
                    if isinstance(issue, dict):
                        issue_severity = issue.get("severity", "low").lower()
                        if severity_levels.get(issue_severity, 1) >= min_severity:
                            relevant_issues.append(issue)
                
                if relevant_issues:
                    security_results.append((result, relevant_issues))
                
                if len(security_results) >= limit:
                    break
            
            if not security_results:
                message = f"No security issues found"
                if repository:
                    message += f" in repository '{repository}'"
                if language:
                    message += f" for language '{language}'"
                message += f" with severity >= '{severity}'"
                return [types.TextContent(type="text", text=message)]
            
            # Format results
            result_lines = [
                f"Security Analysis Results (severity >= {severity}):",
                f"Found {len(security_results)} code chunks with security issues",
                ""
            ]
            
            if repository:
                result_lines.append(f"Repository: {repository}")
            if language:
                result_lines.append(f"Language: {language}")
            if repository or language:
                result_lines.append("")
            
            for i, (result, issues) in enumerate(security_results, 1):
                memory = result.memory
                metadata = memory.metadata or {}
                
                # Extract location info
                file_path = metadata.get("file_path", "unknown")
                start_line = metadata.get("start_line", "?")
                end_line = metadata.get("end_line", "?")
                chunk_type = metadata.get("chunk_type", "code")
                
                result_lines.extend([
                    f"{i}. {chunk_type} in {file_path}:{start_line}-{end_line}",
                    f"   Issues found:"
                ])
                
                for issue in issues:
                    if isinstance(issue, dict):
                        issue_type = issue.get("type", "unknown")
                        issue_severity = issue.get("severity", "unknown")
                        issue_desc = issue.get("description", "No description")
                        line_num = issue.get("line", "?")
                        
                        result_lines.append(f"     • {issue_type} ({issue_severity}) at line {line_num}")
                        result_lines.append(f"       {issue_desc}")
                    else:
                        # Handle string format
                        result_lines.append(f"     • {issue}")
                
                # Show a snippet of the problematic code
                code_preview = memory.content[:200] + "..." if len(memory.content) > 200 else memory.content
                result_lines.extend([
                    f"   Code preview:",
                    f"     {code_preview.replace(chr(10), chr(10) + '     ')}",
                    ""
                ])
            
            # Add summary
            issue_counts = {}
            for _, issues in security_results:
                for issue in issues:
                    if isinstance(issue, dict):
                        issue_type = issue.get("type", "unknown")
                        issue_counts[issue_type] = issue_counts.get(issue_type, 0) + 1
            
            if issue_counts:
                result_lines.extend([
                    "Issue Summary:",
                    *[f"  {issue_type}: {count}" for issue_type, count in sorted(issue_counts.items())],
                    ""
                ])
            
            result_lines.append(f"💡 Review these findings and address high-severity issues first.")
            
            return [types.TextContent(type="text", text="\n".join(result_lines))]
            
        except Exception as e:
            logger.error(f"Error analyzing security: {str(e)}")
            return [types.TextContent(type="text", text=f"Error analyzing security: {str(e)}")]
    
    async def _handle_sync_repository(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle repository synchronization requests."""
        repository_path = arguments.get("repository_path")
        repository_name = arguments.get("repository_name")
        incremental = arguments.get("incremental", True)
        force_full = arguments.get("force_full", False)
        
        if not repository_path or not repository_name:
            return [types.TextContent(type="text", text="Error: repository_path and repository_name are required")]
        
        if not self.repository_sync:
            return [types.TextContent(type="text", text="Error: Repository synchronization not enabled")]
        
        try:
            result = await self.repository_sync.sync_repository(
                repository_path=repository_path,
                repository_name=repository_name,
                incremental=incremental,
                force_full=force_full
            )
            
            # Format the result
            result_lines = [
                f"Repository Synchronization: {repository_name}",
                f"Path: {repository_path}",
                f"Sync Type: {'Full' if force_full or not incremental else 'Incremental'}",
                f"Duration: {result.sync_duration:.2f}s",
                "",
                "Files:",
                f"  Total: {result.total_files}",
                f"  Processed: {result.processed_files}",
                f"  New: {result.new_files}",
                f"  Modified: {result.modified_files}",
                f"  Deleted: {result.deleted_files}",
                "",
                "Chunks:",
                f"  Total: {result.total_chunks}",
                f"  New: {result.new_chunks}",
                f"  Updated: {result.updated_chunks}",
                f"  Deleted: {result.deleted_chunks}",
                "",
                f"Success Rate: {result.success_rate:.1f}%"
            ]
            
            if result.errors:
                result_lines.extend([
                    "",
                    "Errors:",
                    *[f"  - {error}" for error in result.errors[:5]]  # Show first 5 errors
                ])
                if len(result.errors) > 5:
                    result_lines.append(f"  ... and {len(result.errors) - 5} more errors")
            
            # Invalidate caches for this repository
            cache_manager.invalidate_repository(repository_name)
            
            return [types.TextContent(type="text", text="\n".join(result_lines))]
            
        except Exception as e:
            logger.error(f"Error syncing repository: {str(e)}")
            return [types.TextContent(type="text", text=f"Error syncing repository: {str(e)}")]
    
    async def _handle_list_repositories(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle repository listing requests."""
        if not self.repository_sync:
            return [types.TextContent(type="text", text="Error: Repository synchronization not enabled")]
        
        try:
            repositories = self.repository_sync.list_repositories()
            
            if not repositories:
                return [types.TextContent(type="text", text="No repositories are currently synchronized")]
            
            result_lines = ["Synchronized Repositories:", ""]
            
            for repo in repositories:
                result_lines.extend([
                    f"📁 {repo['name']}",
                    f"   Path: {repo['path']}",
                    f"   Files: {repo['cached_files']}",
                    f"   Chunks: {repo.get('total_chunks', 0)}",
                    f"   Last Sync: {datetime.fromtimestamp(repo['last_sync']).strftime('%Y-%m-%d %H:%M:%S')}",
                    f"   Watching: {'Yes' if repo['is_watching'] else 'No'}",
                    ""
                ])
            
            return [types.TextContent(type="text", text="\n".join(result_lines))]
            
        except Exception as e:
            logger.error(f"Error listing repositories: {str(e)}")
            return [types.TextContent(type="text", text=f"Error listing repositories: {str(e)}")]
    
    async def _handle_get_repository_status(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle repository status requests."""
        repository_name = arguments.get("repository_name")
        
        if not repository_name:
            return [types.TextContent(type="text", text="Error: repository_name is required")]
        
        if not self.repository_sync:
            return [types.TextContent(type="text", text="Error: Repository synchronization not enabled")]
        
        try:
            status = self.repository_sync.get_repository_status(repository_name)
            
            if not status:
                return [types.TextContent(type="text", text=f"Repository '{repository_name}' not found")]
            
            result_lines = [
                f"Repository Status: {repository_name}",
                "",
                f"Path: {status['path']}",
                f"Total Files: {status.get('total_files', 0)}",
                f"Cached Files: {status['cached_files']}",
                f"Total Chunks: {status.get('total_chunks', 0)}",
                f"Last Sync: {datetime.fromtimestamp(status['last_sync']).strftime('%Y-%m-%d %H:%M:%S')}",
                f"Sync Type: {status.get('sync_type', 'unknown')}",
                f"File Watching: {'Enabled' if status['is_watching'] else 'Disabled'}",
            ]
            
            return [types.TextContent(type="text", text="\n".join(result_lines))]
            
        except Exception as e:
            logger.error(f"Error getting repository status: {str(e)}")
            return [types.TextContent(type="text", text=f"Error getting repository status: {str(e)}")]
    
    async def _handle_batch_analyze_repository(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle batch repository analysis requests."""
        repository_path = arguments.get("repository_path")
        repository_name = arguments.get("repository_name")
        store_results = arguments.get("store_results", True)
        max_workers = arguments.get("max_workers", 4)
        generate_report = arguments.get("generate_report", True)
        
        if not repository_path or not repository_name:
            return [types.TextContent(type="text", text="Error: repository_path and repository_name are required")]
        
        if not self.batch_processor:
            return [types.TextContent(type="text", text="Error: Batch processing not enabled")]
        
        try:
            # Configure batch processor
            self.batch_processor.max_workers = max_workers
            
            # Progress tracking
            progress_updates = []
            
            def progress_callback(progress):
                nonlocal progress_updates
                progress_updates.append({
                    'processed': progress.processed_files,
                    'total': progress.total_files,
                    'percentage': progress.progress_percentage,
                    'rate': progress.processing_rate,
                    'current_file': progress.current_file
                })
            
            # Start batch processing
            logger.info(f"Starting batch analysis of repository: {repository_name}")
            
            # Track performance for batch processing
            batch_start_time = time.time()
            
            if self.metrics_collector:
                with self.metrics_collector.track_performance("batch_analyze_repository", 
                                                            repository=repository_name, 
                                                            workers=max_workers):
                    result = await self.batch_processor.process_repository(
                        repository_path=repository_path,
                        repository_name=repository_name,
                        progress_callback=progress_callback,
                        store_results=store_results
                    )
            else:
                result = await self.batch_processor.process_repository(
                    repository_path=repository_path,
                    repository_name=repository_name,
                    progress_callback=progress_callback,
                    store_results=store_results
                )
            
            # Store result for later report generation if needed
            if not hasattr(self, '_batch_results'):
                self._batch_results = {}
            self._batch_results[repository_name] = result
            
            # Generate summary
            result_lines = [
                f"Batch Analysis Complete: {repository_name}",
                "",
                f"Repository Path: {result.repository_path}",
                f"Total Files: {result.progress.total_files}",
                f"Processed Files: {result.progress.processed_files}",
                f"Failed Files: {result.progress.failed_files}",
                f"Total Chunks: {result.progress.total_chunks}",
                f"Stored Chunks: {result.progress.stored_chunks}",
                f"Security Issues: {result.progress.security_issues}",
                f"Processing Time: {result.progress.elapsed_time:.2f} seconds",
                f"Processing Rate: {result.progress.processing_rate:.1f} files/second",
                "",
                "Language Distribution:"
            ]
            
            # Add language summary
            for language, count in sorted(result.language_summary.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / result.progress.processed_files) * 100 if result.progress.processed_files > 0 else 0
                result_lines.append(f"  {language}: {count} files ({percentage:.1f}%)")
            
            # Add security summary if issues found
            if result.security_summary:
                result_lines.extend(["", "Security Issues by Severity:"])
                for severity, count in sorted(result.security_summary.items()):
                    result_lines.append(f"  {severity.upper()}: {count} issues")
            
            # Add error summary if errors occurred
            if result.error_summary:
                result_lines.extend(["", "Errors:"])
                for error_type, files in result.error_summary.items():
                    result_lines.append(f"  {error_type}: {len(files)} files")
            
            # Add report generation info
            if generate_report:
                result_lines.extend([
                    "",
                    "📊 Comprehensive analysis report stored in memory.",
                    "Use 'get_batch_analysis_report' to retrieve the full report."
                ])
            
            # Record usage metrics for batch processing
            if self.metrics_collector:
                duration = time.time() - batch_start_time
                self.metrics_collector.record_usage(
                    command="batch_analyze_repository",
                    duration=duration,
                    repository=repository_name,
                    files_processed=result.progress.processed_files,
                    chunks_created=result.progress.total_chunks,
                    security_issues=result.progress.security_issues,
                    success=True
                )
                
                # Record security findings
                for file_path, file_result in result.file_results.items():
                    for issue in file_result.get('security_issues', []):
                        self.metrics_collector.record_security_finding(
                            repository=repository_name,
                            language=file_result.get('language', 'unknown'),
                            file_path=file_path,
                            vulnerability_type=issue['type'],
                            severity=issue['severity'],
                            line_number=issue.get('line_number')
                        )
            
            return [types.TextContent(type="text", text="\n".join(result_lines))]
            
        except Exception as e:
            logger.error(f"Error during batch analysis: {str(e)}")
            
            # Record error metrics
            if self.metrics_collector:
                self.metrics_collector.record_error("batch_analyze_repository", e, 
                                                   repository=repository_name)
                duration = time.time() - batch_start_time
                self.metrics_collector.record_usage(
                    command="batch_analyze_repository",
                    duration=duration,
                    repository=repository_name,
                    success=False,
                    error=str(e)
                )
            
            return [types.TextContent(type="text", text=f"Error during batch analysis: {str(e)}")]
    
    async def _handle_get_batch_analysis_report(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle batch analysis report generation requests."""
        repository_name = arguments.get("repository_name")
        output_format = arguments.get("output_format", "markdown")
        
        if not repository_name:
            return [types.TextContent(type="text", text="Error: repository_name is required")]
        
        if not self.batch_processor:
            return [types.TextContent(type="text", text="Error: Batch processing not enabled")]
        
        try:
            # Check if we have stored results
            if not hasattr(self, '_batch_results') or repository_name not in self._batch_results:
                return [types.TextContent(
                    type="text", 
                    text=f"No batch analysis results found for repository '{repository_name}'. "
                         "Please run 'batch_analyze_repository' first."
                )]
            
            result = self._batch_results[repository_name]
            
            if output_format.lower() == "json":
                # Return JSON format
                import json
                report_data = result.to_dict()
                return [types.TextContent(type="text", text=json.dumps(report_data, indent=2))]
            else:
                # Generate markdown report
                report = self.batch_processor.generate_report(result)
                return [types.TextContent(type="text", text=report)]
                
        except Exception as e:
            logger.error(f"Error generating batch analysis report: {str(e)}")
            return [types.TextContent(type="text", text=f"Error generating batch analysis report: {str(e)}")]
    
    async def _handle_get_performance_metrics(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle performance metrics requests."""
        hours = arguments.get("hours", 24)
        metric_type = arguments.get("metric_type", "summary")
        
        if not self.metrics_collector:
            return [types.TextContent(type="text", text="Error: Metrics collection not enabled")]
        
        try:
            if metric_type == "performance":
                data = self.metrics_collector.get_performance_summary(hours)
            elif metric_type == "usage":
                data = self.metrics_collector.get_usage_analytics(hours)
            elif metric_type == "errors":
                data = self.metrics_collector.get_error_report(hours)
            elif metric_type == "security":
                data = self.metrics_collector.get_security_insights(hours)
            else:  # summary
                # Get all metrics types for summary
                performance = self.metrics_collector.get_performance_summary(hours)
                usage = self.metrics_collector.get_usage_analytics(hours)
                errors = self.metrics_collector.get_error_report(hours)
                security = self.metrics_collector.get_security_insights(hours)
                
                data = {
                    "summary": {
                        "time_range_hours": hours,
                        "total_operations": performance.get("overall", {}).get("total_operations", 0),
                        "total_commands": len(usage.get("commands", [])),
                        "total_errors": errors.get("total_errors", 0),
                        "total_security_issues": sum(s.get("count", 0) for s in security.get("by_severity", []))
                    },
                    "performance": performance,
                    "usage": usage,
                    "errors": errors,
                    "security": security
                }
            
            # Format the response
            if "error" in data:
                return [types.TextContent(type="text", text=f"Error: {data['error']}")]
            
            # Generate formatted report
            result_lines = [f"Code Intelligence Metrics Report ({metric_type.title()})"]
            result_lines.append(f"Time Range: Last {hours} hours")
            result_lines.append("")
            
            if metric_type == "summary":
                summary = data["summary"]
                result_lines.extend([
                    "📊 Overview:",
                    f"  • Total Operations: {summary['total_operations']}",
                    f"  • Commands Used: {summary['total_commands']}",
                    f"  • Errors: {summary['total_errors']}",
                    f"  • Security Issues: {summary['total_security_issues']}",
                    ""
                ])
                
                # Top commands
                commands = data["usage"]["commands"][:5]
                if commands:
                    result_lines.extend(["🔧 Top Commands:"])
                    for cmd in commands:
                        result_lines.append(f"  • {cmd['command']}: {cmd['usage_count']} uses")
                    result_lines.append("")
                
                # Performance overview
                perf = data["performance"]["overall"]
                if perf.get("total_operations", 0) > 0:
                    result_lines.extend([
                        "⚡ Performance:",
                        f"  • Average Duration: {perf.get('avg_duration', 0):.3f}s",
                        f"  • Total Processing Time: {perf.get('total_duration', 0):.2f}s",
                        ""
                    ])
                
                # Error summary
                if data["errors"]["total_errors"] > 0:
                    result_lines.extend([
                        "❌ Errors:",
                        f"  • Total: {data['errors']['total_errors']}",
                    ])
                    for error in data["errors"]["by_error_type"][:3]:
                        result_lines.append(f"  • {error['error_type']}: {error['count']}")
                    result_lines.append("")
                
                # Security summary
                security_issues = data["security"]["by_severity"]
                if security_issues:
                    result_lines.extend(["🔒 Security Issues:"])
                    for issue in security_issues:
                        result_lines.append(f"  • {issue['severity'].upper()}: {issue['count']}")
                    result_lines.append("")
            
            elif metric_type == "performance":
                overall = data.get("overall", {})
                result_lines.extend([
                    f"Total Operations: {overall.get('total_operations', 0)}",
                    f"Average Duration: {overall.get('avg_duration', 0):.3f}s",
                    f"Total Processing Time: {overall.get('total_duration', 0):.2f}s",
                    "",
                    "By Operation:"
                ])
                
                for op in data.get("by_operation", [])[:10]:
                    result_lines.append(
                        f"  {op['operation']}: {op['count']} ops, "
                        f"avg {op['avg_duration']:.3f}s"
                    )
            
            elif metric_type == "usage":
                result_lines.extend(["Command Usage:"])
                for cmd in data.get("commands", [])[:10]:
                    result_lines.append(
                        f"  {cmd['command']}: {cmd['usage_count']} uses, "
                        f"success rate {cmd['success_rate']*100:.1f}%"
                    )
                
                result_lines.append("\nLanguage Distribution:")
                for lang in data.get("languages", [])[:10]:
                    result_lines.append(f"  {lang['language']}: {lang['file_count']} files")
            
            elif metric_type == "errors":
                result_lines.extend([
                    f"Total Errors: {data.get('total_errors', 0)}",
                    "",
                    "By Error Type:"
                ])
                for error in data.get("by_error_type", [])[:10]:
                    result_lines.append(f"  {error['error_type']}: {error['count']}")
                
                prob_files = data.get("problematic_files", [])
                if prob_files:
                    result_lines.extend(["", "Most Problematic Files:"])
                    for file_info in prob_files[:5]:
                        result_lines.append(f"  {file_info['file_path']}: {file_info['error_count']} errors")
            
            elif metric_type == "security":
                result_lines.extend(["Security Issues by Severity:"])
                for issue in data.get("by_severity", []):
                    result_lines.append(
                        f"  {issue['severity'].upper()}: {issue['count']} issues "
                        f"({issue['affected_repos']} repos)"
                    )
                
                result_lines.append("\nBy Vulnerability Type:")
                for vuln in data.get("by_vulnerability_type", [])[:10]:
                    result_lines.append(f"  {vuln['vulnerability_type']}: {vuln['count']}")
            
            return [types.TextContent(type="text", text="\n".join(result_lines))]
            
        except Exception as e:
            logger.error(f"Error getting performance metrics: {str(e)}")
            return [types.TextContent(type="text", text=f"Error getting performance metrics: {str(e)}")]
    
    async def _handle_get_system_health(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle system health requests."""
        include_history = arguments.get("include_history", False)
        
        if not self.metrics_collector:
            return [types.TextContent(type="text", text="Error: Metrics collection not enabled")]
        
        try:
            import psutil
            
            # Get current system metrics
            # Use interval=0 for non-blocking call (gets average since last call)
            cpu_percent = psutil.cpu_percent(interval=0)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            result_lines = [
                "🖥️  System Health Report",
                "",
                "Current Status:",
                f"  • CPU Usage: {cpu_percent:.1f}%",
                f"  • Memory Usage: {memory.percent:.1f}% ({memory.used / (1024**3):.1f}GB / {memory.total / (1024**3):.1f}GB)",
                f"  • Disk Usage: {disk.percent:.1f}% ({disk.used / (1024**3):.1f}GB / {disk.total / (1024**3):.1f}GB)",
                ""
            ]
            
            # Add process-specific information
            try:
                process = psutil.Process()
                process_memory = process.memory_info()
                result_lines.extend([
                    "Process Information:",
                    f"  • Memory Usage: {process_memory.rss / (1024**2):.1f}MB",
                    f"  • CPU Percent: {process.cpu_percent():.1f}%",
                    f"  • Open Files: {len(process.open_files())}",
                    f"  • Connections: {len(process.connections())}",
                    ""
                ])
            except:
                pass
            
            # Add metrics collection status
            if hasattr(self.metrics_collector, 'performance_buffer'):
                result_lines.extend([
                    "Metrics Buffer Status:",
                    f"  • Performance Buffer: {len(self.metrics_collector.performance_buffer)} items",
                    f"  • Usage Buffer: {len(self.metrics_collector.usage_buffer)} items",
                    f"  • Error Buffer: {len(self.metrics_collector.error_buffer)} items",
                    f"  • Security Buffer: {len(self.metrics_collector.security_buffer)} items",
                    ""
                ])
            
            # Add historical data if requested
            if include_history:
                try:
                    with self.metrics_collector._get_db_connection() as conn:
                        cursor = conn.execute("""
                            SELECT AVG(cpu_percent) as avg_cpu, 
                                   AVG(memory_percent) as avg_memory,
                                   MAX(cpu_percent) as max_cpu,
                                   MAX(memory_percent) as max_memory
                            FROM system_metrics 
                            WHERE timestamp > ?
                        """, (time.time() - 24*3600,))
                        
                        row = cursor.fetchone()
                        if row:
                            result_lines.extend([
                                "24-Hour Averages:",
                                f"  • Average CPU: {row['avg_cpu']:.1f}%",
                                f"  • Average Memory: {row['avg_memory']:.1f}%",
                                f"  • Peak CPU: {row['max_cpu']:.1f}%",
                                f"  • Peak Memory: {row['max_memory']:.1f}%",
                            ])
                except Exception as e:
                    result_lines.append(f"  • Historical data unavailable: {e}")
            
            return [types.TextContent(type="text", text="\n".join(result_lines))]
            
        except Exception as e:
            logger.error(f"Error getting system health: {str(e)}")
            return [types.TextContent(type="text", text=f"Error getting system health: {str(e)}")]
    
    async def _handle_cleanup_metrics(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle metrics cleanup requests."""
        if not self.metrics_collector:
            return [types.TextContent(type="text", text="Error: Metrics collection not enabled")]
        
        try:
            self.metrics_collector.cleanup_old_metrics()
            return [types.TextContent(type="text", text="✅ Metrics cleanup completed successfully")]
            
        except Exception as e:
            logger.error(f"Error during metrics cleanup: {str(e)}")
            return [types.TextContent(type="text", text=f"Error during metrics cleanup: {str(e)}")]
    
    # Auto-sync handlers
    
    async def _handle_configure_auto_sync(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Configure auto-sync settings."""
        if not self.auto_sync_manager:
            return [types.TextContent(type="text", text="Error: Auto-sync not available (code intelligence disabled)")]
        
        try:
            config = self.auto_sync_manager.config
            import os
            
            # Update configuration
            if 'scan_paths' in arguments:
                os.environ['AUTO_SYNC_PATHS'] = ','.join(arguments['scan_paths'])
            if 'exclude_patterns' in arguments:
                os.environ['AUTO_SYNC_EXCLUDE'] = ','.join(arguments['exclude_patterns'])
            if 'scan_interval' in arguments:
                config.scan_interval = arguments['scan_interval']
            if 'max_concurrent' in arguments:
                config.max_concurrent_syncs = arguments['max_concurrent']
            if 'priority_languages' in arguments:
                config.priority_languages = arguments['priority_languages']
            
            # Restart auto-sync with new config
            await self.auto_sync_manager.stop()
            self.auto_sync_manager = AutoSyncManager(
                repository_sync=self.repository_sync,
                storage_backend=self.storage,
                metrics_collector=self.metrics_collector
            )
            if self._mcp_context:
                self.auto_sync_manager._mcp_context = self._mcp_context
            await self.auto_sync_manager.start()
            
            return [types.TextContent(
                type="text",
                text="✅ Auto-sync configuration updated successfully"
            )]
            
        except Exception as e:
            logger.error(f"Failed to configure auto-sync: {e}")
            return [types.TextContent(
                type="text",
                text=f"Error configuring auto-sync: {str(e)}"
            )]
    
    async def _handle_get_auto_sync_status(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Get auto-sync status."""
        if not self.auto_sync_manager:
            return [types.TextContent(type="text", text="Error: Auto-sync not available (code intelligence disabled)")]
        
        try:
            status = await self.auto_sync_manager.get_status()
            
            result = [
                "🔄 Auto-Sync Status",
                "=" * 50,
                f"Enabled: {'✅' if status['enabled'] else '❌'}",
                f"Running: {'✅' if status['running'] else '❌'}",
            ]
            
            if status['last_scan']:
                result.append(f"Last Scan: {status['last_scan']}")
            
            result.extend([
                f"\nQueued Repositories: {status['queued_repos']}",
                f"Active Syncs: {status['active_syncs']}",
                f"Synced Repositories: {status['synced_repos']}",
                "\nConfiguration:",
                f"  Scan Interval: {status['config']['scan_interval']}s",
                f"  Sync Interval: {status['config']['sync_interval']}s",
                f"  Max Concurrent: {status['config']['max_concurrent']}"
            ])
            
            return [types.TextContent(type="text", text="\n".join(result))]
            
        except Exception as e:
            logger.error(f"Error getting auto-sync status: {e}")
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def _handle_trigger_repository_scan(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Trigger repository scan."""
        if not self.auto_sync_manager:
            return [types.TextContent(type="text", text="Error: Auto-sync not available (code intelligence disabled)")]
        
        try:
            stats = await self.auto_sync_manager.trigger_scan()
            
            return [types.TextContent(
                type="text",
                text=f"✅ Scan triggered successfully\n"
                     f"Repositories queued: {stats['queued']}\n"
                     f"Active syncs: {stats['active']}\n"
                     f"Total synced: {stats['synced']}"
            )]
            
        except Exception as e:
            logger.error(f"Error triggering scan: {e}")
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def _handle_pause_auto_sync(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Pause auto-sync."""
        if not self.auto_sync_manager:
            return [types.TextContent(type="text", text="Error: Auto-sync not available (code intelligence disabled)")]
        
        try:
            await self.auto_sync_manager.pause()
            return [types.TextContent(type="text", text="⏸️ Auto-sync paused")]
            
        except Exception as e:
            logger.error(f"Error pausing auto-sync: {e}")
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def _handle_resume_auto_sync(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Resume auto-sync."""
        if not self.auto_sync_manager:
            return [types.TextContent(type="text", text="Error: Auto-sync not available (code intelligence disabled)")]
        
        try:
            await self.auto_sync_manager.resume()
            return [types.TextContent(type="text", text="▶️ Auto-sync resumed")]
            
        except Exception as e:
            logger.error(f"Error resuming auto-sync: {e}")
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def _handle_get_auto_sync_paths(self, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Get auto-sync paths."""
        if not self.auto_sync_manager:
            return [types.TextContent(type="text", text="Error: Auto-sync not available (code intelligence disabled)")]
        
        try:
            import os
            import json
            
            # Get configured paths
            configured_paths = os.getenv('AUTO_SYNC_PATHS', '').split(',')
            configured_paths = [p.strip() for p in configured_paths if p.strip()]
            
            # Get Claude Code permitted paths
            permitted_paths = await self.auto_sync_manager._get_claude_code_permitted_paths()
            
            result = {
                'configured_paths': configured_paths,
                'claude_code_paths': permitted_paths,
                'active_paths': configured_paths or permitted_paths,
                'source': 'configured' if configured_paths else 'claude_code' if permitted_paths else 'none'
            }
            
            return [types.TextContent(
                type="text",
                text=json.dumps(result, indent=2)
            )]
            
        except Exception as e:
            logger.error(f"Failed to get auto-sync paths: {e}")
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]

# Entry point for enhanced server
async def main():
    """Main entry point for enhanced server."""
    import os
    import json
    
    # Get MCP context from environment or file
    mcp_context = {}
    
    # Claude Code might pass allowed paths via environment
    if 'CLAUDE_CODE_ALLOWED_PATHS' in os.environ:
        paths = os.environ['CLAUDE_CODE_ALLOWED_PATHS'].split(',')
        mcp_context['allowed_paths'] = [p.strip() for p in paths if p.strip()]
    
    # Or via a context file
    context_file = os.getenv('MCP_CONTEXT_FILE')
    if context_file and os.path.exists(context_file):
        with open(context_file, 'r') as f:
            mcp_context = json.load(f)
    
    # Initialize server with context
    server = EnhancedMemoryServer(
        enable_code_intelligence=True,
        mcp_context=mcp_context
    )
    await server.run()

if __name__ == "__main__":
    asyncio.run(main())