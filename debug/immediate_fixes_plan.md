# Immediate Fixes for Concurrent User Support

## Quick Wins (Can implement now)

### 1. Fix Async Repository Sync Blocking Issue

**Current Problem**: Background tasks hold locks indefinitely

**Immediate Fix**:
```python
class AsyncRepositorySync:
    async def sync_repository(
        self,
        repository_path: str,
        repository_name: str,
        incremental: bool = True,
        force_full: bool = False
    ) -> SyncResult:
        """
        IMMEDIATE FIX: Make sync synchronous by default
        """
        # Remove async task spawning
        # Process files directly and return complete result
        
        result = SyncResult()
        
        # Scan files
        files = await self._scan_repository_async(repo_path)
        
        # Process all files before returning
        await self._process_files_directly(files, result)
        
        return result  # Complete result, no background tasks
```

### 2. Improve Lock Granularity

**Current Problem**: Single global lock blocks all operations

**Immediate Fix**: Use operation-specific locks
```python
class ChromaDBLockManager:
    def __init__(self, base_path: str):
        self.locks = {
            'memory_write': FileLock(f"{base_path}/.memory_write.lock"),
            'memory_read': FileLock(f"{base_path}/.memory_read.lock"),
            'code_sync': FileLock(f"{base_path}/.code_sync.lock"),
            'batch_analyze': FileLock(f"{base_path}/.batch_analyze.lock")
        }
    
    @contextmanager
    def acquire_lock(self, operation: str, timeout: float = 30):
        """Acquire lock for specific operation type."""
        lock_type = self._get_lock_type(operation)
        lock = self.locks.get(lock_type)
        
        try:
            lock.acquire(timeout=timeout)
            yield
        finally:
            lock.release()
    
    def _get_lock_type(self, operation: str) -> str:
        """Determine lock type based on operation."""
        if operation in ['store_memory', 'delete_memory']:
            return 'memory_write'
        elif operation in ['retrieve_memory', 'search_memory']:
            return 'memory_read'  # Could be a shared lock
        elif operation == 'sync_repository':
            return 'code_sync'
        elif operation == 'batch_analyze':
            return 'batch_analyze'
        else:
            return 'memory_write'  # Default to write lock
```

### 3. Add Basic Rate Limiting

**Immediate Fix**: Simple in-memory rate limiter
```python
from collections import defaultdict
from time import time

class SimpleRateLimiter:
    def __init__(self):
        self.user_operations = defaultdict(list)
        self.limits = {
            'memory_ops_per_minute': 100,
            'sync_ops_per_hour': 5,
            'batch_ops_per_day': 10
        }
    
    async def check_rate_limit(self, user_id: str, operation: str) -> bool:
        """Check if operation is within rate limits."""
        now = time()
        key = f"{user_id}:{operation}"
        
        # Clean old entries
        self.user_operations[key] = [
            timestamp for timestamp in self.user_operations[key]
            if now - timestamp < self._get_window(operation)
        ]
        
        # Check limit
        if len(self.user_operations[key]) >= self._get_limit(operation):
            return False
        
        # Record operation
        self.user_operations[key].append(now)
        return True
    
    def _get_window(self, operation: str) -> int:
        """Get time window for operation."""
        if operation.startswith('memory_'):
            return 60  # 1 minute
        elif operation.startswith('sync_'):
            return 3600  # 1 hour
        else:
            return 86400  # 1 day
```

### 4. Add Operation Timeout

**Immediate Fix**: Timeout long-running operations
```python
async def with_timeout(operation, timeout_seconds=300):
    """Wrap operations with timeout."""
    try:
        return await asyncio.wait_for(operation, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error(f"Operation timed out after {timeout_seconds}s")
        raise OperationTimeout(f"Operation exceeded {timeout_seconds}s limit")
```

### 5. Add Progress Tracking

**Immediate Fix**: Simple progress storage
```python
class ProgressStore:
    def __init__(self):
        self.progress = {}  # In-memory for now
    
    async def update_progress(self, operation_id: str, progress: dict):
        """Update operation progress."""
        self.progress[operation_id] = {
            'updated_at': time(),
            'progress': progress
        }
    
    async def get_progress(self, operation_id: str) -> dict:
        """Get operation progress."""
        return self.progress.get(operation_id, {})
```

## Medium-term Improvements (1-2 weeks)

### 1. Connection Pooling for ChromaDB

```python
class ChromaDBPool:
    def __init__(self, pool_size: int = 10):
        self.pool = []
        self.semaphore = asyncio.Semaphore(pool_size)
        
        # Create pool of clients
        for _ in range(pool_size):
            client = chromadb.PersistentClient(path=chroma_path)
            self.pool.append(client)
    
    @asynccontextmanager
    async def get_client(self):
        """Get a client from the pool."""
        async with self.semaphore:
            client = self.pool.pop()
            try:
                yield client
            finally:
                self.pool.append(client)
```

### 2. Async Wrapper for ChromaDB

```python
class AsyncChromaDB:
    def __init__(self, client_pool: ChromaDBPool):
        self.pool = client_pool
        self.executor = ThreadPoolExecutor(max_workers=20)
    
    async def add(self, collection_name: str, **kwargs):
        """Async wrapper for add operation."""
        async with self.pool.get_client() as client:
            collection = client.get_or_create_collection(collection_name)
            
            # Run in thread pool
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                self.executor,
                collection.add,
                **kwargs
            )
```

### 3. User Namespace Isolation

```python
class UserNamespaceManager:
    def get_collection_name(self, user_id: str, base_name: str) -> str:
        """Get user-specific collection name."""
        # Option 1: Separate collections per user
        return f"{user_id}_{base_name}"
        
        # Option 2: Shared collection with metadata filtering
        # return base_name  # Filter by user_id in queries
    
    def add_user_metadata(self, user_id: str, metadata: dict) -> dict:
        """Add user ID to metadata."""
        metadata = metadata.copy()
        metadata['user_id'] = user_id
        return metadata
```

### 4. Basic Job Queue (without Redis)

```python
import sqlite3
from typing import Optional

class SQLiteJobQueue:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database."""
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                priority INTEGER NOT NULL,
                status TEXT NOT NULL,
                payload TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                result TEXT,
                error TEXT
            )
        ''')
        conn.commit()
        conn.close()
    
    async def submit_job(self, job: dict) -> str:
        """Submit a job to queue."""
        job_id = str(uuid.uuid4())
        
        conn = sqlite3.connect(self.db_path)
        conn.execute('''
            INSERT INTO jobs (id, user_id, operation, priority, status, payload)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            job_id,
            job['user_id'],
            job['operation'],
            job.get('priority', 3),
            'queued',
            json.dumps(job.get('payload', {}))
        ))
        conn.commit()
        conn.close()
        
        return job_id
    
    async def get_next_job(self) -> Optional[dict]:
        """Get next job by priority."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute('''
            SELECT * FROM jobs
            WHERE status = 'queued'
            ORDER BY priority ASC, created_at ASC
            LIMIT 1
        ''')
        
        row = cursor.fetchone()
        if row:
            # Mark as processing
            conn.execute('''
                UPDATE jobs 
                SET status = 'processing', started_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (row[0],))
            conn.commit()
        
        conn.close()
        return row
```

## Configuration Changes

### 1. Add to config.py
```python
# Concurrency settings
MAX_CONCURRENT_MEMORY_OPS = int(os.getenv('MAX_CONCURRENT_MEMORY_OPS', '20'))
MAX_CONCURRENT_SYNC_OPS = int(os.getenv('MAX_CONCURRENT_SYNC_OPS', '3'))
MAX_CONCURRENT_BATCH_OPS = int(os.getenv('MAX_CONCURRENT_BATCH_OPS', '2'))

# Timeout settings
MEMORY_OP_TIMEOUT = int(os.getenv('MEMORY_OP_TIMEOUT', '30'))
SYNC_OP_TIMEOUT = int(os.getenv('SYNC_OP_TIMEOUT', '3600'))
BATCH_OP_TIMEOUT = int(os.getenv('BATCH_OP_TIMEOUT', '7200'))

# Rate limiting
RATE_LIMIT_MEMORY_PER_MIN = int(os.getenv('RATE_LIMIT_MEMORY_PER_MIN', '100'))
RATE_LIMIT_SYNC_PER_HOUR = int(os.getenv('RATE_LIMIT_SYNC_PER_HOUR', '5'))
```

### 2. Environment Variables
```bash
# .env file
MAX_CONCURRENT_MEMORY_OPS=50
MAX_CONCURRENT_SYNC_OPS=5
MEMORY_OP_TIMEOUT=60
SYNC_OP_TIMEOUT=1800
RATE_LIMIT_MEMORY_PER_MIN=200
```

## Testing Strategy

### 1. Concurrent User Test
```python
async def test_concurrent_users():
    """Test multiple users performing operations."""
    users = [f"user_{i}" for i in range(10)]
    
    async def user_operations(user_id):
        # Memory operations
        for i in range(10):
            await store_memory(f"Memory {i} from {user_id}")
        
        # Code sync
        await sync_repository("/path", f"repo_{user_id}")
    
    # Run all users concurrently
    await asyncio.gather(*[user_operations(u) for u in users])
```

### 2. Load Test
```bash
# Using locust for load testing
locust -f load_test.py --host=http://localhost:8000 --users=100 --spawn-rate=10
```

## Rollout Plan

### Week 1: Critical Fixes
- [ ] Fix async repository sync blocking
- [ ] Implement operation timeouts
- [ ] Add basic rate limiting
- [ ] Deploy and monitor

### Week 2: Improved Concurrency
- [ ] Implement lock granularity
- [ ] Add connection pooling
- [ ] Basic progress tracking
- [ ] Performance testing

### Week 3: User Isolation
- [ ] User namespace management
- [ ] Per-user resource limits
- [ ] SQLite job queue
- [ ] Integration testing

### Week 4: Production Hardening
- [ ] Monitoring and alerting
- [ ] Performance optimization
- [ ] Documentation
- [ ] Gradual rollout