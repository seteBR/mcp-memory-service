#!/usr/bin/env python3
"""
Debug script for MCP Memory Service repository sync operations.
This script helps diagnose issues during repository synchronization.
"""

import asyncio
import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import memory service modules
try:
    from src.mcp_memory_service.storage.chroma import ChromaMemoryStorage
    from src.mcp_memory_service.code_intelligence.sync.repository_sync import RepositorySync
    from src.mcp_memory_service.code_intelligence.batch.batch_processor import BatchProcessor
    from src.mcp_memory_service.code_intelligence.monitoring.metrics_collector import MetricsCollector, initialize_metrics
    from src.mcp_memory_service.config import CHROMA_PATH, CODE_COLLECTION_NAME
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure you're running from the mcp-memory-service directory")
    sys.exit(1)

# Configure logging
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
logging.basicConfig(
    level=logging.DEBUG,
    format=LOG_FORMAT,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug_sync.log', mode='w')
    ]
)

logger = logging.getLogger(__name__)

class SyncDebugger:
    """Debug harness for repository sync operations."""
    
    def __init__(self):
        self.chroma_path = CHROMA_PATH
        self.code_collection_name = CODE_COLLECTION_NAME
        self.storage = None
        self.code_storage = None
        self.start_time = None
        self.metrics = {
            'start_time': None,
            'end_time': None,
            'duration': None,
            'files_processed': 0,
            'chunks_created': 0,
            'errors': [],
            'warnings': [],
            'lock_acquisitions': 0,
            'lock_releases': 0,
            'retries': 0
        }
        
    async def init_storage(self):
        """Initialize storage with debug logging."""
        logger.info("Initializing ChromaDB storage...")
        try:
            # Initialize regular memory storage
            self.storage = ChromaMemoryStorage(str(self.chroma_path))
            logger.info(f"Memory storage initialized at: {self.chroma_path}")
            
            # Initialize code collection storage for code intelligence
            self.code_storage = ChromaMemoryStorage(str(self.chroma_path))
            # Switch to code collection
            self.code_storage.collection = self.code_storage.client.get_or_create_collection(
                name=self.code_collection_name,
                embedding_function=self.code_storage.embedding_function
            )
            logger.info(f"Code storage initialized with collection: {self.code_collection_name}")
            
            # Check database health
            health = await self.storage.check_health()
            logger.info(f"Database health: {json.dumps(health, indent=2)}")
            
        except Exception as e:
            logger.error(f"Failed to initialize storage: {e}")
            logger.error(traceback.format_exc())
            raise
    
    async def monitor_lock_file(self):
        """Monitor lock file status."""
        lock_path = self.chroma_path / '.chroma.lock'
        
        while True:
            if lock_path.exists():
                stat = lock_path.stat()
                logger.debug(f"Lock file exists - Size: {stat.st_size}, "
                           f"Modified: {datetime.fromtimestamp(stat.st_mtime)}")
                
                # Check if lock is held
                try:
                    import fcntl
                    with open(lock_path, 'r') as f:
                        try:
                            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
                            logger.debug("Lock file is not actively locked")
                        except IOError:
                            logger.debug("Lock file is actively locked by another process")
                except Exception as e:
                    logger.debug(f"Error checking lock status: {e}")
            else:
                logger.debug("Lock file does not exist")
            
            await asyncio.sleep(1)
    
    async def sync_repository_with_monitoring(self, repo_path: str, repo_name: str):
        """Sync repository with detailed monitoring."""
        self.start_time = time.time()
        self.metrics['start_time'] = datetime.now().isoformat()
        
        # Start lock monitoring in background
        monitor_task = asyncio.create_task(self.monitor_lock_file())
        
        try:
            logger.info(f"Starting repository sync: {repo_name} at {repo_path}")
            
            # Initialize metrics if needed
            initialize_metrics()
            
            # Create batch processor with debug logging
            batch_processor = BatchProcessor(
                storage=self.code_storage,
                max_workers=2  # Reduce workers for easier debugging
            )
            
            # Hook into storage events
            original_store = self.code_storage.add_memory
            async def logged_store(*args, **kwargs):
                self.metrics['chunks_created'] += 1
                logger.debug(f"Storing chunk #{self.metrics['chunks_created']}")
                return await original_store(*args, **kwargs)
            self.code_storage.add_memory = logged_store
            
            # Process repository
            logger.info("Starting batch processing...")
            result = await batch_processor.process_repository(
                repository_path=repo_path,
                repository_name=repo_name,
                store_results=True,
                generate_report=True
            )
            
            logger.info(f"Batch processing completed: {result}")
            
            # Get final metrics
            if hasattr(batch_processor, 'metrics_collector'):
                metrics = batch_processor.metrics_collector.get_metrics('summary')
                logger.info(f"Processing metrics: {json.dumps(metrics, indent=2)}")
            
        except asyncio.CancelledError:
            logger.warning("Sync operation was cancelled")
            self.metrics['errors'].append("Operation cancelled")
            raise
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            logger.error(traceback.format_exc())
            self.metrics['errors'].append(str(e))
            raise
        finally:
            # Stop monitoring
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
            # Record final metrics
            self.metrics['end_time'] = datetime.now().isoformat()
            self.metrics['duration'] = time.time() - self.start_time
            
            # Save debug report
            self.save_debug_report()
    
    def save_debug_report(self):
        """Save debug report to file."""
        report_path = Path('debug_sync_report.json')
        
        with open(report_path, 'w') as f:
            json.dump(self.metrics, f, indent=2)
        
        logger.info(f"Debug report saved to: {report_path}")
        
        # Print summary
        print("\n" + "="*60)
        print("SYNC DEBUG SUMMARY")
        print("="*60)
        print(f"Duration: {self.metrics['duration']:.2f} seconds")
        print(f"Files processed: {self.metrics['files_processed']}")
        print(f"Chunks created: {self.metrics['chunks_created']}")
        print(f"Errors: {len(self.metrics['errors'])}")
        if self.metrics['errors']:
            print("\nErrors encountered:")
            for error in self.metrics['errors']:
                print(f"  - {error}")
        print("="*60)

async def main():
    """Main debug function."""
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python debug_sync.py <repository_path> [repository_name]")
        sys.exit(1)
    
    repo_path = sys.argv[1]
    repo_name = sys.argv[2] if len(sys.argv) > 2 else Path(repo_path).name
    
    # Validate repository exists
    if not Path(repo_path).exists():
        print(f"Error: Repository path does not exist: {repo_path}")
        sys.exit(1)
    
    # Create debugger
    debugger = SyncDebugger()
    
    try:
        # Initialize storage
        await debugger.init_storage()
        
        # Run sync with monitoring
        await debugger.sync_repository_with_monitoring(repo_path, repo_name)
        
    except KeyboardInterrupt:
        logger.info("Debug interrupted by user")
    except Exception as e:
        logger.error(f"Debug failed: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        if debugger.storage:
            logger.info("Closing storage...")
            # Note: ChromaStorage doesn't have a close method, but we log for completeness

if __name__ == "__main__":
    asyncio.run(main())