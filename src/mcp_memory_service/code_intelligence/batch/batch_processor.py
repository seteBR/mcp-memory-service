"""
Batch processing capabilities for analyzing entire repositories with parallel processing,
progress tracking, and comprehensive reporting.
"""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable, Any
import logging
from collections import defaultdict
import json

from ..chunker.factory import ChunkerFactory
from ...security.analyzer import SecurityAnalyzer, SecurityIssue, Severity
from ...models.code import CodeChunk
from ...storage.base import MemoryStorage


@dataclass
class BatchProgress:
    """Track batch processing progress."""
    total_files: int = 0
    processed_files: int = 0
    total_chunks: int = 0
    stored_chunks: int = 0
    failed_files: int = 0
    security_issues: int = 0
    start_time: float = field(default_factory=time.time)
    current_file: Optional[str] = None
    
    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time
    
    @property
    def progress_percentage(self) -> float:
        if self.total_files == 0:
            return 0.0
        return (self.processed_files / self.total_files) * 100
    
    @property
    def processing_rate(self) -> float:
        """Files per second."""
        if self.elapsed_time == 0:
            return 0.0
        return self.processed_files / self.elapsed_time
    
    @property
    def estimated_remaining(self) -> float:
        """Estimated remaining time in seconds."""
        if self.processing_rate == 0:
            return 0.0
        remaining_files = self.total_files - self.processed_files
        return remaining_files / self.processing_rate


@dataclass
class BatchResult:
    """Results from batch processing."""
    repository_name: str
    repository_path: str
    progress: BatchProgress
    file_results: Dict[str, Dict] = field(default_factory=dict)
    security_summary: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    language_summary: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    error_summary: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'repository_name': self.repository_name,
            'repository_path': self.repository_path,
            'summary': {
                'total_files': self.progress.total_files,
                'processed_files': self.progress.processed_files,
                'failed_files': self.progress.failed_files,
                'total_chunks': self.progress.total_chunks,
                'stored_chunks': self.progress.stored_chunks,
                'security_issues': self.progress.security_issues,
                'processing_time': self.progress.elapsed_time,
                'processing_rate': self.progress.processing_rate
            },
            'security_summary': dict(self.security_summary),
            'language_summary': dict(self.language_summary),
            'error_summary': {k: list(v) for k, v in self.error_summary.items()},
            'file_results': self.file_results
        }


class BatchProcessor:
    """Batch processor for analyzing entire repositories with parallel processing."""
    
    def __init__(self, storage: MemoryStorage, max_workers: int = 4, chunk_size: int = 100):
        self.storage = storage
        self.max_workers = max_workers
        self.chunk_size = chunk_size
        self.chunker_factory = ChunkerFactory()
        self.security_analyzer = SecurityAnalyzer()
        self.logger = logging.getLogger(__name__)
        
        # File extensions to process
        self.supported_extensions = {
            '.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.rs', '.java', '.cpp', '.c', '.h',
            '.hpp', '.cs', '.php', '.rb', '.swift', '.kt', '.scala', '.r', '.sql', '.sh',
            '.bash', '.zsh', '.fish', '.ps1', '.yaml', '.yml', '.json', '.xml', '.html',
            '.css', '.scss', '.less', '.md', '.rst', '.txt', '.dockerfile', '.makefile'
        }
        
        # Files/directories to exclude
        self.exclude_patterns = {
            '__pycache__', '.git', '.svn', '.hg', 'node_modules', '.pytest_cache',
            '.coverage', '.tox', '.venv', 'venv', '.env', 'dist', 'build', '.idea',
            '.vscode', '.vs', '*.egg-info', '.mypy_cache', '.ruff_cache'
        }
    
    def _should_process_file(self, file_path: Path) -> bool:
        """Determine if a file should be processed."""
        # Check extension
        if file_path.suffix.lower() not in self.supported_extensions:
            # Also check special files without extensions
            if file_path.name.lower() not in {'dockerfile', 'makefile', 'rakefile', 'gemfile'}:
                return False
        
        # Check exclusion patterns
        for part in file_path.parts:
            if any(pattern in part.lower() for pattern in self.exclude_patterns):
                return False
        
        # Check file size (skip very large files > 10MB)
        try:
            if file_path.stat().st_size > 10 * 1024 * 1024:
                return False
        except (OSError, IOError):
            return False
        
        return True
    
    def _collect_files(self, repository_path: Path) -> List[Path]:
        """Collect all files to process from the repository."""
        files = []
        try:
            for file_path in repository_path.rglob('*'):
                if file_path.is_file() and self._should_process_file(file_path):
                    files.append(file_path)
        except (OSError, IOError) as e:
            self.logger.error(f"Error collecting files from {repository_path}: {e}")
        
        return sorted(files)
    
    def _process_single_file(self, file_path: Path, repository_name: str, 
                           progress_callback: Optional[Callable] = None) -> Dict:
        """Process a single file and return results."""
        result = {
            'file_path': str(file_path),
            'chunks': [],
            'security_issues': [],
            'language': None,
            'error': None,
            'processing_time': 0
        }
        
        start_time = time.time()
        
        try:
            # Update progress if callback provided
            if progress_callback:
                progress_callback(current_file=str(file_path))
            
            # Read file content
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
            except UnicodeDecodeError:
                # Try with different encodings
                for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        content = file_path.read_text(encoding=encoding, errors='ignore')
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    raise UnicodeDecodeError("Unable to decode file with any encoding")
            
            # Determine language and get chunker
            language = self._detect_language(file_path)
            result['language'] = language
            
            chunker = self.chunker_factory.get_chunker(language)
            if not chunker:
                result['error'] = f"No chunker available for language: {language}"
                return result
            
            # Chunk the file
            chunks = chunker.chunk_content(content, str(file_path))
            result['chunks'] = [
                {
                    'chunk_type': chunk.chunk_type,
                    'chunk_id': chunk.chunk_id,
                    'start_line': chunk.start_line,
                    'end_line': chunk.end_line,
                    'size': len(chunk.text)
                }
                for chunk in chunks
            ]
            
            # Analyze security issues
            security_issues = self.security_analyzer.analyze_code(content, language)
            result['security_issues'] = [
                {
                    'type': issue.issue_type,
                    'severity': issue.severity.value if hasattr(issue.severity, 'value') else str(issue.severity),
                    'message': issue.message,
                    'line_number': issue.line_number,
                    'recommendation': issue.recommendation
                }
                for issue in security_issues
            ]
            
            # Store chunks with repository context
            for chunk in chunks:
                chunk.repository = repository_name
                chunk.security_issues = security_issues
            
            result['chunks_created'] = len(chunks)
            result['security_issues_found'] = len(security_issues)
            
        except Exception as e:
            result['error'] = str(e)
            self.logger.error(f"Error processing file {file_path}: {e}")
        finally:
            result['processing_time'] = time.time() - start_time
        
        return result
    
    def _detect_language(self, file_path: Path) -> str:
        """Detect programming language from file extension."""
        extension = file_path.suffix.lower()
        name = file_path.name.lower()
        
        # Map extensions to languages
        extension_map = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'typescript',
            '.tsx': 'typescript',
            '.jsx': 'javascript',
            '.go': 'go',
            '.rs': 'rust',
            '.java': 'java',
            '.cpp': 'cpp',
            '.c': 'c',
            '.h': 'c',
            '.hpp': 'cpp',
            '.cs': 'csharp',
            '.php': 'php',
            '.rb': 'ruby',
            '.swift': 'swift',
            '.kt': 'kotlin',
            '.scala': 'scala',
            '.r': 'r',
            '.sql': 'sql',
            '.sh': 'bash',
            '.bash': 'bash',
            '.zsh': 'bash',
            '.fish': 'bash',
            '.ps1': 'powershell',
            '.yaml': 'yaml',
            '.yml': 'yaml',
            '.json': 'json',
            '.xml': 'xml',
            '.html': 'html',
            '.css': 'css',
            '.scss': 'css',
            '.less': 'css',
            '.md': 'markdown',
            '.rst': 'rst',
            '.txt': 'text'
        }
        
        # Special files without extensions
        name_map = {
            'dockerfile': 'dockerfile',
            'makefile': 'makefile',
            'rakefile': 'ruby',
            'gemfile': 'ruby'
        }
        
        return name_map.get(name, extension_map.get(extension, 'unknown'))
    
    async def _store_chunks_batch(self, chunks: List[CodeChunk]) -> Tuple[int, int, int]:
        """Store chunks in batches and return (stored, duplicates, errors)."""
        stored_count = 0
        duplicate_count = 0
        error_count = 0
        
        # Process chunks in smaller batches to avoid memory issues
        for i in range(0, len(chunks), self.chunk_size):
            batch = chunks[i:i + self.chunk_size]
            for chunk in batch:
                try:
                    memory = chunk.to_memory()
                    success, message = await self.storage.store(memory)
                    if success:
                        stored_count += 1
                    elif "Duplicate content detected" in message:
                        duplicate_count += 1
                    else:
                        error_count += 1
                except Exception as e:
                    self.logger.error(f"Error storing chunk: {e}")
                    error_count += 1
        
        return stored_count, duplicate_count, error_count
    
    async def process_repository(self, repository_path: str, repository_name: str,
                               progress_callback: Optional[Callable] = None,
                               store_results: bool = True) -> BatchResult:
        """Process an entire repository with batch processing capabilities."""
        repo_path = Path(repository_path)
        if not repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repository_path}")
        
        # Initialize result tracking
        progress = BatchProgress()
        result = BatchResult(repository_name=repository_name, repository_path=repository_path, progress=progress)
        
        # Collect files to process
        files_to_process = self._collect_files(repo_path)
        progress.total_files = len(files_to_process)
        
        if progress.total_files == 0:
            self.logger.warning(f"No files found to process in {repository_path}")
            return result
        
        self.logger.info(f"Starting batch processing of {progress.total_files} files in {repository_name}")
        
        # Process files in parallel batches
        all_chunks = []
        
        def update_progress(**kwargs):
            for key, value in kwargs.items():
                setattr(progress, key, value)
            if progress_callback:
                progress_callback(progress)
        
        # Use ThreadPoolExecutor for CPU-bound file processing
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all file processing tasks
            future_to_file = {
                executor.submit(self._process_single_file, file_path, repository_name, update_progress): file_path
                for file_path in files_to_process
            }
            
            # Process completed tasks
            for future in as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    file_result = future.result()
                    progress.processed_files += 1
                    
                    # Store file result
                    result.file_results[str(file_path)] = file_result
                    
                    # Aggregate statistics
                    if file_result.get('error'):
                        progress.failed_files += 1
                        result.error_summary[file_result['error']].append(str(file_path))
                    else:
                        # Count chunks and security issues
                        chunks_count = file_result.get('chunks_created', 0)
                        progress.total_chunks += chunks_count
                        
                        security_count = file_result.get('security_issues_found', 0)
                        progress.security_issues += security_count
                        
                        # Language statistics
                        language = file_result.get('language', 'unknown')
                        result.language_summary[language] += 1
                        
                        # Security severity statistics
                        for issue in file_result.get('security_issues', []):
                            severity = issue.get('severity', 'unknown')
                            result.security_summary[severity] += 1
                        
                        # Prepare chunks for storage if enabled
                        if store_results and chunks_count > 0:
                            try:
                                content = file_path.read_text(encoding='utf-8', errors='ignore')
                                language = self._detect_language(file_path)
                                chunker = self.chunker_factory.get_chunker(language)
                                if chunker:
                                    chunks = chunker.chunk_content(content, str(file_path))
                                    for chunk in chunks:
                                        chunk.repository = repository_name
                                        # Add security issues if any
                                        security_issues = [
                                            SecurityIssue(
                                                issue_type=issue['type'],
                                                severity=getattr(Severity, issue['severity'].upper(), Severity.LOW),
                                                message=issue['message'],
                                                line_number=issue['line_number'],
                                                recommendation=issue['recommendation']
                                            )
                                            for issue in file_result.get('security_issues', [])
                                        ]
                                        chunk.security_issues = security_issues
                                    all_chunks.extend(chunks)
                            except Exception as e:
                                self.logger.error(f"Error preparing chunks for storage: {e}")
                
                except Exception as e:
                    progress.failed_files += 1
                    progress.processed_files += 1
                    error_msg = f"Processing failed: {str(e)}"
                    result.error_summary[error_msg].append(str(file_path))
                    self.logger.error(f"Error processing {file_path}: {e}")
                
                # Update progress
                update_progress()
        
        # Store chunks if enabled
        if store_results and all_chunks:
            self.logger.info(f"Storing {len(all_chunks)} chunks to vector database...")
            stored, duplicates, errors = await self._store_chunks_batch(all_chunks)
            progress.stored_chunks = stored
            
            self.logger.info(f"Storage complete: {stored} stored, {duplicates} duplicates, {errors} errors")
        
        # Final progress update
        update_progress()
        
        processing_time = progress.elapsed_time
        self.logger.info(
            f"Batch processing complete for {repository_name}: "
            f"{progress.processed_files}/{progress.total_files} files processed "
            f"in {processing_time:.2f}s ({progress.processing_rate:.1f} files/s)"
        )
        
        return result
    
    def generate_report(self, result: BatchResult, output_path: Optional[str] = None) -> str:
        """Generate a comprehensive analysis report."""
        report_lines = [
            f"# Code Intelligence Batch Analysis Report",
            f"",
            f"**Repository:** {result.repository_name}",
            f"**Path:** {result.repository_path}",
            f"**Analysis Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"## Summary",
            f"",
            f"- **Total Files:** {result.progress.total_files}",
            f"- **Processed Files:** {result.progress.processed_files}",
            f"- **Failed Files:** {result.progress.failed_files}",
            f"- **Total Chunks:** {result.progress.total_chunks}",
            f"- **Stored Chunks:** {result.progress.stored_chunks}",
            f"- **Security Issues:** {result.progress.security_issues}",
            f"- **Processing Time:** {result.progress.elapsed_time:.2f} seconds",
            f"- **Processing Rate:** {result.progress.processing_rate:.1f} files/second",
            f"",
            f"## Language Distribution",
            f""
        ]
        
        # Language statistics
        if result.language_summary:
            for language, count in sorted(result.language_summary.items(), key=lambda x: x[1], reverse=True):
                percentage = (count / result.progress.processed_files) * 100 if result.progress.processed_files > 0 else 0
                report_lines.append(f"- **{language.title()}:** {count} files ({percentage:.1f}%)")
        else:
            report_lines.append("- No language data available")
        
        report_lines.extend([
            f"",
            f"## Security Analysis",
            f""
        ])
        
        # Security statistics
        if result.security_summary:
            total_issues = sum(result.security_summary.values())
            report_lines.append(f"**Total Security Issues:** {total_issues}")
            report_lines.append("")
            for severity, count in sorted(result.security_summary.items()):
                percentage = (count / total_issues) * 100 if total_issues > 0 else 0
                report_lines.append(f"- **{severity.upper()}:** {count} issues ({percentage:.1f}%)")
        else:
            report_lines.append("- No security issues detected")
        
        # Error summary
        if result.error_summary:
            report_lines.extend([
                f"",
                f"## Errors and Issues",
                f""
            ])
            for error_type, files in result.error_summary.items():
                report_lines.append(f"**{error_type}:** {len(files)} files")
                for file_path in files[:5]:  # Show first 5 files
                    report_lines.append(f"  - {file_path}")
                if len(files) > 5:
                    report_lines.append(f"  - ... and {len(files) - 5} more files")
                report_lines.append("")
        
        report_content = "\n".join(report_lines)
        
        # Save to file if output path provided
        if output_path:
            Path(output_path).write_text(report_content, encoding='utf-8')
            self.logger.info(f"Report saved to {output_path}")
        
        return report_content