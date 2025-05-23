"""
Metrics collection and monitoring system for code intelligence platform.

Provides comprehensive tracking of performance, usage, errors, and insights
for optimization and analytics purposes.
"""

import time
import asyncio
import logging
import json
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any, Callable
from collections import defaultdict, deque
from pathlib import Path
import threading
from concurrent.futures import ThreadPoolExecutor
import psutil
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetric:
    """Individual performance measurement."""
    operation: str
    start_time: float
    end_time: float
    duration: float
    memory_start: Optional[int] = None
    memory_end: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def memory_delta(self) -> Optional[int]:
        if self.memory_start is not None and self.memory_end is not None:
            return self.memory_end - self.memory_start
        return None


@dataclass
class UsageMetric:
    """Usage statistics tracking."""
    command: str
    timestamp: float
    duration: float
    repository: Optional[str] = None
    language: Optional[str] = None
    files_processed: int = 0
    chunks_created: int = 0
    security_issues: int = 0
    success: bool = True
    error: Optional[str] = None
    user_id: Optional[str] = None


@dataclass
class ErrorMetric:
    """Error tracking and analysis."""
    timestamp: float
    operation: str
    error_type: str
    error_message: str
    file_path: Optional[str] = None
    language: Optional[str] = None
    repository: Optional[str] = None
    traceback: Optional[str] = None


@dataclass
class SecurityMetric:
    """Security analysis tracking."""
    timestamp: float
    repository: str
    language: str
    file_path: str
    vulnerability_type: str
    severity: str
    line_number: Optional[int] = None


@dataclass
class SystemMetric:
    """System resource utilization."""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_io_read_mb: float
    disk_io_write_mb: float
    active_connections: int = 0
    chunk_storage_size_mb: float = 0.0


class MetricsCollector:
    """Centralized metrics collection and analysis system."""
    
    def __init__(self, db_path: str = "metrics.db", retention_days: int = 30):
        self.db_path = db_path
        self.retention_days = retention_days
        self.performance_buffer = deque(maxlen=1000)
        self.usage_buffer = deque(maxlen=1000)
        self.error_buffer = deque(maxlen=500)
        self.security_buffer = deque(maxlen=1000)
        self.system_buffer = deque(maxlen=100)
        
        # Thread safety
        self.lock = threading.RLock()
        
        # Background metrics collection
        self.system_monitor_enabled = True
        self.system_monitor_interval = 30  # seconds
        self.background_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="metrics")
        
        # Initialize database
        self._init_database()
        
        # Start background system monitoring
        self._start_system_monitoring()
        
        logger.info(f"MetricsCollector initialized with database: {db_path}")
    
    def _init_database(self):
        """Initialize SQLite database for metrics storage."""
        with self._get_db_connection() as conn:
            # Performance metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    operation TEXT NOT NULL,
                    duration REAL NOT NULL,
                    memory_delta INTEGER,
                    metadata TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Usage metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS usage_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    command TEXT NOT NULL,
                    duration REAL NOT NULL,
                    repository TEXT,
                    language TEXT,
                    files_processed INTEGER DEFAULT 0,
                    chunks_created INTEGER DEFAULT 0,
                    security_issues INTEGER DEFAULT 0,
                    success BOOLEAN DEFAULT TRUE,
                    error TEXT,
                    user_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Error metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS error_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    operation TEXT NOT NULL,
                    error_type TEXT NOT NULL,
                    error_message TEXT NOT NULL,
                    file_path TEXT,
                    language TEXT,
                    repository TEXT,
                    traceback TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Security metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS security_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    repository TEXT NOT NULL,
                    language TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    vulnerability_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    line_number INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # System metrics table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    cpu_percent REAL NOT NULL,
                    memory_percent REAL NOT NULL,
                    memory_used_mb REAL NOT NULL,
                    disk_io_read_mb REAL NOT NULL,
                    disk_io_write_mb REAL NOT NULL,
                    active_connections INTEGER DEFAULT 0,
                    chunk_storage_size_mb REAL DEFAULT 0.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_performance_timestamp ON performance_metrics(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_timestamp ON usage_metrics(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_error_timestamp ON error_metrics(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_security_timestamp ON security_metrics(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_system_timestamp ON system_metrics(timestamp)")
            
            conn.commit()
    
    @contextmanager
    def _get_db_connection(self):
        """Get database connection with proper cleanup."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        try:
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            conn.close()
    
    def _start_system_monitoring(self):
        """Start background system metrics collection."""
        def monitor_system():
            while self.system_monitor_enabled:
                try:
                    self._collect_system_metrics()
                    time.sleep(self.system_monitor_interval)
                except Exception as e:
                    logger.error(f"Error in system monitoring: {e}")
                    time.sleep(self.system_monitor_interval * 2)  # Back off on error
        
        self.background_executor.submit(monitor_system)
        logger.info("Background system monitoring started")
    
    def _collect_system_metrics(self):
        """Collect current system resource metrics."""
        try:
            # Get system stats
            cpu_percent = psutil.cpu_percent()
            memory = psutil.virtual_memory()
            disk_io = psutil.disk_io_counters()
            
            metric = SystemMetric(
                timestamp=time.time(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                disk_io_read_mb=(disk_io.read_bytes / (1024 * 1024)) if disk_io else 0.0,
                disk_io_write_mb=(disk_io.write_bytes / (1024 * 1024)) if disk_io else 0.0
            )
            
            with self.lock:
                self.system_buffer.append(metric)
            
            # Persist to database periodically
            if len(self.system_buffer) >= 10:
                self._flush_system_metrics()
                
        except Exception as e:
            logger.error(f"Error collecting system metrics: {e}")
    
    def track_performance(self, operation: str, **metadata) -> 'PerformanceTracker':
        """Context manager for tracking operation performance."""
        return PerformanceTracker(self, operation, metadata)
    
    def record_usage(self, command: str, duration: float, repository: str = None,
                    language: str = None, files_processed: int = 0, chunks_created: int = 0,
                    security_issues: int = 0, success: bool = True, error: str = None,
                    user_id: str = None):
        """Record usage statistics."""
        metric = UsageMetric(
            command=command,
            timestamp=time.time(),
            duration=duration,
            repository=repository,
            language=language,
            files_processed=files_processed,
            chunks_created=chunks_created,
            security_issues=security_issues,
            success=success,
            error=error,
            user_id=user_id
        )
        
        with self.lock:
            self.usage_buffer.append(metric)
        
        # Async flush to database
        if len(self.usage_buffer) >= 50:
            self.background_executor.submit(self._flush_usage_metrics)
    
    def record_error(self, operation: str, error: Exception, file_path: str = None,
                    language: str = None, repository: str = None, traceback_str: str = None):
        """Record error occurrence."""
        metric = ErrorMetric(
            timestamp=time.time(),
            operation=operation,
            error_type=type(error).__name__,
            error_message=str(error),
            file_path=file_path,
            language=language,
            repository=repository,
            traceback=traceback_str
        )
        
        with self.lock:
            self.error_buffer.append(metric)
        
        # Immediate flush for errors
        self.background_executor.submit(self._flush_error_metrics)
        
        logger.warning(f"Error recorded: {operation} - {error}")
    
    def record_security_finding(self, repository: str, language: str, file_path: str,
                              vulnerability_type: str, severity: str, line_number: int = None):
        """Record security vulnerability detection."""
        metric = SecurityMetric(
            timestamp=time.time(),
            repository=repository,
            language=language,
            file_path=file_path,
            vulnerability_type=vulnerability_type,
            severity=severity,
            line_number=line_number
        )
        
        with self.lock:
            self.security_buffer.append(metric)
        
        # Flush security metrics periodically
        if len(self.security_buffer) >= 100:
            self.background_executor.submit(self._flush_security_metrics)
    
    def _flush_performance_metrics(self):
        """Flush performance metrics to database."""
        with self.lock:
            metrics = list(self.performance_buffer)
            self.performance_buffer.clear()
        
        if not metrics:
            return
        
        try:
            with self._get_db_connection() as conn:
                conn.executemany("""
                    INSERT INTO performance_metrics 
                    (timestamp, operation, duration, memory_delta, metadata)
                    VALUES (?, ?, ?, ?, ?)
                """, [
                    (m.start_time, m.operation, m.duration, m.memory_delta, 
                     json.dumps(m.metadata) if m.metadata else None)
                    for m in metrics
                ])
                conn.commit()
        except Exception as e:
            logger.error(f"Error flushing performance metrics: {e}")
    
    def _flush_usage_metrics(self):
        """Flush usage metrics to database."""
        with self.lock:
            metrics = list(self.usage_buffer)
            self.usage_buffer.clear()
        
        if not metrics:
            return
        
        try:
            with self._get_db_connection() as conn:
                conn.executemany("""
                    INSERT INTO usage_metrics 
                    (timestamp, command, duration, repository, language, files_processed, 
                     chunks_created, security_issues, success, error, user_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    (m.timestamp, m.command, m.duration, m.repository, m.language,
                     m.files_processed, m.chunks_created, m.security_issues,
                     m.success, m.error, m.user_id)
                    for m in metrics
                ])
                conn.commit()
        except Exception as e:
            logger.error(f"Error flushing usage metrics: {e}")
    
    def _flush_error_metrics(self):
        """Flush error metrics to database."""
        with self.lock:
            metrics = list(self.error_buffer)
            self.error_buffer.clear()
        
        if not metrics:
            return
        
        try:
            with self._get_db_connection() as conn:
                conn.executemany("""
                    INSERT INTO error_metrics 
                    (timestamp, operation, error_type, error_message, file_path, 
                     language, repository, traceback)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    (m.timestamp, m.operation, m.error_type, m.error_message,
                     m.file_path, m.language, m.repository, m.traceback)
                    for m in metrics
                ])
                conn.commit()
        except Exception as e:
            logger.error(f"Error flushing error metrics: {e}")
    
    def _flush_security_metrics(self):
        """Flush security metrics to database."""
        with self.lock:
            metrics = list(self.security_buffer)
            self.security_buffer.clear()
        
        if not metrics:
            return
        
        try:
            with self._get_db_connection() as conn:
                conn.executemany("""
                    INSERT INTO security_metrics 
                    (timestamp, repository, language, file_path, vulnerability_type, 
                     severity, line_number)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, [
                    (m.timestamp, m.repository, m.language, m.file_path,
                     m.vulnerability_type, m.severity, m.line_number)
                    for m in metrics
                ])
                conn.commit()
        except Exception as e:
            logger.error(f"Error flushing security metrics: {e}")
    
    def _flush_system_metrics(self):
        """Flush system metrics to database."""
        with self.lock:
            metrics = list(self.system_buffer)
            self.system_buffer.clear()
        
        if not metrics:
            return
        
        try:
            with self._get_db_connection() as conn:
                conn.executemany("""
                    INSERT INTO system_metrics 
                    (timestamp, cpu_percent, memory_percent, memory_used_mb, 
                     disk_io_read_mb, disk_io_write_mb, active_connections, 
                     chunk_storage_size_mb)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, [
                    (m.timestamp, m.cpu_percent, m.memory_percent, m.memory_used_mb,
                     m.disk_io_read_mb, m.disk_io_write_mb, m.active_connections,
                     m.chunk_storage_size_mb)
                    for m in metrics
                ])
                conn.commit()
        except Exception as e:
            logger.error(f"Error flushing system metrics: {e}")
    
    def get_performance_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get performance metrics summary for the last N hours."""
        cutoff_time = time.time() - (hours * 3600)
        
        try:
            with self._get_db_connection() as conn:
                # Operation performance summary
                cursor = conn.execute("""
                    SELECT operation, 
                           COUNT(*) as count,
                           AVG(duration) as avg_duration,
                           MIN(duration) as min_duration,
                           MAX(duration) as max_duration
                    FROM performance_metrics 
                    WHERE timestamp > ?
                    GROUP BY operation
                    ORDER BY count DESC
                """, (cutoff_time,))
                
                operations = [dict(row) for row in cursor.fetchall()]
                
                # Overall stats
                cursor = conn.execute("""
                    SELECT COUNT(*) as total_operations,
                           AVG(duration) as avg_duration,
                           SUM(duration) as total_duration
                    FROM performance_metrics 
                    WHERE timestamp > ?
                """, (cutoff_time,))
                
                overall = dict(cursor.fetchone())
                
                return {
                    "time_range_hours": hours,
                    "overall": overall,
                    "by_operation": operations
                }
                
        except Exception as e:
            logger.error(f"Error getting performance summary: {e}")
            return {"error": str(e)}
    
    def get_usage_analytics(self, hours: int = 24) -> Dict[str, Any]:
        """Get usage analytics for the last N hours."""
        cutoff_time = time.time() - (hours * 3600)
        
        try:
            with self._get_db_connection() as conn:
                # Command usage frequency
                cursor = conn.execute("""
                    SELECT command, 
                           COUNT(*) as usage_count,
                           AVG(duration) as avg_duration,
                           SUM(files_processed) as total_files,
                           SUM(chunks_created) as total_chunks,
                           SUM(security_issues) as total_security_issues,
                           AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) as success_rate
                    FROM usage_metrics 
                    WHERE timestamp > ?
                    GROUP BY command
                    ORDER BY usage_count DESC
                """, (cutoff_time,))
                
                commands = [dict(row) for row in cursor.fetchall()]
                
                # Language distribution
                cursor = conn.execute("""
                    SELECT language, 
                           COUNT(*) as file_count,
                           SUM(chunks_created) as chunk_count
                    FROM usage_metrics 
                    WHERE timestamp > ? AND language IS NOT NULL
                    GROUP BY language
                    ORDER BY file_count DESC
                """, (cutoff_time,))
                
                languages = [dict(row) for row in cursor.fetchall()]
                
                # Repository activity
                cursor = conn.execute("""
                    SELECT repository, 
                           COUNT(*) as operation_count,
                           SUM(files_processed) as files_processed,
                           MAX(timestamp) as last_activity
                    FROM usage_metrics 
                    WHERE timestamp > ? AND repository IS NOT NULL
                    GROUP BY repository
                    ORDER BY operation_count DESC
                """, (cutoff_time,))
                
                repositories = [dict(row) for row in cursor.fetchall()]
                
                return {
                    "time_range_hours": hours,
                    "commands": commands,
                    "languages": languages,
                    "repositories": repositories
                }
                
        except Exception as e:
            logger.error(f"Error getting usage analytics: {e}")
            return {"error": str(e)}
    
    def get_error_report(self, hours: int = 24) -> Dict[str, Any]:
        """Get error analysis for the last N hours."""
        cutoff_time = time.time() - (hours * 3600)
        
        try:
            with self._get_db_connection() as conn:
                # Error frequency by type
                cursor = conn.execute("""
                    SELECT error_type, 
                           COUNT(*) as count,
                           GROUP_CONCAT(DISTINCT operation) as operations
                    FROM error_metrics 
                    WHERE timestamp > ?
                    GROUP BY error_type
                    ORDER BY count DESC
                """, (cutoff_time,))
                
                error_types = [dict(row) for row in cursor.fetchall()]
                
                # Most problematic files
                cursor = conn.execute("""
                    SELECT file_path, 
                           COUNT(*) as error_count,
                           GROUP_CONCAT(DISTINCT error_type) as error_types
                    FROM error_metrics 
                    WHERE timestamp > ? AND file_path IS NOT NULL
                    GROUP BY file_path
                    ORDER BY error_count DESC
                    LIMIT 10
                """, (cutoff_time,))
                
                problematic_files = [dict(row) for row in cursor.fetchall()]
                
                # Total error count
                cursor = conn.execute("""
                    SELECT COUNT(*) as total_errors
                    FROM error_metrics 
                    WHERE timestamp > ?
                """, (cutoff_time,))
                
                total_errors = cursor.fetchone()[0]
                
                return {
                    "time_range_hours": hours,
                    "total_errors": total_errors,
                    "by_error_type": error_types,
                    "problematic_files": problematic_files
                }
                
        except Exception as e:
            logger.error(f"Error getting error report: {e}")
            return {"error": str(e)}
    
    def get_security_insights(self, hours: int = 24) -> Dict[str, Any]:
        """Get security analysis insights for the last N hours."""
        cutoff_time = time.time() - (hours * 3600)
        
        try:
            with self._get_db_connection() as conn:
                # Vulnerability distribution by severity
                cursor = conn.execute("""
                    SELECT severity, 
                           COUNT(*) as count,
                           COUNT(DISTINCT repository) as affected_repos
                    FROM security_metrics 
                    WHERE timestamp > ?
                    GROUP BY severity
                    ORDER BY 
                        CASE severity 
                            WHEN 'critical' THEN 1 
                            WHEN 'high' THEN 2 
                            WHEN 'medium' THEN 3 
                            WHEN 'low' THEN 4 
                        END
                """, (cutoff_time,))
                
                by_severity = [dict(row) for row in cursor.fetchall()]
                
                # Vulnerability types
                cursor = conn.execute("""
                    SELECT vulnerability_type, 
                           COUNT(*) as count,
                           COUNT(DISTINCT file_path) as affected_files
                    FROM security_metrics 
                    WHERE timestamp > ?
                    GROUP BY vulnerability_type
                    ORDER BY count DESC
                """, (cutoff_time,))
                
                by_type = [dict(row) for row in cursor.fetchall()]
                
                # Most vulnerable repositories
                cursor = conn.execute("""
                    SELECT repository, 
                           COUNT(*) as vulnerability_count,
                           COUNT(DISTINCT file_path) as affected_files,
                           COUNT(DISTINCT vulnerability_type) as vulnerability_types
                    FROM security_metrics 
                    WHERE timestamp > ?
                    GROUP BY repository
                    ORDER BY vulnerability_count DESC
                    LIMIT 10
                """, (cutoff_time,))
                
                vulnerable_repos = [dict(row) for row in cursor.fetchall()]
                
                return {
                    "time_range_hours": hours,
                    "by_severity": by_severity,
                    "by_vulnerability_type": by_type,
                    "most_vulnerable_repositories": vulnerable_repos
                }
                
        except Exception as e:
            logger.error(f"Error getting security insights: {e}")
            return {"error": str(e)}
    
    def cleanup_old_metrics(self):
        """Clean up metrics older than retention period."""
        cutoff_time = time.time() - (self.retention_days * 24 * 3600)
        
        try:
            with self._get_db_connection() as conn:
                tables = ["performance_metrics", "usage_metrics", "error_metrics", 
                         "security_metrics", "system_metrics"]
                
                total_deleted = 0
                for table in tables:
                    cursor = conn.execute(f"""
                        DELETE FROM {table} WHERE timestamp < ?
                    """, (cutoff_time,))
                    deleted = cursor.rowcount
                    total_deleted += deleted
                    logger.info(f"Cleaned up {deleted} old records from {table}")
                
                conn.commit()
                logger.info(f"Total cleanup: {total_deleted} records removed")
                
        except Exception as e:
            logger.error(f"Error during metrics cleanup: {e}")
    
    def shutdown(self):
        """Gracefully shutdown metrics collection."""
        logger.info("Shutting down metrics collection...")
        
        # Stop system monitoring
        self.system_monitor_enabled = False
        
        # Flush all pending metrics
        self._flush_performance_metrics()
        self._flush_usage_metrics()
        self._flush_error_metrics()
        self._flush_security_metrics()
        self._flush_system_metrics()
        
        # Shutdown background executor
        self.background_executor.shutdown(wait=True)
        
        logger.info("Metrics collection shutdown complete")


class PerformanceTracker:
    """Context manager for tracking operation performance."""
    
    def __init__(self, collector: MetricsCollector, operation: str, metadata: Dict[str, Any]):
        self.collector = collector
        self.operation = operation
        self.metadata = metadata
        self.start_time = None
        self.start_memory = None
    
    def __enter__(self):
        self.start_time = time.time()
        try:
            process = psutil.Process()
            self.start_memory = process.memory_info().rss
        except:
            self.start_memory = None
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        end_time = time.time()
        duration = end_time - self.start_time
        
        end_memory = None
        try:
            process = psutil.Process()
            end_memory = process.memory_info().rss
        except:
            pass
        
        metric = PerformanceMetric(
            operation=self.operation,
            start_time=self.start_time,
            end_time=end_time,
            duration=duration,
            memory_start=self.start_memory,
            memory_end=end_memory,
            metadata=self.metadata
        )
        
        with self.collector.lock:
            self.collector.performance_buffer.append(metric)
        
        # Flush if buffer is getting full
        if len(self.collector.performance_buffer) >= 100:
            self.collector.background_executor.submit(self.collector._flush_performance_metrics)


# Global metrics collector instance
metrics_collector = None

def get_metrics_collector() -> MetricsCollector:
    """Get the global metrics collector instance."""
    global metrics_collector
    if metrics_collector is None:
        metrics_collector = MetricsCollector()
    return metrics_collector

def initialize_metrics(db_path: str = "metrics.db", retention_days: int = 30) -> MetricsCollector:
    """Initialize the global metrics collector."""
    global metrics_collector
    metrics_collector = MetricsCollector(db_path, retention_days)
    return metrics_collector

def shutdown_metrics():
    """Shutdown the global metrics collector."""
    global metrics_collector
    if metrics_collector:
        metrics_collector.shutdown()
        metrics_collector = None