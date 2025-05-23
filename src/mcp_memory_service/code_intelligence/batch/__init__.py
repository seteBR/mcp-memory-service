"""
Batch processing module for code intelligence.

This module provides capabilities for analyzing entire repositories
with parallel processing, progress tracking, and comprehensive reporting.
"""

from .batch_processor import BatchProcessor, BatchProgress, BatchResult

__all__ = ['BatchProcessor', 'BatchProgress', 'BatchResult']