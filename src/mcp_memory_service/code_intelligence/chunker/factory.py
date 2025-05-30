"""
Factory for creating appropriate code chunkers.
"""
from typing import List, Optional, Dict, Type
from pathlib import Path

from .base import ChunkerBase, GenericChunker
from .python_chunker import PythonChunker
from .javascript_chunker import JavaScriptChunker
from .go_chunker import GoChunker
from .rust_chunker import RustChunker
from ...models.code import CodeChunk, detect_language_from_extension

class ChunkerFactory:
    """Factory for creating and managing code chunkers."""
    
    # Registry of available chunkers
    _chunkers: Dict[str, Type[ChunkerBase]] = {
        'python': PythonChunker,
        'javascript': JavaScriptChunker,
        'typescript': JavaScriptChunker,
        'go': GoChunker,
        'rust': RustChunker,
    }
    
    # Extension to language mapping
    _extension_map: Dict[str, str] = {
        '.py': 'python',
        '.pyw': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript', 
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.mjs': 'javascript',
        '.go': 'go',
        '.rs': 'rust',
    }
    
    @classmethod
    def get_chunker(cls, file_path: str, language: str = None) -> ChunkerBase:
        """Get appropriate chunker for a file."""
        if language:
            # Use specified language
            chunker_class = cls._chunkers.get(language, GenericChunker)
        else:
            # Auto-detect from extension
            ext = Path(file_path).suffix.lower()
            detected_language = cls._extension_map.get(ext)
            chunker_class = cls._chunkers.get(detected_language, GenericChunker)
        
        return chunker_class()
    
    @classmethod
    def chunk_file(cls, file_path: str, language: str = None, 
                   repository: str = None) -> List[CodeChunk]:
        """Chunk a single file."""
        chunker = cls.get_chunker(file_path, language)
        return chunker.chunk_file(file_path, repository)
    
    @classmethod
    def chunk_content(cls, content: str, file_path: str, 
                     language: str = None, repository: str = None) -> List[CodeChunk]:
        """Chunk content directly."""
        chunker = cls.get_chunker(file_path, language)
        return chunker.chunk_content(content, file_path, repository)
    
    @classmethod
    def get_supported_extensions(cls) -> List[str]:
        """Get list of all supported file extensions."""
        return list(cls._extension_map.keys())
    
    @classmethod
    def get_supported_languages(cls) -> List[str]:
        """Get list of all supported languages."""
        return list(cls._chunkers.keys())
    
    @classmethod
    def register_chunker(cls, language: str, chunker_class: Type[ChunkerBase],
                        extensions: List[str] = None):
        """Register a new chunker for a language."""
        cls._chunkers[language] = chunker_class
        
        if extensions:
            for ext in extensions:
                cls._extension_map[ext] = language