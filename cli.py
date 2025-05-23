#!/usr/bin/env python3
"""
CLI interface for mcp-code-intelligence.
Entry point script for command-line access.
"""
import asyncio
import argparse
import sys
import os
from pathlib import Path
from typing import List, Optional

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from mcp_memory_service.enhanced_server import EnhancedMemoryServer
from mcp_memory_service.code_intelligence.chunker.factory import ChunkerFactory
from mcp_memory_service.performance.cache import cache_manager

class CodeIntelligenceCLI:
    """CLI interface for code intelligence operations."""
    
    def __init__(self):
        self.server = None
    
    async def initialize(self):
        """Initialize the enhanced memory server."""
        print("🚀 Initializing Code Intelligence system...")
        self.server = EnhancedMemoryServer(enable_code_intelligence=True)
        print("✅ Ready")
    
    async def ingest_file(self, file_path: str, repository: str = None) -> None:
        """Ingest a single file into the code intelligence system."""
        if not os.path.exists(file_path):
            print(f"❌ Error: File not found: {file_path}")
            return
        
        if not repository:
            repository = Path(file_path).parent.name
        
        print(f"📥 Ingesting {file_path} into repository '{repository}'...")
        
        arguments = {
            'file_path': file_path,
            'repository': repository
        }
        
        try:
            result = await self.server._handle_ingest_code_file(arguments)
            for content in result:
                print(content.text)
        except Exception as e:
            print(f"❌ Error ingesting file: {e}")
    
    async def ingest_directory(self, directory: str, repository: str = None, 
                             recursive: bool = True) -> None:
        """Ingest all supported files in a directory."""
        if not os.path.exists(directory):
            print(f"❌ Error: Directory not found: {directory}")
            return
        
        if not repository:
            repository = Path(directory).name
        
        # Get supported extensions
        factory = ChunkerFactory()
        supported_extensions = factory.get_supported_extensions()
        
        # Find all supported files
        files_to_ingest = []
        
        if recursive:
            for root, dirs, files in os.walk(directory):
                # Skip common directories that shouldn't be indexed
                dirs[:] = [d for d in dirs if not d.startswith('.') and 
                          d not in ['node_modules', '__pycache__', 'venv', 'env', 'dist', 'build']]
                
                for file in files:
                    file_path = os.path.join(root, file)
                    if any(file.endswith(ext) for ext in supported_extensions):
                        files_to_ingest.append(file_path)
        else:
            for file in os.listdir(directory):
                file_path = os.path.join(directory, file)
                if os.path.isfile(file_path) and any(file.endswith(ext) for ext in supported_extensions):
                    files_to_ingest.append(file_path)
        
        if not files_to_ingest:
            print(f"❌ No supported files found in {directory}")
            print(f"Supported extensions: {', '.join(supported_extensions)}")
            return
        
        print(f"📂 Found {len(files_to_ingest)} files to ingest into '{repository}'")
        
        total_chunks = 0
        successful_files = 0
        
        for i, file_path in enumerate(files_to_ingest):
            try:
                rel_path = os.path.relpath(file_path, directory)
                print(f"📥 [{i+1}/{len(files_to_ingest)}] {rel_path}...")
                
                arguments = {
                    'file_path': file_path,
                    'repository': repository
                }
                
                result = await self.server._handle_ingest_code_file(arguments)
                # Extract chunk count from result text
                result_text = result[0].text if result else ""
                if "Successfully ingested" in result_text:
                    # Parse "Successfully ingested X/Y code chunks"
                    chunks_line = result_text.split('\n')[0]
                    chunk_count = int(chunks_line.split()[2].split('/')[0])
                    total_chunks += chunk_count
                    successful_files += 1
                    print(f"   ✅ {chunk_count} chunks")
                else:
                    print(f"   ⚠️  No chunks extracted")
                
            except Exception as e:
                print(f"   ❌ Error: {e}")
        
        print(f"\n🎉 Ingestion complete:")
        print(f"   📊 {successful_files}/{len(files_to_ingest)} files processed")
        print(f"   🧩 {total_chunks} total code chunks stored")
    
    async def search_code(self, query: str, repository: str = None, 
                         language: str = None, n_results: int = 10) -> None:
        """Search for code using semantic similarity."""
        print(f"🔍 Searching for: '{query}'")
        
        search_args = {
            'query': query,
            'n_results': n_results
        }
        
        if repository:
            search_args['repository'] = repository
            print(f"   📂 Repository: {repository}")
        
        if language:
            search_args['language'] = language
            print(f"   🔤 Language: {language}")
        
        print()
        
        try:
            result = await self.server._handle_search_code(search_args)
            for content in result:
                print(content.text)
        except Exception as e:
            print(f"❌ Error searching: {e}")
    
    async def get_stats(self, repository: str = None) -> None:
        """Get statistics about stored code."""
        print("📊 Code Repository Statistics")
        print()
        
        stats_args = {}
        if repository:
            stats_args['repository'] = repository
        
        try:
            result = await self.server._handle_get_code_stats(stats_args)
            for content in result:
                print(content.text)
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
    
    async def list_repositories(self) -> None:
        """List all known repositories."""
        print("📚 Available Repositories")
        print()
        
        try:
            # Get all memories and extract unique repositories
            results = await self.server.storage.retrieve("repository", 1000)
            repositories = set()
            
            for result in results:
                metadata = result.memory.metadata or {}
                repo = metadata.get("repository")
                if repo:
                    repositories.add(repo)
            
            if repositories:
                for repo in sorted(repositories):
                    print(f"   📂 {repo}")
            else:
                print("   No repositories found")
        except Exception as e:
            print(f"❌ Error listing repositories: {e}")
    
    async def cache_stats(self) -> None:
        """Display cache performance statistics."""
        print("🚀 Cache Performance Statistics")
        print()
        
        try:
            stats = cache_manager.get_cache_stats()
            
            # Search cache stats
            search_stats = stats['search_cache']
            print("🔍 Search Cache:")
            print(f"   Size: {search_stats['size']}/{search_stats['max_size']}")
            print(f"   Hit Rate: {search_stats['hit_rate']:.1%}")
            print(f"   Hits: {search_stats['hits']}")
            print(f"   Misses: {search_stats['misses']}")
            print(f"   Evictions: {search_stats['evictions']}")
            print()
            
            # Stats cache stats  
            stats_cache_stats = stats['stats_cache']
            print("📊 Stats Cache:")
            print(f"   Size: {stats_cache_stats['size']}/{stats_cache_stats['max_size']}")
            print(f"   Hit Rate: {stats_cache_stats['hit_rate']:.1%}")
            print(f"   Hits: {stats_cache_stats['hits']}")
            print(f"   Misses: {stats_cache_stats['misses']}")
            print(f"   Evictions: {stats_cache_stats['evictions']}")
            
        except Exception as e:
            print(f"❌ Error getting cache stats: {e}")
    
    async def clear_cache(self, repository: str = None) -> None:
        """Clear cache entries."""
        if repository:
            print(f"🧹 Clearing cache for repository '{repository}'...")
            invalidated = cache_manager.invalidate_repository(repository)
            print(f"✅ Cleared {invalidated['search_entries']} search entries and {invalidated['stats_entries']} stats entries")
        else:
            print("🧹 Clearing all cache entries...")
            invalidated = cache_manager.invalidate_all()
            print(f"✅ Cleared {invalidated['search_entries']} search entries and {invalidated['stats_entries']} stats entries")
    
    async def analyze_security(self, repository: str = None, language: str = None, 
                              severity: str = "medium", limit: int = 50) -> None:
        """Analyze code for security vulnerabilities."""
        print("🔒 Analyzing code for security vulnerabilities...")
        
        if repository:
            print(f"   Repository: {repository}")
        if language:
            print(f"   Language: {language}")
        print(f"   Min Severity: {severity}")
        print(f"   Limit: {limit}")
        print()
        
        try:
            # Create the request
            request = {
                "repository": repository,
                "language": language,
                "severity": severity,
                "limit": limit
            }
            
            # Filter out None values
            request = {k: v for k, v in request.items() if v is not None}
            
            # Call the server method directly
            result = await self.server._handle_analyze_security(request)
            
            # Print the result
            if result and len(result) > 0:
                print(result[0].text)
            else:
                print("❌ No results returned from security analysis")
                
        except Exception as e:
            print(f"❌ Error analyzing security: {e}")
    
    async def sync_repository(self, repository_path: str, repository_name: str, 
                             force_full: bool = False, disable_incremental: bool = False) -> None:
        """Synchronize a repository with the code intelligence system."""
        print(f"🔄 Synchronizing repository '{repository_name}' from {repository_path}")
        
        if force_full:
            print("   Mode: Full synchronization (forced)")
        elif disable_incremental:
            print("   Mode: Full synchronization (incremental disabled)")
        else:
            print("   Mode: Incremental synchronization")
        print()
        
        try:
            # Create the request
            request = {
                "repository_path": repository_path,
                "repository_name": repository_name,
                "incremental": not disable_incremental,
                "force_full": force_full
            }
            
            # Call the server method directly
            result = await self.server._handle_sync_repository(request)
            
            # Print the result
            if result and len(result) > 0:
                print(result[0].text)
            else:
                print("❌ No results returned from repository sync")
                
        except Exception as e:
            print(f"❌ Error synchronizing repository: {e}")
    
    async def list_repositories(self) -> None:
        """List all synchronized repositories."""
        print("📁 Listing synchronized repositories...")
        print()
        
        try:
            # Call the server method directly
            result = await self.server._handle_list_repositories({})
            
            # Print the result
            if result and len(result) > 0:
                print(result[0].text)
            else:
                print("❌ No results returned from repository list")
                
        except Exception as e:
            print(f"❌ Error listing repositories: {e}")
    
    async def get_repository_status(self, repository_name: str) -> None:
        """Get detailed status for a specific repository."""
        print(f"📊 Getting status for repository '{repository_name}'...")
        print()
        
        try:
            # Create the request
            request = {"repository_name": repository_name}
            
            # Call the server method directly
            result = await self.server._handle_get_repository_status(request)
            
            # Print the result
            if result and len(result) > 0:
                print(result[0].text)
            else:
                print("❌ No results returned from repository status")
                
        except Exception as e:
            print(f"❌ Error getting repository status: {e}")
    
    async def batch_analyze_repository(self, repository_path: str, repository_name: str, 
                                     store_results: bool = True, max_workers: int = 4, 
                                     generate_report: bool = True) -> None:
        """Perform comprehensive batch analysis of an entire repository."""
        print(f"🔄 Starting batch analysis of repository '{repository_name}'...")
        print(f"📁 Repository path: {repository_path}")
        print(f"👥 Workers: {max_workers}")
        print(f"💾 Store results: {'Yes' if store_results else 'No'}")
        print(f"📊 Generate report: {'Yes' if generate_report else 'No'}")
        print()
        
        try:
            # Create the request
            request = {
                "repository_path": repository_path,
                "repository_name": repository_name,
                "store_results": store_results,
                "max_workers": max_workers,
                "generate_report": generate_report
            }
            
            # Call the server method directly
            result = await self.server._handle_batch_analyze_repository(request)
            
            # Print the result
            if result and len(result) > 0:
                print(result[0].text)
            else:
                print("❌ No results returned from batch analysis")
                
        except Exception as e:
            print(f"❌ Error during batch analysis: {e}")
    
    async def get_batch_analysis_report(self, repository_name: str, output_format: str = "markdown", 
                                      output_file: str = None) -> None:
        """Generate and retrieve a comprehensive analysis report for a batch processed repository."""
        print(f"📊 Generating {output_format} report for repository '{repository_name}'...")
        print()
        
        try:
            # Create the request
            request = {
                "repository_name": repository_name,
                "output_format": output_format
            }
            
            # Call the server method directly
            result = await self.server._handle_get_batch_analysis_report(request)
            
            # Handle the result
            if result and len(result) > 0:
                report_content = result[0].text
                
                # Save to file if specified
                if output_file:
                    try:
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(report_content)
                        print(f"✅ Report saved to: {output_file}")
                        print()
                    except Exception as e:
                        print(f"❌ Error saving report to file: {e}")
                        print()
                
                # Print the report content
                print(report_content)
            else:
                print("❌ No results returned from batch report generation")
                
        except Exception as e:
            print(f"❌ Error generating batch report: {e}")
    
    async def get_performance_metrics(self, hours: int = 24, metric_type: str = "summary") -> None:
        """Get performance metrics and analytics."""
        print(f"📊 Retrieving {metric_type} metrics for the last {hours} hours...")
        print()
        
        try:
            # Create the request
            request = {
                "hours": hours,
                "metric_type": metric_type
            }
            
            # Call the server method directly
            result = await self.server._handle_get_performance_metrics(request)
            
            # Print the result
            if result and len(result) > 0:
                print(result[0].text)
            else:
                print("❌ No metrics data available")
                
        except Exception as e:
            print(f"❌ Error getting performance metrics: {e}")
    
    async def get_system_health(self, include_history: bool = False) -> None:
        """Get current system health and resource utilization metrics."""
        print("🖥️  Checking system health...")
        print()
        
        try:
            # Create the request
            request = {
                "include_history": include_history
            }
            
            # Call the server method directly
            result = await self.server._handle_get_system_health(request)
            
            # Print the result
            if result and len(result) > 0:
                print(result[0].text)
            else:
                print("❌ No system health data available")
                
        except Exception as e:
            print(f"❌ Error getting system health: {e}")
    
    async def cleanup_metrics(self) -> None:
        """Clean up old metrics data beyond retention period."""
        print("🧹 Cleaning up old metrics data...")
        print()
        
        try:
            # Create the request
            request = {}
            
            # Call the server method directly
            result = await self.server._handle_cleanup_metrics(request)
            
            # Print the result
            if result and len(result) > 0:
                print(result[0].text)
            else:
                print("❌ No cleanup result returned")
                
        except Exception as e:
            print(f"❌ Error cleaning up metrics: {e}")
    
    # Auto-sync methods
    
    async def configure_auto_sync(self, scan_paths: List[str] = None, exclude_patterns: List[str] = None,
                                  scan_interval: int = None, max_concurrent: int = None,
                                  priority_languages: List[str] = None, enabled: bool = None) -> None:
        """Configure auto-sync settings."""
        args = {}
        
        if scan_paths:
            args['scan_paths'] = scan_paths
        if exclude_patterns:
            args['exclude_patterns'] = exclude_patterns
        if scan_interval is not None:
            args['scan_interval'] = scan_interval
        if max_concurrent is not None:
            args['max_concurrent'] = max_concurrent
        if priority_languages:
            args['priority_languages'] = priority_languages
        
        # Handle enabled/disabled separately
        if enabled is not None:
            import os
            os.environ['AUTO_SYNC_ENABLED'] = 'true' if enabled else 'false'
        
        if not args and enabled is None:
            print("❌ No configuration changes specified")
            return
        
        print("🔧 Configuring auto-sync...")
        
        try:
            result = await self.server._handle_configure_auto_sync(args)
            for content in result:
                print(content.text)
        except Exception as e:
            print(f"❌ Error: {e}")
    
    async def get_auto_sync_status(self) -> None:
        """Get auto-sync status."""
        try:
            result = await self.server._handle_get_auto_sync_status({})
            for content in result:
                print(content.text)
        except Exception as e:
            print(f"❌ Error: {e}")
    
    async def trigger_auto_sync_scan(self) -> None:
        """Trigger repository scan."""
        print("🔍 Triggering repository scan...")
        
        try:
            result = await self.server._handle_trigger_repository_scan({})
            for content in result:
                print(content.text)
        except Exception as e:
            print(f"❌ Error: {e}")
    
    async def get_auto_sync_paths(self) -> None:
        """Get auto-sync paths."""
        try:
            result = await self.server._handle_get_auto_sync_paths({})
            for content in result:
                print(content.text)
        except Exception as e:
            print(f"❌ Error: {e}")

def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description="🧠 Code Intelligence CLI - Semantic code search and analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ingest-file main.py --repository MyProject
  %(prog)s ingest-dir ./src --repository MyProject --recursive  
  %(prog)s search "authentication function" --repository MyProject
  %(prog)s stats --repository MyProject
  %(prog)s analyze-security --repository MyProject --severity high
  %(prog)s list-repos
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Ingest file command
    ingest_file_parser = subparsers.add_parser(
        'ingest-file',
        help='Ingest a single file into the code intelligence system'
    )
    ingest_file_parser.add_argument('file_path', help='Path to the file to ingest')
    ingest_file_parser.add_argument('--repository', '-r', help='Repository name (default: parent directory name)')
    
    # Ingest directory command
    ingest_dir_parser = subparsers.add_parser(
        'ingest-dir',
        help='Ingest all supported files in a directory'
    )
    ingest_dir_parser.add_argument('directory', help='Directory to ingest')
    ingest_dir_parser.add_argument('--repository', '-r', help='Repository name (default: directory name)')
    ingest_dir_parser.add_argument('--recursive', action='store_true', default=True, help='Process subdirectories (default)')
    ingest_dir_parser.add_argument('--no-recursive', dest='recursive', action='store_false', help='Don\'t process subdirectories')
    
    # Search command
    search_parser = subparsers.add_parser(
        'search',
        help='Search for code using semantic similarity'
    )
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--repository', '-r', help='Filter by repository')
    search_parser.add_argument('--language', '-l', help='Filter by programming language')
    search_parser.add_argument('--results', '-n', type=int, default=10, help='Number of results (default: 10)')
    
    # Stats command
    stats_parser = subparsers.add_parser(
        'stats',
        help='Get statistics about stored code'
    )
    stats_parser.add_argument('--repository', '-r', help='Filter by repository')
    
    # List repositories command
    subparsers.add_parser(
        'list-repos',
        help='List all known repositories'
    )
    
    # Cache management commands
    subparsers.add_parser(
        'cache-stats',
        help='Show cache performance statistics'
    )
    
    clear_cache_parser = subparsers.add_parser(
        'clear-cache',
        help='Clear cache entries'
    )
    clear_cache_parser.add_argument('--repository', '-r', help='Clear cache only for specific repository')
    
    # Security analysis command
    security_parser = subparsers.add_parser(
        'analyze-security',
        help='Analyze code for security vulnerabilities'
    )
    security_parser.add_argument('--repository', '-r', help='Filter by repository')
    security_parser.add_argument('--language', '-l', help='Filter by programming language')
    security_parser.add_argument('--severity', '-s', choices=['low', 'medium', 'high', 'critical'], 
                                default='medium', help='Minimum severity level (default: medium)')
    security_parser.add_argument('--limit', '-n', type=int, default=50, help='Maximum number of results (default: 50)')
    
    # Repository synchronization commands
    sync_parser = subparsers.add_parser(
        'sync-repository',
        help='Synchronize a repository with the code intelligence system'
    )
    sync_parser.add_argument('repository_path', help='Path to the repository')
    sync_parser.add_argument('repository_name', help='Name for the repository')
    sync_parser.add_argument('--full', action='store_true', help='Force full synchronization')
    sync_parser.add_argument('--no-incremental', action='store_true', help='Disable incremental sync')
    
    # List repositories command (enhanced)
    list_repos_parser = subparsers.add_parser(
        'list-repositories',
        help='List all synchronized repositories with detailed status'
    )
    
    # Repository status command
    status_parser = subparsers.add_parser(
        'repository-status',
        help='Get detailed status for a specific repository'
    )
    status_parser.add_argument('repository_name', help='Name of the repository')
    
    # Batch processing commands
    batch_parser = subparsers.add_parser(
        'batch-analyze',
        help='Perform comprehensive batch analysis of an entire repository'
    )
    batch_parser.add_argument('repository_path', help='Path to the repository')
    batch_parser.add_argument('repository_name', help='Name for the repository')
    batch_parser.add_argument('--no-store', action='store_true', help='Skip storing chunks in vector database')
    batch_parser.add_argument('--workers', '-w', type=int, default=4, help='Number of parallel workers (default: 4)')
    batch_parser.add_argument('--no-report', action='store_true', help='Skip generating analysis report')
    
    # Batch report command
    report_parser = subparsers.add_parser(
        'batch-report',
        help='Generate and retrieve a comprehensive analysis report for a batch processed repository'
    )
    report_parser.add_argument('repository_name', help='Name of the repository')
    report_parser.add_argument('--format', '-f', choices=['markdown', 'json'], default='markdown', 
                              help='Report format (default: markdown)')
    report_parser.add_argument('--output', '-o', help='Output file path (optional)')
    
    # Metrics and monitoring commands
    metrics_parser = subparsers.add_parser(
        'metrics',
        help='Get performance metrics and analytics for code intelligence operations'
    )
    metrics_parser.add_argument('--hours', type=int, default=24, help='Time range in hours (default: 24)')
    metrics_parser.add_argument('--type', '-t', choices=['summary', 'performance', 'usage', 'errors', 'security'], 
                               default='summary', help='Type of metrics (default: summary)')
    
    # System health command
    health_parser = subparsers.add_parser(
        'system-health',
        help='Get current system health and resource utilization metrics'
    )
    health_parser.add_argument('--history', action='store_true', help='Include historical system metrics')
    
    # Metrics cleanup command
    cleanup_parser = subparsers.add_parser(
        'cleanup-metrics',
        help='Clean up old metrics data beyond retention period'
    )
    
    # Auto-sync commands
    auto_sync_config_parser = subparsers.add_parser(
        'auto-sync-config',
        help='Configure automatic repository synchronization'
    )
    auto_sync_config_parser.add_argument('--path', '-p', action='append', dest='scan_paths',
                                        help='Paths to scan for repositories (can be specified multiple times)')
    auto_sync_config_parser.add_argument('--exclude', '-e', action='append', dest='exclude_patterns',
                                        help='Patterns to exclude (can be specified multiple times)')
    auto_sync_config_parser.add_argument('--scan-interval', type=int, help='Scan interval in seconds')
    auto_sync_config_parser.add_argument('--max-concurrent', type=int, help='Maximum concurrent sync operations')
    auto_sync_config_parser.add_argument('--priority-languages', nargs='+', help='Languages to prioritize')
    auto_sync_config_parser.add_argument('--enabled/--disabled', dest='enabled', default=None,
                                        help='Enable or disable auto-sync')
    
    auto_sync_status_parser = subparsers.add_parser(
        'auto-sync-status',
        help='Get current status of automatic repository synchronization'
    )
    
    auto_sync_scan_parser = subparsers.add_parser(
        'auto-sync-scan',
        help='Manually trigger a scan for new repositories'
    )
    
    auto_sync_paths_parser = subparsers.add_parser(
        'auto-sync-paths',
        help='Display the paths that will be used for automatic synchronization'
    )
    
    return parser

async def main():
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    cli = CodeIntelligenceCLI()
    
    try:
        await cli.initialize()
        
        if args.command == 'ingest-file':
            await cli.ingest_file(args.file_path, args.repository)
        
        elif args.command == 'ingest-dir':
            await cli.ingest_directory(args.directory, args.repository, args.recursive)
        
        elif args.command == 'search':
            await cli.search_code(args.query, args.repository, args.language, args.results)
        
        elif args.command == 'stats':
            await cli.get_stats(args.repository)
        
        elif args.command == 'list-repos':
            await cli.list_repositories()
        
        elif args.command == 'cache-stats':
            await cli.cache_stats()
        
        elif args.command == 'clear-cache':
            await cli.clear_cache(args.repository)
        
        elif args.command == 'analyze-security':
            await cli.analyze_security(args.repository, args.language, args.severity, args.limit)
        
        elif args.command == 'sync-repository':
            await cli.sync_repository(args.repository_path, args.repository_name, args.full, args.no_incremental)
        
        elif args.command == 'list-repositories':
            await cli.list_repositories()
        
        elif args.command == 'repository-status':
            await cli.get_repository_status(args.repository_name)
        
        elif args.command == 'batch-analyze':
            await cli.batch_analyze_repository(args.repository_path, args.repository_name, 
                                             not args.no_store, args.workers, not args.no_report)
        
        elif args.command == 'batch-report':
            await cli.get_batch_analysis_report(args.repository_name, args.format, args.output)
        
        elif args.command == 'metrics':
            await cli.get_performance_metrics(args.hours, args.type)
        
        elif args.command == 'system-health':
            await cli.get_system_health(args.history)
        
        elif args.command == 'cleanup-metrics':
            await cli.cleanup_metrics()
        
        elif args.command == 'auto-sync-config':
            await cli.configure_auto_sync(
                scan_paths=args.scan_paths,
                exclude_patterns=args.exclude_patterns,
                scan_interval=args.scan_interval,
                max_concurrent=args.max_concurrent,
                priority_languages=args.priority_languages,
                enabled=args.enabled
            )
        
        elif args.command == 'auto-sync-status':
            await cli.get_auto_sync_status()
        
        elif args.command == 'auto-sync-scan':
            await cli.trigger_auto_sync_scan()
        
        elif args.command == 'auto-sync-paths':
            await cli.get_auto_sync_paths()
        
        else:
            parser.print_help()
            
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())