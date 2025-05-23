"""
Python code chunker using AST parsing.
"""
import ast
import re
from typing import List, Optional, Tuple
from pathlib import Path

from .base import ChunkerBase
from ...models.code import CodeChunk

class PythonChunker(ChunkerBase):
    """Python code chunker with AST-aware parsing."""
    
    def __init__(self):
        super().__init__()
        self.language_name = "python"
        self.supported_extensions = {'.py', '.pyw'}
    
    def chunk_content(self, content: str, file_path: str, 
                     repository: str = None) -> List[CodeChunk]:
        """Parse Python content into semantic chunks."""
        if not content.strip():
            return []
        
        try:
            return self._chunk_with_ast(content, file_path, repository)
        except SyntaxError:
            # Fall back to regex if AST parsing fails
            return self._chunk_with_regex(content, file_path, repository)
    
    def _chunk_with_ast(self, content: str, file_path: str, 
                       repository: str) -> List[CodeChunk]:
        """Use AST for precise Python parsing."""
        chunks = []
        lines = content.splitlines()
        
        tree = ast.parse(content)
        
        def extract_chunks(node: ast.AST, context: str = ""):
            """Recursively extract chunks from AST nodes."""
            
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunk = self._create_chunk_from_node(
                    node, lines, file_path, repository, "function", context
                )
                chunks.append(chunk)
            
            elif isinstance(node, ast.ClassDef):
                class_chunk = self._create_chunk_from_node(
                    node, lines, file_path, repository, "class", context
                )
                chunks.append(class_chunk)
                
                # Update context for nested items
                class_name = node.name
                new_context = f"{context}.{class_name}" if context else class_name
                
                # Process class methods
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_chunk = self._create_chunk_from_node(
                            child, lines, file_path, repository, "method", new_context
                        )
                        chunks.append(method_chunk)
            
            # Process child nodes for nested structures
            for child in ast.iter_child_nodes(node):
                extract_chunks(child, context)
        
        extract_chunks(tree)
        return chunks
    
    def _create_chunk_from_node(self, node: ast.AST, lines: List[str], 
                               file_path: str, repository: str, 
                               chunk_type: str, context: str) -> CodeChunk:
        """Create a CodeChunk from an AST node."""
        start_line = node.lineno
        end_line = node.end_lineno or start_line
        
        # Extract the text for this node
        chunk_lines = lines[start_line-1:end_line]
        text = '\n'.join(chunk_lines)
        
        return CodeChunk.create(
            file_path=file_path,
            language=self.language_name,
            text=text,
            start_line=start_line,
            end_line=end_line,
            chunk_type=chunk_type,
            context=context,
            repository=repository
        )
    
    def _chunk_with_regex(self, content: str, file_path: str, 
                         repository: str) -> List[CodeChunk]:
        """Fallback regex-based chunking for when AST isn't available."""
        chunks = []
        lines = content.splitlines()
        
        # Pattern to match function and class definitions
        patterns = [
            (r'^(async\s+)?def\s+(\w+)\s*\(', 'function'),
            (r'^class\s+(\w+)(?:\([^)]*\))?\s*:', 'class')
        ]
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            for pattern, chunk_type in patterns:
                match = re.match(pattern, line.strip())
                if match:
                    start_line = i + 1
                    
                    # Find the end of this definition
                    end_line = self._find_definition_end(lines, i)
                    
                    chunk_text = '\n'.join(lines[i:end_line])
                    
                    chunks.append(CodeChunk.create(
                        file_path=file_path,
                        language=self.language_name,
                        text=chunk_text,
                        start_line=start_line,
                        end_line=end_line,
                        chunk_type=chunk_type,
                        repository=repository
                    ))
                    
                    i = end_line - 1  # Skip to end of definition
                    break
            
            i += 1
        
        return chunks
    
    def _find_definition_end(self, lines: List[str], start_idx: int) -> int:
        """Find the end line of a function or class definition."""
        if start_idx >= len(lines):
            return len(lines)
        
        # Get the indentation of the definition line
        def_line = lines[start_idx]
        base_indent = len(def_line) - len(def_line.lstrip())
        
        # Look for the next line with same or less indentation
        i = start_idx + 1
        while i < len(lines):
            line = lines[i]
            
            # Skip empty lines and comments
            if not line.strip() or line.strip().startswith('#'):
                i += 1
                continue
            
            # Check indentation
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent:
                break
            
            i += 1
        
        return i