# src/mcp_memory_service/code_intelligence/chunker/rust_chunker.py
"""
Rust language chunker for extracting semantic code chunks.
Enhanced for ConnectivityTestingTool MCP Code Intelligence project.
"""

import re
from typing import List, Optional, Tuple
from .base import ChunkerBase
from ...models.code import CodeChunk


class RustChunker(ChunkerBase):
    """Chunker for Rust programming language using regex-based parsing."""
    
    def __init__(self):
        super().__init__()
        self.language = "rust"
        
        # Rust-specific patterns for different constructs
        self.patterns = {
            # Functions: pub fn, async fn, const fn, unsafe fn
            'function': [
                r'^\s*(?:pub\s+)?(?:async\s+)?(?:const\s+)?(?:unsafe\s+)?fn\s+(\w+)\s*(?:<[^>]*>)?\s*\([^)]*\)(?:\s*->\s*[^{]+)?\s*\{',
                r'^\s*(?:pub\s+)?(?:async\s+)?(?:const\s+)?(?:unsafe\s+)?extern\s+"C"\s+fn\s+(\w+)\s*\([^)]*\)(?:\s*->\s*[^{]+)?\s*\{',
            ],
            
            # Structs: pub struct, struct with generics
            'struct': [
                r'^\s*(?:pub\s+)?struct\s+(\w+)(?:<[^>]*>)?\s*\{',
                r'^\s*(?:pub\s+)?struct\s+(\w+)(?:<[^>]*>)?\s*\([^)]*\)\s*;',  # Tuple structs
            ],
            
            # Enums: pub enum, enum with generics
            'enum': [
                r'^\s*(?:pub\s+)?enum\s+(\w+)(?:<[^>]*>)?\s*\{',
            ],
            
            # Traits: pub trait, trait with generics
            'trait': [
                r'^\s*(?:pub\s+)?(?:unsafe\s+)?trait\s+(\w+)(?:<[^>]*>)?(?:\s*:\s*[^{]+)?\s*\{',
            ],
            
            # Implementations: impl blocks
            'impl': [
                r'^\s*impl(?:<[^>]*>)?\s+(?:(\w+)(?:<[^>]*>)?(?:\s+for\s+(\w+)(?:<[^>]*>)?)?|\s*(\w+)(?:<[^>]*>)?)\s*\{',
            ],
            
            # Modules: pub mod, mod
            'module': [
                r'^\s*(?:pub\s+)?mod\s+(\w+)\s*\{',
            ],
            
            # Constants: pub const, const
            'constant': [
                r'^\s*(?:pub\s+)?const\s+(\w+)\s*:\s*[^=]+=',
            ],
            
            # Static variables: pub static, static
            'static': [
                r'^\s*(?:pub\s+)?static\s+(?:mut\s+)?(\w+)\s*:\s*[^=]+=',
            ],
            
            # Type aliases: pub type, type
            'type_alias': [
                r'^\s*(?:pub\s+)?type\s+(\w+)(?:<[^>]*>)?\s*=',
            ],
            
            # Macros: macro_rules!
            'macro': [
                r'^\s*(?:pub\s+)?macro_rules!\s+(\w+)\s*\{',
            ],
        }
    
    def chunk_content(self, content: str, file_path: str, repository: str) -> List[CodeChunk]:
        """Chunk Rust content into semantic pieces."""
        lines = content.split('\n')
        chunks = []
        
        for construct_type, patterns in self.patterns.items():
            for pattern in patterns:
                chunks.extend(self._find_constructs(lines, pattern, construct_type, file_path, repository))
        
        # Sort chunks by start line
        chunks.sort(key=lambda x: x.start_line)
        
        # Remove overlapping chunks (keep the more specific one)
        chunks = self._remove_overlaps(chunks)
        
        return chunks
    
    def _find_constructs(self, lines: List[str], pattern: str, construct_type: str, 
                        file_path: str, repository: str) -> List[CodeChunk]:
        """Find all constructs matching the given pattern."""
        chunks = []
        
        for line_num, line in enumerate(lines, 1):
            match = re.match(pattern, line)
            if match:
                # Extract construct name
                name = None
                for group in match.groups():
                    if group:
                        name = group
                        break
                
                if not name:
                    name = f"anonymous_{construct_type}"
                
                # Find the end of this construct
                end_line = self._find_construct_end(lines, line_num - 1)
                
                if end_line > line_num:
                    # Extract the actual code
                    code_lines = lines[line_num - 1:end_line]
                    code_text = '\n'.join(code_lines)
                    
                    # Calculate complexity (rough estimate)
                    complexity = self._calculate_complexity(code_text)
                    
                    # Extract context (preceding comments and attributes)
                    context = self._extract_context(lines, line_num - 1)
                    
                    chunk = CodeChunk.create(
                        file_path=file_path,
                        language=self.language,
                        text=code_text,
                        start_line=line_num,
                        end_line=end_line,
                        chunk_type=construct_type,
                        context=context,
                        repository=repository
                    )
                    chunk.complexity_score = complexity
                    chunks.append(chunk)
        
        return chunks
    
    def _find_construct_end(self, lines: List[str], start_line: int) -> int:
        """Find the closing brace for a construct starting at start_line."""
        if start_line >= len(lines):
            return start_line + 1
        
        brace_count = 0
        in_string = False
        in_char = False
        in_comment = False
        
        for i, line in enumerate(lines[start_line:], start_line):
            line_content = line
            j = 0
            
            while j < len(line_content):
                char = line_content[j]
                
                # Handle block comments
                if not in_string and not in_char and j < len(line_content) - 1:
                    if line_content[j:j+2] == '/*':
                        in_comment = True
                        j += 2
                        continue
                    elif line_content[j:j+2] == '*/' and in_comment:
                        in_comment = False
                        j += 2
                        continue
                
                # Handle line comments
                if not in_string and not in_char and not in_comment and j < len(line_content) - 1:
                    if line_content[j:j+2] == '//':
                        break  # Rest of line is comment
                
                if in_comment:
                    j += 1
                    continue
                
                # Handle string literals
                if char == '"' and not in_char:
                    if not in_string:
                        in_string = True
                    elif j == 0 or line_content[j-1] != '\\':
                        in_string = False
                
                # Handle character literals
                elif char == "'" and not in_string:
                    if not in_char:
                        in_char = True
                    elif j == 0 or line_content[j-1] != '\\':
                        in_char = False
                
                # Count braces only when not in strings or comments
                elif not in_string and not in_char and not in_comment:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            return i + 1
                
                j += 1
            
            # Reset string/char state at end of line (except for multi-line strings)
            if not in_comment:
                in_char = False
        
        # If we didn't find a closing brace, return the last line
        return len(lines)
    
    def _extract_context(self, lines: List[str], start_line: int) -> Optional[str]:
        """Extract context (comments and attributes) before the construct."""
        context_lines = []
        
        # Look backward for comments and attributes
        for i in range(start_line - 1, -1, -1):
            line = lines[i].strip()
            
            # Skip empty lines at the beginning of context
            if not line and not context_lines:
                continue
            
            # Include doc comments, regular comments, and attributes
            if (line.startswith('///') or 
                line.startswith('//!') or 
                line.startswith('//') or
                line.startswith('#[') or
                line.startswith('#![')):
                context_lines.insert(0, lines[i])
            elif not line:
                # Empty line within context
                context_lines.insert(0, lines[i])
            else:
                # Hit non-comment, non-attribute line
                break
        
        return '\n'.join(context_lines) if context_lines else None
    
    def _calculate_complexity(self, code: str) -> int:
        """Calculate a rough complexity score for the code."""
        complexity = 1  # Base complexity
        
        # Keywords that increase complexity
        complexity_keywords = [
            'if', 'else', 'elif', 'match', 'while', 'for', 'loop',
            'try', 'catch', '?', 'unwrap', 'expect'
        ]
        
        for keyword in complexity_keywords:
            # Use word boundaries to avoid partial matches
            pattern = r'\b' + re.escape(keyword) + r'\b'
            complexity += len(re.findall(pattern, code))
        
        # Function calls add minor complexity
        complexity += len(re.findall(r'\w+\s*\(', code)) * 0.1
        
        # Nested braces add complexity
        complexity += code.count('{') * 0.5
        
        return int(complexity)
    
    def _remove_overlaps(self, chunks: List[CodeChunk]) -> List[CodeChunk]:
        """Remove overlapping chunks, keeping the more specific ones."""
        if not chunks:
            return chunks
        
        filtered_chunks = []
        
        for i, chunk in enumerate(chunks):
            is_overlapped = False
            
            for j, other_chunk in enumerate(chunks):
                if i == j:
                    continue
                
                # Check if current chunk is completely contained within another
                if (other_chunk.start_line <= chunk.start_line and 
                    other_chunk.end_line >= chunk.end_line):
                    
                    # Prefer more specific types (functions over modules, etc.)
                    specificity_order = ['function', 'method', 'struct', 'enum', 'trait', 'impl', 
                                       'constant', 'static', 'type_alias', 'macro', 'module']
                    
                    try:
                        chunk_specificity = specificity_order.index(chunk.chunk_type)
                        other_specificity = specificity_order.index(other_chunk.chunk_type)
                        
                        if other_specificity <= chunk_specificity:
                            is_overlapped = True
                            break
                    except ValueError:
                        # If type not in list, keep both
                        pass
            
            if not is_overlapped:
                filtered_chunks.append(chunk)
        
        return filtered_chunks
    
    def get_supported_extensions(self) -> List[str]:
        """Return list of file extensions this chunker supports."""
        return ['.rs']
    
    def estimate_chunks(self, content: str) -> int:
        """Estimate the number of chunks this content will produce."""
        chunk_count = 0
        
        for patterns in self.patterns.values():
            for pattern in patterns:
                chunk_count += len(re.findall(pattern, content, re.MULTILINE))
        
        return max(1, chunk_count)  # At least 1 chunk per file