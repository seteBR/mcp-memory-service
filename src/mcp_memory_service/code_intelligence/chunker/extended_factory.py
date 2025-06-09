"""
Extended factory with support for more file types.
"""
from .factory import ChunkerFactory
from .base import GenericChunker


def initialize_extended_file_support():
    """Initialize support for additional file types."""
    
    # Additional file types that should be supported
    additional_extensions = {
        # Documentation
        '.md': 'markdown',
        '.rst': 'restructuredtext', 
        '.txt': 'text',
        
        # Configuration
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml',
        '.toml': 'toml',
        '.ini': 'ini',
        '.cfg': 'config',
        '.conf': 'config',
        
        # Web
        '.html': 'html',
        '.xml': 'xml',
        '.css': 'css',
        
        # Shell
        '.sh': 'shell',
        '.bash': 'bash',
        '.bat': 'batch',
        '.ps1': 'powershell',
        
        # Common languages not yet supported
        '.java': 'java',
        '.c': 'c',
        '.cpp': 'cpp',
        '.h': 'c_header',
        '.hpp': 'cpp_header',
        '.cs': 'csharp',
        '.rb': 'ruby',
        '.php': 'php',
        '.swift': 'swift',
        '.kt': 'kotlin',
        '.scala': 'scala',
        '.r': 'r',
        '.sql': 'sql',
        
        # Build files
        'Dockerfile': 'dockerfile',
        '.dockerfile': 'dockerfile',
    }
    
    # Register each extension
    for ext, lang in additional_extensions.items():
        # Create a language-specific chunker dynamically
        chunker_class = type(
            f"{lang.capitalize().replace('_', '')}Chunker",
            (GenericChunker,),
            {
                '__init__': lambda self, lang=lang: (
                    super(type(self), self).__init__(),
                    setattr(self, 'language_name', lang)
                )
            }
        )
        
        # Register with factory
        extensions = [ext] if ext.startswith('.') else []
        ChunkerFactory.register_chunker(lang, chunker_class, extensions=extensions)


# Don't initialize on import to avoid circular dependencies
# Call initialize_extended_file_support() explicitly when needed