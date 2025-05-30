# src/mcp_memory_service/code_intelligence/chunker/go_chunker.py
"""
Go language code chunker using regex patterns.
Enhanced for ConnectivityTestingTool MCP Code Intelligence project.
"""
import re
import logging
from typing import List, Dict, Optional
from .base import ChunkerBase
from ...models.code import CodeChunk

class GoChunker(ChunkerBase):
    """Chunker for Go language files."""
    
    def __init__(self):
        super().__init__()
        self.supported_extensions = {'.go'}
        self.language_name = "go"
        self.logger = logging.getLogger(__name__)
        
        # Regex patterns for Go language constructs
        self.patterns = {
            'function': [
                # Function declarations: func name() {}
                r'func\s+(\w+)\s*\([^)]*\)(?:\s*\([^)]*\))?\s*{',
                # Method declarations: func (receiver) name() {}
                r'func\s+\([^)]+\)\s+(\w+)\s*\([^)]*\)(?:\s*\([^)]*\))?\s*{',
            ],
            'struct': [
                # Struct declarations: type Name struct {}
                r'type\s+(\w+)\s+struct\s*{',
            ],
            'interface': [
                # Interface declarations: type Name interface {}
                r'type\s+(\w+)\s+interface\s*{',
            ],
            'type': [
                # Type aliases: type Name = OtherType
                r'type\s+(\w+)\s*=',
                # Type definitions: type Name CustomType
                r'type\s+(\w+)\s+\w+',
            ],
            'const': [
                # Const declarations: const NAME = value
                r'const\s+(\w+)\s*=',
                # Const blocks: const ( ... )
                r'const\s*\(',
            ],
            'var': [
                # Variable declarations: var name = value
                r'var\s+(\w+)\s*=',
                # Variable blocks: var ( ... )
                r'var\s*\(',
            ]
        }
    
    def chunk_content(self, content: str, file_path: str, repository: str) -> List[CodeChunk]:
        """Chunk Go content into semantic pieces."""
        try:
            chunks = []
            lines = content.split('\n')
            
            # Find functions, structs, interfaces, etc.
            for chunk_type, patterns in self.patterns.items():
                chunks.extend(self._find_chunks_by_patterns(
                    content, lines, patterns, chunk_type, file_path, repository
                ))
            
            # Sort chunks by start line to maintain order
            chunks.sort(key=lambda x: x.start_line)
            
            # Remove overlapping chunks (keep the more specific one)
            chunks = self._remove_overlapping_chunks(chunks)
            
            return chunks
            
        except Exception as e:
            self.logger.error(f"Error chunking Go content: {e}")
            # Fallback to generic chunking
            return self._generic_chunk_fallback(content, file_path, repository)
    
    def _find_chunks_by_patterns(self, content: str, lines: List[str], patterns: List[str], 
                                chunk_type: str, file_path: str, repository: str) -> List[CodeChunk]:
        """Find code chunks using regex patterns."""
        chunks = []
        
        for pattern in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                if match.groups():
                    name = match.group(1)
                else:
                    name = f"anonymous_{chunk_type}"
                
                start_pos = match.start()
                
                # Find the line number
                start_line = content[:start_pos].count('\n') + 1
                
                # Find the end of this construct
                if chunk_type in ['function', 'struct', 'interface']:
                    # Find closing brace
                    end_line = self._find_closing_brace(lines, start_line - 1)
                elif chunk_type in ['const', 'var'] and '(' in match.group(0):
                    # Find closing parenthesis for blocks
                    end_line = self._find_closing_paren(lines, start_line - 1)
                else:
                    # Single line declaration
                    end_line = start_line
                
                if end_line > start_line:
                    # Extract the code text
                    code_lines = lines[start_line - 1:end_line]
                    code_text = '\n'.join(code_lines)
                    
                    # Skip very small chunks (likely false positives)
                    if len(code_lines) < 1:
                        continue
                    
                    # Create context information
                    context = self._extract_context(lines, start_line - 1, file_path)
                    
                    chunk = CodeChunk.create(
                        file_path=file_path,
                        language='go',
                        text=code_text,
                        start_line=start_line,
                        end_line=end_line,
                        chunk_type=chunk_type,
                        context=context,
                        repository=repository
                    )
                    
                    # Add complexity estimation
                    chunk.complexity_score = self._estimate_complexity(code_text)
                    
                    chunks.append(chunk)
        
        return chunks
    
    def _find_closing_brace(self, lines: List[str], start_line: int) -> int:
        """Find the closing brace for a code block starting at start_line."""
        if start_line >= len(lines):
            return start_line + 1
        
        brace_count = 0
        in_string = False
        string_char = None
        
        for i in range(start_line, len(lines)):
            line = lines[i]
            
            j = 0
            while j < len(line):
                char = line[j]
                
                # Handle string literals
                if not in_string and char in ['"', '`']:
                    in_string = True
                    string_char = char
                elif in_string and char == string_char:
                    # Check if it's escaped
                    if j == 0 or line[j-1] != '\\':
                        in_string = False
                        string_char = None
                
                # Skip characters inside strings
                if in_string:
                    j += 1
                    continue
                
                # Handle comments
                if j < len(line) - 1 and line[j:j+2] == '//':
                    break  # Rest of line is comment
                elif j < len(line) - 1 and line[j:j+2] == '/*':
                    # Find end of block comment
                    comment_end = line.find('*/', j + 2)
                    if comment_end != -1:
                        j = comment_end + 2
                        continue
                    else:
                        # Comment continues to next line
                        break
                
                # Count braces
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        return i + 1  # Return 1-based line number
                
                j += 1
        
        # If we didn't find a closing brace, return a reasonable end
        return min(start_line + 50, len(lines))
    
    def _find_closing_paren(self, lines: List[str], start_line: int) -> int:
        """Find the closing parenthesis for a block starting at start_line."""
        if start_line >= len(lines):
            return start_line + 1
        
        paren_count = 0
        in_string = False
        string_char = None
        
        for i in range(start_line, len(lines)):
            line = lines[i]
            
            for j, char in enumerate(line):
                # Handle string literals
                if not in_string and char in ['"', '`']:
                    in_string = True
                    string_char = char
                elif in_string and char == string_char:
                    if j == 0 or line[j-1] != '\\':
                        in_string = False
                        string_char = None
                
                # Skip characters inside strings
                if in_string:
                    continue
                
                # Handle comments
                if j < len(line) - 1 and line[j:j+2] == '//':
                    break
                
                # Count parentheses
                if char == '(':
                    paren_count += 1
                elif char == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        return i + 1
        
        return min(start_line + 20, len(lines))
    
    def _extract_context(self, lines: List[str], start_line: int, file_path: str) -> Optional[str]:
        """Extract context information (package, struct, etc.)."""
        context_parts = []
        
        # Look for package declaration
        for i in range(min(20, len(lines))):
            line = lines[i].strip()
            package_match = re.search(r'package\s+(\w+)', line)
            if package_match:
                context_parts.append(f"package {package_match.group(1)}")
                break
        
        # Look backwards for struct or interface containing this method
        for i in range(start_line - 1, max(0, start_line - 20), -1):
            line = lines[i].strip()
            
            # Check for struct declaration
            struct_match = re.search(r'type\s+(\w+)\s+struct', line)
            if struct_match:
                context_parts.append(f"struct {struct_match.group(1)}")
                break
            
            # Check for interface declaration
            interface_match = re.search(r'type\s+(\w+)\s+interface', line)
            if interface_match:
                context_parts.append(f"interface {interface_match.group(1)}")
                break
        
        return " - ".join(context_parts) if context_parts else None
    
    def _estimate_complexity(self, code: str) -> int:
        """Estimate cyclomatic complexity of Go code."""
        complexity = 1  # Base complexity
        
        # Count decision points
        complexity_patterns = [
            r'\bif\s+',             # if statements
            r'\belse\s+if\s+',      # else if
            r'\belse\s*{',          # else
            r'\bfor\s+',            # for loops
            r'\bswitch\s+',         # switch statements
            r'\bcase\s+',           # case statements
            r'\bselect\s*{',        # select statements
            r'\bgo\s+',             # goroutines
            r'\bdefer\s+',          # defer statements
            r'&&',                  # logical AND
            r'\|\|',                # logical OR
        ]
        
        for pattern in complexity_patterns:
            complexity += len(re.findall(pattern, code))
        
        return complexity
    
    def _remove_overlapping_chunks(self, chunks: List[CodeChunk]) -> List[CodeChunk]:
        """Remove overlapping chunks, keeping the more specific ones."""
        if not chunks:
            return chunks
        
        # Sort by start line, then by specificity
        type_priority = {
            'function': 1,
            'struct': 2,
            'interface': 3,
            'type': 4,
            'const': 5,
            'var': 6
        }
        
        chunks.sort(key=lambda x: (x.start_line, type_priority.get(x.chunk_type, 999)))
        
        filtered_chunks = []
        for chunk in chunks:
            # Check if this chunk overlaps with any already accepted chunk
            overlaps = False
            for accepted in filtered_chunks:
                if (chunk.start_line < accepted.end_line and 
                    chunk.end_line > accepted.start_line):
                    overlaps = True
                    break
            
            if not overlaps:
                filtered_chunks.append(chunk)
        
        return filtered_chunks
    
    def _generic_chunk_fallback(self, content: str, file_path: str, repository: str) -> List[CodeChunk]:
        """Fallback to generic chunking when pattern matching fails."""
        chunks = []
        lines = content.split('\n')
        
        # Split into chunks of reasonable size (40 lines each for Go)
        chunk_size = 40
        for i in range(0, len(lines), chunk_size):
            end_idx = min(i + chunk_size, len(lines))
            chunk_lines = lines[i:end_idx]
            chunk_text = '\n'.join(chunk_lines)
            
            if chunk_text.strip():  # Skip empty chunks
                chunk = CodeChunk.create(
                    file_path=file_path,
                    language='go',
                    text=chunk_text,
                    start_line=i + 1,
                    end_line=end_idx,
                    chunk_type='code_block',
                    repository=repository
                )
                chunks.append(chunk)
        
        return chunks