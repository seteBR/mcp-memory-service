"""
Base classes for code chunking functionality.
"""
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import hashlib
from pathlib import Path

from ...models.code import CodeChunk

class ChunkerBase(ABC):
    """Base class for language-specific code chunkers."""
    
    def __init__(self):
        self.supported_extensions = set()
        self.language_name = "unknown"
    
    @abstractmethod
    def chunk_content(self, content: str, file_path: str, 
                     repository: str = None) -> List[CodeChunk]:
        """Parse content and return semantic code chunks."""
        pass
    
    def chunk_file(self, file_path: str, repository: str = None) -> List[CodeChunk]:
        """Read and chunk a file."""
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            return self.chunk_content(content, file_path, repository)
        except Exception as e:
            raise RuntimeError(f"Failed to read {file_path}: {str(e)}")
    
    def supports_file(self, file_path: str) -> bool:
        """Check if this chunker supports the given file."""
        return Path(file_path).suffix.lower() in self.supported_extensions

class GenericChunker(ChunkerBase):
    """Fallback chunker for unsupported languages."""
    
    def __init__(self):
        super().__init__()
        self.language_name = "text"
        self.supported_extensions = set()  # Supports any file as fallback
    
    def chunk_content(self, content: str, file_path: str, 
                     repository: str = None) -> List[CodeChunk]:
        """Create a single chunk for the entire file."""
        if not content.strip():
            return []
        
        return [CodeChunk.create(
            file_path=file_path,
            language=self.language_name,
            text=content,
            start_line=1,
            end_line=len(content.splitlines()),
            chunk_type="file",
            repository=repository
        )]