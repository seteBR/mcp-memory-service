#!/usr/bin/env python3
"""
Extend supported file types for code intelligence sync.
This script shows how to add support for additional file extensions.
"""

import sys
import os

# Add the src directory to Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from mcp_memory_service.code_intelligence.chunker.factory import ChunkerFactory
from mcp_memory_service.code_intelligence.chunker.base import GenericChunker

def extend_supported_file_types():
    """Add support for additional file types using the GenericChunker."""
    
    # Define additional file types to support
    additional_extensions = {
        # Documentation files
        '.md': 'markdown',
        '.rst': 'restructuredtext',
        '.txt': 'text',
        '.adoc': 'asciidoc',
        
        # Configuration files
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.toml': 'toml',
        '.ini': 'ini',
        '.cfg': 'config',
        '.conf': 'config',
        '.properties': 'properties',
        
        # Web files
        '.html': 'html',
        '.htm': 'html',
        '.xml': 'xml',
        '.css': 'css',
        '.scss': 'scss',
        '.sass': 'sass',
        '.less': 'less',
        
        # Shell scripts
        '.sh': 'shell',
        '.bash': 'bash',
        '.zsh': 'zsh',
        '.fish': 'fish',
        '.ps1': 'powershell',
        '.bat': 'batch',
        '.cmd': 'batch',
        
        # Data files
        '.csv': 'csv',
        '.sql': 'sql',
        
        # Other languages
        '.java': 'java',
        '.c': 'c',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.h': 'c',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.scala': 'scala',
        '.lua': 'lua',
        '.r': 'r',
        '.R': 'r',
        '.m': 'matlab',
        '.jl': 'julia',
        '.dart': 'dart',
        '.ex': 'elixir',
        '.exs': 'elixir',
        '.clj': 'clojure',
        '.vim': 'vim',
        '.el': 'elisp',
        '.lisp': 'lisp',
        '.pl': 'perl',
        '.pm': 'perl',
        
        # Build files
        '.gradle': 'gradle',
        '.cmake': 'cmake',
        '.make': 'make',
        '.mk': 'make',
        'Makefile': 'make',
        'Dockerfile': 'dockerfile',
        '.dockerfile': 'dockerfile',
        
        # Documentation
        '.tex': 'latex',
        '.bib': 'bibtex',
    }
    
    # Create generic chunkers for each file type
    for ext, lang in additional_extensions.items():
        # Create a custom chunker class for this language
        class_name = f"{lang.capitalize()}Chunker"
        
        # Dynamically create a chunker class
        chunker_class = type(class_name, (GenericChunker,), {
            '__init__': lambda self, lang=lang: (
                super(type(self), self).__init__(),
                setattr(self, 'language_name', lang)
            )
        })
        
        # Register the chunker
        extensions = [ext] if ext.startswith('.') else []
        ChunkerFactory.register_chunker(lang, chunker_class, extensions=extensions)
    
    # Print summary
    print(f"Successfully registered {len(additional_extensions)} additional file types")
    print(f"\nTotal supported extensions: {len(ChunkerFactory.get_supported_extensions())}")
    print(f"Supported extensions: {sorted(ChunkerFactory.get_supported_extensions())}")

if __name__ == "__main__":
    extend_supported_file_types()