# src/mcp_memory_service/models/code.py
"""
Code chunk models that integrate with existing Memory system.
Enhanced for ConnectivityTestingTool MCP Code Intelligence project.
"""
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import time
from datetime import datetime

# Import from existing memory system
from .memory import Memory
from ..utils.hashing import generate_content_hash
from ..security.analyzer import security_analyzer

@dataclass
class CodeChunk:
    """Represents a semantic code chunk that can be stored as Memory."""
    chunk_id: str
    file_path: str
    language: str
    text: str
    sha256: str
    start_line: int
    end_line: int
    chunk_type: str  # function, class, module, method, interface, struct, enum
    context: Optional[str] = None  # parent class/module context
    repository: Optional[str] = None
    branch: Optional[str] = None
    complexity_score: Optional[int] = None
    security_issues: Optional[List[str]] = None
    
    @classmethod
    def create(cls, file_path: str, language: str, text: str, 
               start_line: int, end_line: int, chunk_type: str,
               context: str = None, repository: str = None) -> 'CodeChunk':
        """Factory method to create a CodeChunk with generated IDs and security analysis."""
        content_hash = generate_content_hash(text, {
            'file_path': file_path,
            'language': language,
            'chunk_type': chunk_type,
            'start_line': start_line,
            'end_line': end_line
        })
        
        # Create readable chunk ID
        filename = file_path.split('/')[-1] if '/' in file_path else file_path
        chunk_id = f"{filename}:{start_line}-{end_line}:{content_hash[:8]}"
        
        # Perform security analysis
        security_issues = security_analyzer.analyze_code(text, language)
        
        return cls(
            chunk_id=chunk_id,
            file_path=file_path,
            language=language,
            text=text,
            sha256=content_hash,
            start_line=start_line,
            end_line=end_line,
            chunk_type=chunk_type,
            context=context,
            repository=repository,
            security_issues=security_issues if security_issues else None
        )
    
    def to_memory(self) -> Memory:
        """Convert CodeChunk to Memory object for storage in existing system."""
        # Create enriched content for better semantic search
        content_parts = []
        
        # Add context information
        if self.context:
            content_parts.append(f"Context: {self.context}")
        
        # Add metadata for search
        content_parts.extend([
            f"File: {self.file_path}",
            f"Language: {self.language}", 
            f"Type: {self.chunk_type}",
            f"Lines {self.start_line}-{self.end_line}:",
            ""  # Empty line before code
        ])
        
        # Add the actual code
        content_parts.append(self.text)
        
        # Join all parts
        enriched_content = "\n".join(content_parts)
        
        # Generate tags for efficient filtering
        tags = [
            "code",  # Primary tag for all code chunks
            self.language.lower(),
            self.chunk_type.lower(),
            f"file:{self.file_path.split('/')[-1]}"  # filename tag
        ]
        
        # Add repository tag if specified
        if self.repository:
            tags.append(f"repo:{self.repository}")
        
        # Add complexity tag if calculated
        if self.complexity_score:
            if self.complexity_score > 10:
                tags.append("complexity:high")
            elif self.complexity_score > 5:
                tags.append("complexity:medium")
            else:
                tags.append("complexity:low")
        
        # Add security tags if issues found
        if self.security_issues:
            tags.append("security:issues")
            for issue in self.security_issues[:3]:  # Limit to first 3
                if hasattr(issue, 'issue_type'):  # SecurityIssue object
                    tags.append(f"security:{issue.issue_type}")
                else:  # String
                    tags.append(f"security:{issue}")
        
        # Create comprehensive metadata, filtering out None values for ChromaDB compatibility
        metadata = {
            "code_chunk": True,
            "chunk_id": self.chunk_id,
            "file_path": self.file_path,
            "language": self.language,
            "chunk_type": self.chunk_type,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "line_count": self.end_line - self.start_line + 1,
            "tags": ",".join(tags),
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        
        # Add optional fields only if they have values
        if self.context:
            metadata["context"] = self.context
        if self.repository:
            metadata["repository"] = self.repository
        if self.branch:
            metadata["branch"] = self.branch
        if self.complexity_score is not None:
            metadata["complexity_score"] = self.complexity_score
        if self.security_issues:
            # Store security issues as JSON string for ChromaDB compatibility
            import json
            if hasattr(self.security_issues[0], 'issue_type'):  # SecurityIssue objects
                security_data = []
                for issue in self.security_issues:
                    security_data.append({
                        'type': issue.issue_type,
                        'severity': issue.severity.value if hasattr(issue.severity, 'value') else str(issue.severity),
                        'description': issue.message,
                        'line': issue.line_number,
                        'recommendation': issue.recommendation
                    })
                # Serialize to JSON string for ChromaDB
                metadata["security_issues"] = json.dumps(security_data)
            else:  # Backwards compatibility with strings
                metadata["security_issues"] = ",".join(self.security_issues)
        
        # Create Memory object using existing infrastructure
        now = time.time()
        return Memory(
            content=enriched_content,
            content_hash=self.sha256,
            tags=tags,
            memory_type="code_chunk",
            metadata=metadata,
            created_at=now,
            created_at_iso=datetime.utcfromtimestamp(now).isoformat() + "Z"
        )
    
    @classmethod
    def from_memory(cls, memory: Memory) -> Optional['CodeChunk']:
        """Convert Memory back to CodeChunk if it represents code."""
        if memory.memory_type != "code_chunk" or not memory.metadata.get("code_chunk"):
            return None
        
        metadata = memory.metadata
        
        # Extract code text from enriched content
        code_text = cls._extract_code_from_content(memory.content)
        
        return cls(
            chunk_id=metadata["chunk_id"],
            file_path=metadata["file_path"],
            language=metadata["language"],
            text=code_text,
            sha256=memory.content_hash,
            start_line=metadata["start_line"],
            end_line=metadata["end_line"],
            chunk_type=metadata["chunk_type"],
            context=metadata.get("context"),
            repository=metadata.get("repository"),
            branch=metadata.get("branch"),
            complexity_score=metadata.get("complexity_score"),
            security_issues=metadata.get("security_issues")
        )
    
    @staticmethod
    def _extract_code_from_content(content: str) -> str:
        """Extract just the code portion from enriched content."""
        lines = content.split('\n')
        
        # Find where the actual code starts (after metadata and empty line)
        code_start = 0
        for i, line in enumerate(lines):
            if line.strip() == "" and i > 0:
                # Found empty line, code starts after this
                code_start = i + 1
                break
        
        if code_start < len(lines):
            return '\n'.join(lines[code_start:])
        
        # Fallback: return last part if no empty line found
        return lines[-1] if lines else ""
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of this code chunk for display."""
        return {
            "chunk_id": self.chunk_id,
            "file": self.file_path.split('/')[-1],
            "language": self.language,
            "type": self.chunk_type,
            "lines": f"{self.start_line}-{self.end_line}",
            "line_count": self.end_line - self.start_line + 1,
            "context": self.context,
            "repository": self.repository,
            "complexity": self.complexity_score,
            "has_security_issues": bool(self.security_issues)
        }

@dataclass
class RepositoryMetadata:
    """Metadata about a synchronized repository."""
    repo_path: str
    repo_name: str
    last_sync: float
    total_files: int
    total_chunks: int
    languages: Dict[str, int]  # language -> chunk count
    chunk_types: Dict[str, int]  # type -> chunk count
    branch: str = "main"
    sync_type: str = "full"  # full, incremental
    sync_duration: float = 0.0
    failed_files: List[str] = None
    
    def __post_init__(self):
        if self.failed_files is None:
            self.failed_files = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RepositoryMetadata':
        """Create from dictionary."""
        return cls(**data)
    
    def get_stats_summary(self) -> Dict[str, Any]:
        """Get statistics summary for display."""
        total_chunks = self.total_chunks
        
        return {
            "repository": self.repo_name,
            "last_sync": datetime.fromtimestamp(self.last_sync).isoformat(),
            "total_files": self.total_files,
            "total_chunks": total_chunks,
            "sync_type": self.sync_type,
            "sync_duration": f"{self.sync_duration:.2f}s",
            "languages": self.languages,
            "chunk_types": self.chunk_types,
            "failed_files": len(self.failed_files),
            "branch": self.branch
        }

def detect_language_from_extension(file_path: str) -> str:
    """Detect programming language from file extension."""
    extension_map = {
        '.py': 'python',
        '.pyw': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.mjs': 'javascript',
        '.go': 'go',
        '.rs': 'rust',
        '.java': 'java',
        '.kt': 'kotlin',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.c': 'c',
        '.h': 'c',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.php': 'php',
        '.rb': 'ruby',
        '.swift': 'swift',
        '.m': 'objective-c',
        '.scala': 'scala',
        '.clj': 'clojure',
        '.hs': 'haskell',
        '.ml': 'ocaml',
        '.fs': 'fsharp'
    }
    
    # Extract extension
    if '.' in file_path:
        ext = '.' + file_path.split('.')[-1].lower()
        return extension_map.get(ext, 'unknown')
    
    return 'unknown'