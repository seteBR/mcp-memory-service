# src/mcp_memory_service/security/analyzer.py
"""
Security analysis module for code intelligence system.
Detects common security patterns and potential vulnerabilities.
"""
import re
import logging
from typing import List, Dict, Any, Set, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class Severity(Enum):
    """Security issue severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class SecurityIssue:
    """Represents a security issue found in code."""
    issue_type: str
    severity: Severity
    message: str
    line_number: Optional[int] = None
    code_snippet: Optional[str] = None
    recommendation: Optional[str] = None

class SecurityAnalyzer:
    """Analyzes code for security vulnerabilities and patterns."""
    
    def __init__(self):
        self.patterns = self._initialize_patterns()
        self.secret_patterns = self._initialize_secret_patterns()
        
    def _initialize_patterns(self) -> Dict[str, List[Dict[str, Any]]]:
        """Initialize security vulnerability patterns."""
        return {
            # SQL Injection patterns
            'sql_injection': [
                {
                    'pattern': r'(execute|query|exec)\s*\(\s*["\'].*?\+.*?["\']',
                    'severity': Severity.HIGH,
                    'message': 'Potential SQL injection via string concatenation',
                    'recommendation': 'Use parameterized queries or prepared statements'
                },
                {
                    'pattern': r'(SELECT|INSERT|UPDATE|DELETE).*?\+.*?(user_input|request\.|params\.|query\.)',
                    'severity': Severity.HIGH,
                    'message': 'Potential SQL injection via dynamic query construction',
                    'recommendation': 'Use parameterized queries instead of string concatenation'
                },
                {
                    'pattern': r'(cursor\.execute|execute)\s*\(\s*f["\']',
                    'severity': Severity.MEDIUM,
                    'message': 'Potential SQL injection via f-string formatting',
                    'recommendation': 'Use parameterized queries with placeholders'
                },
                {
                    'pattern': r'f["\'].*?(SELECT|INSERT|UPDATE|DELETE).*?\{.*?\}',
                    'severity': Severity.HIGH,
                    'message': 'SQL injection via f-string with variable interpolation',
                    'recommendation': 'Use parameterized queries instead of f-strings for SQL'
                }
            ],
            
            # XSS patterns
            'xss': [
                {
                    'pattern': r'innerHTML\s*=\s*.*?\+',
                    'severity': Severity.HIGH,
                    'message': 'Potential XSS vulnerability via innerHTML',
                    'recommendation': 'Use textContent or sanitize input before setting innerHTML'
                },
                {
                    'pattern': r'document\.write\s*\(',
                    'severity': Severity.MEDIUM,
                    'message': 'Use of document.write may lead to XSS',
                    'recommendation': 'Use safer DOM manipulation methods'
                },
                {
                    'pattern': r'eval\s*\(',
                    'severity': Severity.CRITICAL,
                    'message': 'Use of eval() is dangerous and can lead to code injection',
                    'recommendation': 'Avoid eval() and use safer alternatives like JSON.parse()'
                }
            ],
            
            # Command Injection patterns
            'command_injection': [
                {
                    'pattern': r'(os\.system|subprocess\.call|exec|shell_exec)\s*\(.*?\+',
                    'severity': Severity.CRITICAL,
                    'message': 'Potential command injection via string concatenation',
                    'recommendation': 'Use subprocess with list arguments or validate/sanitize input'
                },
                {
                    'pattern': r'(system|exec|shell_exec|passthru)\s*\(\s*\$',
                    'severity': Severity.HIGH,
                    'message': 'Potential command injection via variable execution',
                    'recommendation': 'Validate and sanitize input, use safe execution methods'
                },
                {
                    'pattern': r'shell\s*=\s*True',
                    'severity': Severity.HIGH,
                    'message': 'Use of shell=True can lead to command injection',
                    'recommendation': 'Use shell=False and pass commands as list arguments'
                },
                {
                    'pattern': r'subprocess\.(run|call|Popen).*shell=True',
                    'severity': Severity.HIGH,
                    'message': 'Subprocess with shell=True is vulnerable to command injection',
                    'recommendation': 'Use shell=False and validate all input'
                }
            ],
            
            # Path Traversal patterns
            'path_traversal': [
                {
                    'pattern': r'(open|file|read|write).*?\.\./.*?\.\.',
                    'severity': Severity.HIGH,
                    'message': 'Potential path traversal vulnerability',
                    'recommendation': 'Validate file paths and use os.path.join() safely'
                },
                {
                    'pattern': r'(\.\.[\\/]){2,}',
                    'severity': Severity.MEDIUM,
                    'message': 'Suspicious path traversal pattern detected',
                    'recommendation': 'Validate and normalize file paths'
                }
            ],
            
            # Hardcoded credentials
            'hardcoded_credentials': [
                {
                    'pattern': r'(password|passwd|pwd)\s*=\s*["\'][^"\']{3,}["\']',
                    'severity': Severity.HIGH,
                    'message': 'Hardcoded password detected',
                    'recommendation': 'Use environment variables or secure credential storage'
                },
                {
                    'pattern': r'(api_key|apikey|secret|token)\s*=\s*["\'][A-Za-z0-9+/=]{10,}["\']',
                    'severity': Severity.HIGH,
                    'message': 'Hardcoded API key or secret detected',
                    'recommendation': 'Use environment variables or secure credential storage'
                }
            ],
            
            # Weak crypto patterns
            'weak_crypto': [
                {
                    'pattern': r'(md5|sha1)\s*\(',
                    'severity': Severity.MEDIUM,
                    'message': 'Weak cryptographic hash function detected',
                    'recommendation': 'Use stronger hash functions like SHA-256 or bcrypt for passwords'
                },
                {
                    'pattern': r'(des|3des|rc4)\s*',
                    'severity': Severity.HIGH,
                    'message': 'Weak encryption algorithm detected',
                    'recommendation': 'Use modern encryption algorithms like AES'
                }
            ],
            
            # Insecure random patterns
            'insecure_random': [
                {
                    'pattern': r'(Math\.random|random\.random|rand)\s*\(',
                    'severity': Severity.MEDIUM,
                    'message': 'Insecure random number generation',
                    'recommendation': 'Use cryptographically secure random generators for security purposes'
                }
            ],
            
            # Debug/logging patterns
            'debug_logging': [
                {
                    'pattern': r'(console\.log|print|println|echo|var_dump)\s*\(.*?(password|token|secret|key)',
                    'severity': Severity.MEDIUM,
                    'message': 'Potential sensitive data logging',
                    'recommendation': 'Avoid logging sensitive information'
                }
            ]
        }
    
    def _initialize_secret_patterns(self) -> List[Dict[str, Any]]:
        """Initialize patterns for detecting hardcoded secrets."""
        return [
            {
                'name': 'AWS Access Key',
                'pattern': r'AKIA[0-9A-Z]{16}',
                'severity': Severity.CRITICAL
            },
            {
                'name': 'AWS Secret Key', 
                'pattern': r'[A-Za-z0-9+/]{40}',
                'severity': Severity.CRITICAL
            },
            {
                'name': 'GitHub Token',
                'pattern': r'ghp_[A-Za-z0-9]{36}',
                'severity': Severity.HIGH
            },
            {
                'name': 'JWT Token',
                'pattern': r'eyJ[A-Za-z0-9+/=]+\.[A-Za-z0-9+/=]+\.[A-Za-z0-9+/=]+',
                'severity': Severity.HIGH
            },
            {
                'name': 'Google API Key',
                'pattern': r'AIza[0-9A-Za-z-_]{35}',
                'severity': Severity.HIGH
            },
            {
                'name': 'Private Key',
                'pattern': r'-----BEGIN (RSA|DSA|EC) PRIVATE KEY-----',
                'severity': Severity.CRITICAL
            },
            {
                'name': 'Database URL',
                'pattern': r'(mysql|postgres|mongodb)://[^\\s]+:[^\\s]+@',
                'severity': Severity.HIGH
            }
        ]
    
    def analyze_code(self, code: str, language: str = None) -> List[SecurityIssue]:
        """Analyze code for security issues."""
        issues = []
        
        # Run pattern-based analysis
        issues.extend(self._analyze_patterns(code))
        
        # Run secret detection
        issues.extend(self._detect_secrets(code))
        
        # Language-specific analysis
        if language:
            issues.extend(self._analyze_language_specific(code, language))
        
        return issues
    
    def _analyze_patterns(self, code: str) -> List[SecurityIssue]:
        """Analyze code using predefined vulnerability patterns."""
        issues = []
        lines = code.split('\n')
        
        for category, patterns in self.patterns.items():
            for pattern_info in patterns:
                pattern = pattern_info['pattern']
                
                # Check each line
                for line_num, line in enumerate(lines, 1):
                    matches = re.finditer(pattern, line, re.IGNORECASE)
                    for match in matches:
                        issue = SecurityIssue(
                            issue_type=category,
                            severity=pattern_info['severity'],
                            message=pattern_info['message'],
                            line_number=line_num,
                            code_snippet=line.strip(),
                            recommendation=pattern_info['recommendation']
                        )
                        issues.append(issue)
        
        return issues
    
    def _detect_secrets(self, code: str) -> List[SecurityIssue]:
        """Detect hardcoded secrets in code."""
        issues = []
        lines = code.split('\n')
        
        for secret_info in self.secret_patterns:
            pattern = secret_info['pattern']
            
            for line_num, line in enumerate(lines, 1):
                # Skip comments and strings that might be examples
                if line.strip().startswith('#') or line.strip().startswith('//'):
                    continue
                
                matches = re.finditer(pattern, line)
                for match in matches:
                    # Additional validation for false positives
                    matched_text = match.group()
                    
                    # Skip obvious test/example values
                    if any(test_word in matched_text.lower() for test_word in 
                          ['test', 'example', 'demo', 'sample', 'placeholder']):
                        continue
                    
                    issue = SecurityIssue(
                        issue_type='hardcoded_secret',
                        severity=secret_info['severity'],
                        message=f"Potential hardcoded {secret_info['name']} detected",
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation="Move secrets to environment variables or secure credential storage"
                    )
                    issues.append(issue)
        
        return issues
    
    def _analyze_language_specific(self, code: str, language: str) -> List[SecurityIssue]:
        """Perform language-specific security analysis."""
        issues = []
        
        if language.lower() == 'python':
            issues.extend(self._analyze_python_specific(code))
        elif language.lower() in ['javascript', 'typescript']:
            issues.extend(self._analyze_javascript_specific(code))
        elif language.lower() == 'go':
            issues.extend(self._analyze_go_specific(code))
        elif language.lower() == 'rust':
            issues.extend(self._analyze_rust_specific(code))
        
        return issues
    
    def _analyze_python_specific(self, code: str) -> List[SecurityIssue]:
        """Python-specific security analysis."""
        issues = []
        lines = code.split('\n')
        
        python_patterns = [
            {
                'pattern': r'pickle\.loads?\s*\(',
                'severity': Severity.HIGH,
                'message': 'Use of pickle can lead to arbitrary code execution',
                'recommendation': 'Use safer serialization formats like JSON'
            },
            {
                'pattern': r'yaml\.load\s*\(',
                'severity': Severity.HIGH,
                'message': 'yaml.load() is unsafe, use yaml.safe_load()',
                'recommendation': 'Use yaml.safe_load() instead of yaml.load()'
            },
            {
                'pattern': r'input\s*\(.*?\)',
                'severity': Severity.LOW,
                'message': 'input() in Python 2 can execute arbitrary code',
                'recommendation': 'Use raw_input() in Python 2 or ensure Python 3'
            }
        ]
        
        for pattern_info in python_patterns:
            pattern = pattern_info['pattern']
            
            for line_num, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    issue = SecurityIssue(
                        issue_type='python_specific',
                        severity=pattern_info['severity'],
                        message=pattern_info['message'],
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation=pattern_info['recommendation']
                    )
                    issues.append(issue)
        
        return issues
    
    def _analyze_javascript_specific(self, code: str) -> List[SecurityIssue]:
        """JavaScript/TypeScript-specific security analysis."""
        issues = []
        lines = code.split('\n')
        
        js_patterns = [
            {
                'pattern': r'dangerouslySetInnerHTML',
                'severity': Severity.HIGH,
                'message': 'dangerouslySetInnerHTML can lead to XSS vulnerabilities',
                'recommendation': 'Sanitize content before using dangerouslySetInnerHTML'
            },
            {
                'pattern': r'new\s+Function\s*\(',
                'severity': Severity.HIGH,
                'message': 'Function constructor can lead to code injection',
                'recommendation': 'Avoid dynamic function creation'
            },
            {
                'pattern': r'setTimeout\s*\(\s*["\']',
                'severity': Severity.MEDIUM,
                'message': 'setTimeout with string argument can lead to code injection',
                'recommendation': 'Use function references instead of string arguments'
            }
        ]
        
        for pattern_info in js_patterns:
            pattern = pattern_info['pattern']
            
            for line_num, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    issue = SecurityIssue(
                        issue_type='javascript_specific',
                        severity=pattern_info['severity'],
                        message=pattern_info['message'],
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation=pattern_info['recommendation']
                    )
                    issues.append(issue)
        
        return issues
    
    def _analyze_go_specific(self, code: str) -> List[SecurityIssue]:
        """Go-specific security analysis."""
        issues = []
        lines = code.split('\n')
        
        go_patterns = [
            {
                'pattern': r'exec\.Command\s*\(',
                'severity': Severity.MEDIUM,
                'message': 'Command execution detected',
                'recommendation': 'Validate input and avoid shell injection'
            },
            {
                'pattern': r'http\.ListenAndServe\s*\(\s*["\']:[0-9]+["\']',
                'severity': Severity.LOW,
                'message': 'HTTP server without TLS',
                'recommendation': 'Consider using HTTPS for production'
            }
        ]
        
        for pattern_info in go_patterns:
            pattern = pattern_info['pattern']
            
            for line_num, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    issue = SecurityIssue(
                        issue_type='go_specific',
                        severity=pattern_info['severity'],
                        message=pattern_info['message'],
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation=pattern_info['recommendation']
                    )
                    issues.append(issue)
        
        return issues
    
    def _analyze_rust_specific(self, code: str) -> List[SecurityIssue]:
        """Rust-specific security analysis."""
        issues = []
        lines = code.split('\n')
        
        rust_patterns = [
            {
                'pattern': r'unsafe\s*\{',
                'severity': Severity.HIGH,
                'message': 'Unsafe block detected',
                'recommendation': 'Review unsafe code carefully for memory safety violations'
            },
            {
                'pattern': r'\.unwrap\s*\(\s*\)',
                'severity': Severity.MEDIUM,
                'message': 'Use of unwrap() can cause panics',
                'recommendation': 'Use proper error handling with match, if let, or expect() with descriptive message'
            },
            {
                'pattern': r'\.expect\s*\(\s*["\'][^"\']*["\']\s*\)',
                'severity': Severity.LOW,
                'message': 'Use of expect() can cause panics',
                'recommendation': 'Consider using match or if let for graceful error handling'
            },
            {
                'pattern': r'std::process::Command::new\s*\(',
                'severity': Severity.MEDIUM,
                'message': 'Command execution detected',
                'recommendation': 'Validate input to prevent command injection'
            },
            {
                'pattern': r'std::ptr::(read|write)_volatile',
                'severity': Severity.HIGH,
                'message': 'Volatile memory operations detected',
                'recommendation': 'Ensure proper synchronization and memory safety'
            },
            {
                'pattern': r'std::mem::(transmute|forget)',
                'severity': Severity.CRITICAL,
                'message': 'Dangerous memory operations detected',
                'recommendation': 'Use safe alternatives or ensure memory safety invariants'
            },
            {
                'pattern': r'std::slice::from_raw_parts',
                'severity': Severity.HIGH,
                'message': 'Raw pointer to slice conversion',
                'recommendation': 'Ensure pointer validity and proper lifetime management'
            },
            {
                'pattern': r'libc::(malloc|free|realloc)',
                'severity': Severity.HIGH,
                'message': 'Direct C memory management detected',
                'recommendation': 'Use Rust memory management or ensure proper allocation/deallocation'
            },
            {
                'pattern': r'#\[allow\(.*dead_code.*\)\]',
                'severity': Severity.LOW,
                'message': 'Dead code allowed',
                'recommendation': 'Remove unused code instead of suppressing warnings'
            },
            {
                'pattern': r'panic!\s*\(',
                'severity': Severity.MEDIUM,
                'message': 'Explicit panic detected',
                'recommendation': 'Use Result<T, E> for recoverable errors'
            },
            {
                'pattern': r'unimplemented!\s*\(',
                'severity': Severity.MEDIUM,
                'message': 'Unimplemented code path',
                'recommendation': 'Implement the missing functionality or use todo!()'
            },
            {
                'pattern': r'\.clone\(\)(?:\s*\.clone\(\))+',
                'severity': Severity.LOW,
                'message': 'Multiple consecutive clones detected',
                'recommendation': 'Consider borrowing or using references to avoid unnecessary clones'
            }
        ]
        
        for pattern_info in rust_patterns:
            pattern = pattern_info['pattern']
            
            for line_num, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    issue = SecurityIssue(
                        issue_type='rust_specific',
                        severity=pattern_info['severity'],
                        message=pattern_info['message'],
                        line_number=line_num,
                        code_snippet=line.strip(),
                        recommendation=pattern_info['recommendation']
                    )
                    issues.append(issue)
        
        return issues
    
    def get_security_summary(self, issues: List[SecurityIssue]) -> Dict[str, Any]:
        """Generate a summary of security issues."""
        summary = {
            'total_issues': len(issues),
            'by_severity': {severity.value: 0 for severity in Severity},
            'by_type': {},
            'critical_issues': [],
            'recommendations': set()
        }
        
        for issue in issues:
            # Count by severity
            summary['by_severity'][issue.severity.value] += 1
            
            # Count by type
            if issue.issue_type not in summary['by_type']:
                summary['by_type'][issue.issue_type] = 0
            summary['by_type'][issue.issue_type] += 1
            
            # Collect critical issues
            if issue.severity == Severity.CRITICAL:
                summary['critical_issues'].append(issue)
            
            # Collect recommendations
            if issue.recommendation:
                summary['recommendations'].add(issue.recommendation)
        
        # Convert recommendations set to list
        summary['recommendations'] = list(summary['recommendations'])
        
        return summary

# Global security analyzer instance
security_analyzer = SecurityAnalyzer()