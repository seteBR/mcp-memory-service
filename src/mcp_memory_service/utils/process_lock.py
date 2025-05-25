"""Process lock implementation for auto-sync single instance enforcement."""

import os
import sys
import time
import atexit
import signal
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ProcessLock:
    """Manages a PID file to ensure only one auto-sync instance runs."""
    
    def __init__(self, name: str = "mcp_auto_sync"):
        self.name = name
        self.pid_file = Path.home() / ".mcp" / f"{name}.pid"
        self.pid_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock_acquired = False
        
    def acquire(self) -> bool:
        """Try to acquire the lock. Returns True if successful."""
        # Check if PID file exists
        if self.pid_file.exists():
            try:
                # Read the PID
                pid = int(self.pid_file.read_text().strip())
                
                # Check if process is still running
                if pid == os.getpid():
                    # It's our own PID, something is wrong
                    logger.warning(f"PID file contains our own PID {pid}, removing")
                    self.pid_file.unlink()
                elif self._is_process_running(pid):
                    logger.info(f"Auto-sync already running with PID {pid}")
                    return False
                else:
                    # Process is dead, remove stale PID file
                    logger.info(f"Removing stale PID file for dead process {pid}")
                    self.pid_file.unlink()
            except (ValueError, OSError) as e:
                logger.warning(f"Error reading PID file: {e}")
                # Invalid PID file, remove it
                self.pid_file.unlink()
        
        # Write our PID
        try:
            self.pid_file.write_text(str(os.getpid()))
            self._lock_acquired = True
            
            # Register cleanup handlers
            atexit.register(self.release)
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
            
            logger.info(f"Auto-sync lock acquired with PID {os.getpid()}")
            return True
        except OSError as e:
            logger.error(f"Failed to write PID file: {e}")
            return False
    
    def release(self):
        """Release the lock by removing the PID file."""
        if self._lock_acquired and self.pid_file.exists():
            try:
                # Only remove if it's our PID
                current_pid = int(self.pid_file.read_text().strip())
                if current_pid == os.getpid():
                    self.pid_file.unlink()
                    logger.info("Auto-sync lock released")
            except (ValueError, OSError) as e:
                logger.warning(f"Error releasing lock: {e}")
            finally:
                self._lock_acquired = False
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals."""
        self.release()
        sys.exit(0)
    
    def _is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running."""
        if HAS_PSUTIL:
            try:
                process = psutil.Process(pid)
                # Check if it's actually our process type
                cmdline = " ".join(process.cmdline()).lower()
                return "mcp" in cmdline and "memory" in cmdline
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return False
        else:
            # Fallback: check if process exists using os.kill
            try:
                os.kill(pid, 0)  # Signal 0 just checks if process exists
                return True  # Can't verify it's our process without psutil
            except (ProcessLookupError, PermissionError):
                return False
    
    def __enter__(self):
        """Context manager support."""
        if not self.acquire():
            raise RuntimeError("Could not acquire auto-sync lock")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.release()


class CooperativeProcessLock(ProcessLock):
    """A cooperative lock that allows checking without acquiring."""
    
    def is_locked(self) -> tuple[bool, Optional[int]]:
        """Check if lock is held by another process. Returns (is_locked, pid)."""
        if not self.pid_file.exists():
            return False, None
        
        try:
            pid = int(self.pid_file.read_text().strip())
            if self._is_process_running(pid):
                return True, pid
            else:
                # Stale lock
                return False, None
        except (ValueError, OSError):
            return False, None
    
    def wait_for_lock(self, timeout: float = 30.0) -> bool:
        """Wait for lock to become available. Returns True if acquired."""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.acquire():
                return True
            time.sleep(1.0)
        
        return False