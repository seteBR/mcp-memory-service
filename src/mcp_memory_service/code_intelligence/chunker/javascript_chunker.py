# src/mcp_memory_service/code_intelligence/chunker/javascript_chunker.py
"""
JavaScript/TypeScript code chunker using regex patterns and basic AST parsing.
Enhanced for ConnectivityTestingTool MCP Code Intelligence project.
"""
import re
import logging
from typing import List, Dict, Optional
from .base import ChunkerBase
from ...models.code import CodeChunk

class JavaScriptChunker(ChunkerBase):
    """Chunker for JavaScript and TypeScript files."""
    
    SUPPORTED_EXTENSIONS = {'.js', '.jsx', '.ts', '.tsx', '.mjs'}
    
    def __init__(self):
        super().__init__()
        self.supported_extensions = {'.js', '.jsx', '.ts', '.tsx', '.mjs'}
        self.language_name = "javascript"
        self.logger = logging.getLogger(__name__)
        
        # Regex patterns for different JavaScript/TypeScript constructs
        self.patterns = {
            'function': [
                # Function declarations: function name() {}
                r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\([^)]*\)\s*{',
                # Arrow functions: const name = () => {}
                r'(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>\s*{',
                # Method definitions: methodName() {}
                r'(?:async\s+)?(\w+)\s*\([^)]*\)\s*{',
            ],
            'class': [
                # Class declarations: class ClassName {}
                r'(?:export\s+)?(?:default\s+)?class\s+(\w+)(?:\s+extends\s+\w+)?\s*{',
            ],
            'interface': [
                # TypeScript interfaces: interface Name {}
                r'(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+[\w,\s]+)?\s*{',
            ],
            'type': [
                # TypeScript type aliases: type Name = 
                r'(?:export\s+)?type\s+(\w+)\s*=',
            ],
            'enum': [
                # TypeScript enums: enum Name {}
                r'(?:export\s+)?enum\s+(\w+)\s*{',
            ],
            'const': [
                # Exported constants: export const NAME = 
                r'(?:export\s+)?const\s+(\w+)\s*=',
            ]
        }
    
    def chunk_content(self, content: str, file_path: str, repository: str) -> List[CodeChunk]:
        """Chunk JavaScript/TypeScript content into semantic pieces."""
        try:
            chunks = []
            lines = content.split('\n')
            
            # Try to find functions, classes, interfaces, etc.
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
            self.logger.error(f"Error chunking JavaScript/TypeScript content: {e}")
            # Fallback to generic chunking
            return self._generic_chunk_fallback(content, file_path, repository)
    
    def _find_chunks_by_patterns(self, content: str, lines: List[str], patterns: List[str], 
                                chunk_type: str, file_path: str, repository: str) -> List[CodeChunk]:
        """Find code chunks using regex patterns."""
        chunks = []
        
        for pattern in patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                name = match.group(1) if match.groups() else "anonymous"
                start_pos = match.start()
                
                # Find the line number
                start_line = content[:start_pos].count('\n') + 1
                
                # Find the end of this construct by matching braces
                end_line = self._find_closing_brace(lines, start_line - 1)
                
                if end_line > start_line:
                    # Extract the code text
                    code_lines = lines[start_line - 1:end_line]
                    code_text = '\n'.join(code_lines)
                    
                    # Skip very small chunks (likely false positives)
                    if len(code_lines) < 2:
                        continue
                    
                    # Create context information
                    context = self._extract_context(lines, start_line - 1, file_path)
                    
                    chunk = CodeChunk.create(
                        file_path=file_path,
                        language=self._detect_js_variant(file_path),
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
                if not in_string and char in ['"', "'", '`']:
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
                if j < len(line) - 1:
                    if line[j:j+2] == '//':
                        break  # Rest of line is comment
                    elif line[j:j+2] == '/*':
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
    
    def _extract_context(self, lines: List[str], start_line: int, file_path: str) -> Optional[str]:
        """Extract context information (parent class, namespace, etc.)."""
        # Look backwards for class or namespace declarations
        for i in range(start_line - 1, max(0, start_line - 20), -1):
            line = lines[i].strip()
            
            # Check for class declaration
            class_match = re.search(r'(?:export\s+)?(?:default\s+)?class\s+(\w+)', line)
            if class_match:
                return f"class {class_match.group(1)}"
            
            # Check for namespace or module
            namespace_match = re.search(r'(?:export\s+)?(?:namespace|module)\s+(\w+)', line)
            if namespace_match:
                return f"namespace {namespace_match.group(1)}"
        
        return None
    
    def _detect_js_variant(self, file_path: str) -> str:
        """Detect specific JavaScript variant from file extension."""
        ext = file_path.split('.')[-1].lower()
        variant_map = {
            'ts': 'typescript',
            'tsx': 'typescript',
            'jsx': 'javascript',
            'mjs': 'javascript',
            'js': 'javascript'
        }
        return variant_map.get(ext, 'javascript')
    
    def _estimate_complexity(self, code: str) -> int:
        """Estimate cyclomatic complexity of JavaScript/TypeScript code."""
        complexity = 1  # Base complexity
        
        # Count decision points
        complexity_patterns = [
            r'\bif\s*\(',           # if statements
            r'\belse\s+if\s*\(',    # else if
            r'\bwhile\s*\(',        # while loops
            r'\bfor\s*\(',          # for loops
            r'\bswitch\s*\(',       # switch statements
            r'\bcase\s+',           # case statements
            r'\bcatch\s*\(',        # try-catch
            r'\?\s*.*?\s*:',        # ternary operators
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
        
        # Sort by start line, then by specificity (functions > classes > constants)
        type_priority = {
            'function': 1,
            'class': 2,
            'interface': 3,
            'enum': 4,
            'type': 5,
            'const': 6
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
        
        # Split into chunks of reasonable size (50 lines each)
        chunk_size = 50
        for i in range(0, len(lines), chunk_size):
            end_idx = min(i + chunk_size, len(lines))
            chunk_lines = lines[i:end_idx]
            chunk_text = '\n'.join(chunk_lines)
            
            if chunk_text.strip():  # Skip empty chunks
                chunk = CodeChunk.create(
                    file_path=file_path,
                    language=self._detect_js_variant(file_path),
                    text=chunk_text,
                    start_line=i + 1,
                    end_line=end_idx,
                    chunk_type='code_block',
                    repository=repository
                )
                chunks.append(chunk)
        
        return chunks