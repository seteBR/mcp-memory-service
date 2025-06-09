# Concurrent Multi-User Architecture Design

## Current Implementation Analysis

### Architecture Weaknesses

1. **Single Point of Contention**
   - File-based lock (`.chroma.lock`) serializes ALL operations
   - One user's long operation blocks everyone
   - No priority or fairness mechanisms

2. **Unmanaged Background Tasks**
   - Code intelligence spawns untracked async tasks
   - No resource limits or quotas
   - No way to cancel or monitor tasks
   - Tasks can accumulate and exhaust resources

3. **Thread Pool Exhaustion**
   - Fixed thread pool (4 workers) shared globally
   - Heavy operations consume all threads
   - Memory operations compete with sync operations

4. **No User Isolation**
   - All users share same namespace
   - No per-user resource limits
   - No audit trail or access control
   - One user can impact all others

5. **Synchronous ChromaDB Client**
   - All operations go through synchronous client
   - Wrapped in thread pool executor
   - Additional overhead and complexity

## Proposed Architecture

### Core Design Principles

1. **Job Queue Architecture**
   - Decouple request acceptance from processing
   - Enable horizontal scaling
   - Provide backpressure and flow control

2. **Resource Isolation**
   - Per-user quotas and limits
   - Separate queues for different operation types
   - Priority-based scheduling

3. **Async-First Design**
   - Native async database client
   - Event-driven processing
   - Non-blocking operations throughout

### Component Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   MCP Client 1  │     │   MCP Client 2  │     │   MCP Client N  │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                         │
         └───────────────────────┴─────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   API Gateway Layer     │
                    │  - Rate Limiting        │
                    │  - Authentication       │
                    │  - Request Routing      │
                    └────────────┬────────────┘
                                 │
                ┌────────────────┴────────────────┐
                │          Job Queue System       │
                │  ┌─────────────────────────┐   │
                │  │   Memory Operations     │   │
                │  │   - High Priority       │   │
                │  │   - Fast Processing     │   │
                │  └─────────────────────────┘   │
                │  ┌─────────────────────────┐   │
                │  │   Code Intelligence     │   │
                │  │   - Low Priority        │   │
                │  │   - Long Running        │   │
                │  └─────────────────────────┘   │
                └────────────┬───────────────────┘
                             │
                ┌────────────▼───────────────┐
                │      Worker Pool           │
                │  ┌──────────────────┐      │
                │  │ Memory Workers   │      │
                │  │ (Many instances) │      │
                │  └──────────────────┘      │
                │  ┌──────────────────┐      │
                │  │  Code Workers    │      │
                │  │ (Few instances)  │      │
                │  └──────────────────┘      │
                └────────────┬───────────────┘
                             │
                ┌────────────▼───────────────┐
                │    Storage Layer           │
                │  ┌──────────────────┐      │
                │  │   ChromaDB       │      │
                │  │  (Async Client)  │      │
                │  └──────────────────┘      │
                │  ┌──────────────────┐      │
                │  │   PostgreSQL     │      │
                │  │  (Job State)     │      │
                │  └──────────────────┘      │
                └────────────────────────────┘
```

### Implementation Details

#### 1. Job Queue System

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import asyncio
from datetime import datetime

class JobPriority(Enum):
    CRITICAL = 1  # System operations
    HIGH = 2      # Memory operations
    NORMAL = 3    # Regular operations
    LOW = 4       # Code intelligence

class JobStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Job:
    id: str
    user_id: str
    operation: str
    priority: JobPriority
    payload: Dict[str, Any]
    status: JobStatus
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    worker_id: Optional[str] = None
    progress: Optional[Dict[str, Any]] = None

class JobQueue:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.queues = {
            JobPriority.CRITICAL: "jobs:critical",
            JobPriority.HIGH: "jobs:high",
            JobPriority.NORMAL: "jobs:normal",
            JobPriority.LOW: "jobs:low"
        }
    
    async def submit(self, job: Job) -> str:
        """Submit a job to the appropriate queue."""
        # Store job data
        await self.redis.hset(f"job:{job.id}", mapping=job.to_dict())
        
        # Add to priority queue
        queue_name = self.queues[job.priority]
        await self.redis.lpush(queue_name, job.id)
        
        # Track user's active jobs
        await self.redis.sadd(f"user:{job.user_id}:jobs", job.id)
        
        return job.id
    
    async def get_next_job(self, worker_type: str) -> Optional[Job]:
        """Get next job based on priority."""
        # Try queues in priority order
        for priority in JobPriority:
            queue_name = self.queues[priority]
            
            # Check if worker can handle this job type
            if not self._can_handle(worker_type, priority):
                continue
            
            # Pop from queue
            job_id = await self.redis.rpop(queue_name)
            if job_id:
                job_data = await self.redis.hgetall(f"job:{job_id}")
                return Job.from_dict(job_data)
        
        return None
```

#### 2. Worker Pool Management

```python
class WorkerPool:
    def __init__(self, worker_type: str, count: int):
        self.worker_type = worker_type
        self.count = count
        self.workers = []
        self.running = False
    
    async def start(self):
        """Start worker pool."""
        self.running = True
        
        for i in range(self.count):
            worker = Worker(
                worker_id=f"{self.worker_type}-{i}",
                worker_type=self.worker_type
            )
            self.workers.append(worker)
            asyncio.create_task(worker.run())
    
    async def stop(self):
        """Gracefully stop all workers."""
        self.running = False
        
        # Signal all workers to stop
        stop_tasks = [worker.stop() for worker in self.workers]
        await asyncio.gather(*stop_tasks)

class Worker:
    def __init__(self, worker_id: str, worker_type: str):
        self.worker_id = worker_id
        self.worker_type = worker_type
        self.current_job = None
        self.running = False
    
    async def run(self):
        """Main worker loop."""
        self.running = True
        
        while self.running:
            try:
                # Get next job
                job = await job_queue.get_next_job(self.worker_type)
                
                if not job:
                    # No job available, wait
                    await asyncio.sleep(1)
                    continue
                
                # Process job
                await self.process_job(job)
                
            except Exception as e:
                logger.error(f"Worker {self.worker_id} error: {e}")
                await asyncio.sleep(5)  # Back off on error
    
    async def process_job(self, job: Job):
        """Process a single job."""
        self.current_job = job
        
        try:
            # Update job status
            job.status = JobStatus.PROCESSING
            job.started_at = datetime.utcnow()
            job.worker_id = self.worker_id
            await job_queue.update_job(job)
            
            # Execute based on operation type
            if job.operation == "store_memory":
                result = await self.process_memory_operation(job)
            elif job.operation == "sync_repository":
                result = await self.process_sync_operation(job)
            else:
                raise ValueError(f"Unknown operation: {job.operation}")
            
            # Update job as completed
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            job.result = result
            await job_queue.update_job(job)
            
        except Exception as e:
            # Update job as failed
            job.status = JobStatus.FAILED
            job.completed_at = datetime.utcnow()
            job.error = str(e)
            await job_queue.update_job(job)
        
        finally:
            self.current_job = None
```

#### 3. Resource Management

```python
class ResourceManager:
    def __init__(self):
        self.user_limits = {
            "max_concurrent_jobs": 10,
            "max_memory_ops_per_minute": 100,
            "max_sync_ops_per_hour": 5,
            "max_storage_mb": 1000
        }
    
    async def check_limits(self, user_id: str, operation: str) -> bool:
        """Check if user is within limits."""
        # Check concurrent jobs
        active_jobs = await redis.scard(f"user:{user_id}:jobs")
        if active_jobs >= self.user_limits["max_concurrent_jobs"]:
            raise LimitExceeded("Max concurrent jobs exceeded")
        
        # Check rate limits
        if operation.startswith("memory_"):
            count = await self.get_operation_count(
                user_id, "memory", 60  # Last minute
            )
            if count >= self.user_limits["max_memory_ops_per_minute"]:
                raise RateLimitExceeded("Memory operation rate limit exceeded")
        
        elif operation.startswith("sync_"):
            count = await self.get_operation_count(
                user_id, "sync", 3600  # Last hour
            )
            if count >= self.user_limits["max_sync_ops_per_hour"]:
                raise RateLimitExceeded("Sync operation rate limit exceeded")
        
        return True
    
    async def get_operation_count(self, user_id: str, op_type: str, window: int) -> int:
        """Get operation count in time window."""
        key = f"rate:{user_id}:{op_type}"
        now = time.time()
        
        # Remove old entries
        await redis.zremrangebyscore(key, 0, now - window)
        
        # Count remaining
        return await redis.zcard(key)
```

#### 4. API Gateway Layer

```python
class APIGateway:
    def __init__(self):
        self.job_queue = JobQueue(redis_client)
        self.resource_manager = ResourceManager()
    
    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP request."""
        user_id = request.get("user_id")
        operation = request.get("operation")
        
        try:
            # Check resource limits
            await self.resource_manager.check_limits(user_id, operation)
            
            # Determine priority
            priority = self.get_priority(operation)
            
            # Create job
            job = Job(
                id=str(uuid.uuid4()),
                user_id=user_id,
                operation=operation,
                priority=priority,
                payload=request.get("payload", {}),
                status=JobStatus.QUEUED,
                created_at=datetime.utcnow()
            )
            
            # Submit job
            job_id = await self.job_queue.submit(job)
            
            # For high-priority operations, wait for completion
            if priority in [JobPriority.CRITICAL, JobPriority.HIGH]:
                result = await self.wait_for_job(job_id, timeout=30)
                return {
                    "status": "completed",
                    "result": result
                }
            else:
                # For low-priority, return job ID
                return {
                    "status": "queued",
                    "job_id": job_id,
                    "message": "Use get_job_status to check progress"
                }
            
        except LimitExceeded as e:
            return {
                "status": "error",
                "error": str(e),
                "retry_after": e.retry_after
            }
    
    def get_priority(self, operation: str) -> JobPriority:
        """Determine job priority based on operation."""
        if operation in ["store_memory", "retrieve_memory"]:
            return JobPriority.HIGH
        elif operation in ["sync_repository", "batch_analyze"]:
            return JobPriority.LOW
        else:
            return JobPriority.NORMAL
```

#### 5. Progress Tracking

```python
class ProgressTracker:
    async def update_progress(self, job_id: str, progress: Dict[str, Any]):
        """Update job progress."""
        # Store in Redis for real-time updates
        await redis.hset(f"job:{job_id}:progress", mapping=progress)
        
        # Publish to subscribers
        await redis.publish(f"job:{job_id}:progress", json.dumps(progress))
    
    async def get_progress(self, job_id: str) -> Dict[str, Any]:
        """Get current job progress."""
        progress = await redis.hgetall(f"job:{job_id}:progress")
        return progress or {"status": "unknown"}
    
    async def subscribe_to_progress(self, job_id: str):
        """Subscribe to real-time progress updates."""
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"job:{job_id}:progress")
        
        async for message in pubsub.listen():
            if message["type"] == "message":
                yield json.loads(message["data"])
```

### Deployment Architecture

#### 1. Container Structure
```yaml
services:
  api-gateway:
    image: mcp-memory/api-gateway
    replicas: 3
    environment:
      - REDIS_URL=redis://redis:6379
      - MAX_REQUESTS_PER_SECOND=1000
    
  memory-workers:
    image: mcp-memory/worker
    replicas: 10
    environment:
      - WORKER_TYPE=memory
      - WORKER_COUNT=4
  
  code-workers:
    image: mcp-memory/worker
    replicas: 3
    environment:
      - WORKER_TYPE=code_intelligence
      - WORKER_COUNT=2
  
  redis:
    image: redis:7-alpine
    volumes:
      - redis-data:/data
  
  chromadb:
    image: chromadb/chroma
    environment:
      - CHROMA_SERVER_AUTH_PROVIDER=token
      - CHROMA_SERVER_AUTH_TOKEN=${CHROMA_TOKEN}
  
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_DB=mcp_jobs
    volumes:
      - postgres-data:/var/lib/postgresql/data
```

#### 2. Monitoring Stack
```yaml
monitoring:
  prometheus:
    scrape_configs:
      - job_name: 'mcp-memory'
        static_configs:
          - targets: ['api-gateway:9090', 'workers:9090']
  
  grafana:
    dashboards:
      - job-queue-depth
      - worker-utilization
      - operation-latency
      - error-rates
      - user-quotas
```

### Migration Strategy

#### Phase 1: Foundation (Week 1-2)
1. Implement job queue system
2. Create worker pool framework
3. Add progress tracking
4. Basic resource limits

#### Phase 2: Integration (Week 3-4)
1. Integrate memory operations
2. Migrate code intelligence operations
3. Add monitoring and metrics
4. Implement rate limiting

#### Phase 3: Optimization (Week 5-6)
1. Performance tuning
2. Advanced scheduling algorithms
3. Auto-scaling policies
4. Chaos testing

### Key Benefits

1. **Scalability**
   - Horizontal scaling of workers
   - Queue-based backpressure
   - Distributed processing

2. **Isolation**
   - User operations isolated
   - Resource limits enforced
   - Fair scheduling

3. **Reliability**
   - Job persistence
   - Automatic retries
   - Graceful degradation

4. **Observability**
   - Real-time progress
   - Comprehensive metrics
   - Audit trails

5. **Performance**
   - Async throughout
   - Optimized for throughput
   - Predictable latency