#!/usr/bin/env python3
"""
CLI interface for mcp-code-intelligence.
Provides command-line access to code intelligence features.
"""
import asyncio
import argparse
import sys
import os
from pathlib import Path
from typing import List, Optional

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from .enhanced_server import EnhancedMemoryServer
from .code_intelligence.chunker.factory import ChunkerFactory

class CodeIntelligenceCLI:
    """CLI interface for code intelligence operations."""
    
    def __init__(self):
        self.server = None
    
    async def initialize(self):
        """Initialize the enhanced memory server."""
        print("Initializing Code Intelligence system...")
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
                          d not in ['node_modules', '__pycache__', 'venv', 'env']]
                
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
        
        print(f"📂 Found {len(files_to_ingest)} files to ingest in '{repository}'")
        
        total_chunks = 0
        successful_files = 0
        
        for file_path in files_to_ingest:
            try:
                print(f"📥 Processing {os.path.relpath(file_path, directory)}...")
                
                arguments = {
                    'file_path': file_path,
                    'repository': repository
                }
                
                result = await self.server._handle_ingest_code_file(arguments)
                # Extract chunk count from result text
                result_text = result[0].text if result else ""
                if "Successfully ingested" in result_text:
                    chunks_line = result_text.split('\n')[0]
                    chunk_count = int(chunks_line.split('/')[0].split()[-1])
                    total_chunks += chunk_count
                    successful_files += 1
                
            except Exception as e:
                print(f"❌ Error processing {file_path}: {e}")
        
        print(f"\n✅ Ingestion complete:")
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
        
        try:
            result = await self.server._handle_search_code(search_args)
            for content in result:
                print(content.text)
        except Exception as e:
            print(f"❌ Error searching: {e}")
    
    async def get_stats(self, repository: str = None) -> None:
        """Get statistics about stored code."""
        print("📊 Code Repository Statistics")
        
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

def create_parser() -> argparse.ArgumentParser:
    """Create the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        description="Code Intelligence CLI - Semantic code search and analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ingest-file main.py --repository MyProject
  %(prog)s ingest-dir ./src --repository MyProject --recursive
  %(prog)s search "authentication function" --repository MyProject
  %(prog)s stats --repository MyProject
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
    ingest_dir_parser.add_argument('--recursive', action='store_true', default=True, help='Process subdirectories')
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
        
        else:
            parser.print_help()
            
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    asyncio.run(main())