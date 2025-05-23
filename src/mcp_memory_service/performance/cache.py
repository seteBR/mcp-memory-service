# src/mcp_memory_service/performance/cache.py
"""
Performance caching layer for code intelligence system.
Implements in-memory LRU cache with TTL for search results.
"""
import time
import hashlib
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict
import threading
import json

from ..models.memory import MemoryQueryResult

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Cache entry with TTL support."""
    data: Any
    created_at: float
    last_accessed: float
    access_count: int = 0
    ttl: float = 300.0  # 5 minutes default TTL
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        return time.time() - self.created_at > self.ttl
    
    def touch(self) -> None:
        """Update last accessed time and increment access count."""
        self.last_accessed = time.time()
        self.access_count += 1

class LRUCache:
    """Thread-safe LRU cache with TTL support."""
    
    def __init__(self, max_size: int = 1000, default_ttl: float = 300.0):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'expired': 0
        }
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Generate cache key from arguments."""
        # Create a deterministic key from arguments
        key_data = {
            'args': args,
            'kwargs': sorted(kwargs.items()) if kwargs else {}
        }
        key_str = json.dumps(key_data, sort_keys=True, default=str)
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Get item from cache."""
        with self.lock:
            if key not in self.cache:
                self.stats['misses'] += 1
                return None
            
            entry = self.cache[key]
            
            # Check if expired
            if entry.is_expired():
                del self.cache[key]
                self.stats['expired'] += 1
                self.stats['misses'] += 1
                return None
            
            # Move to end (most recently used)
            self.cache.move_to_end(key)
            entry.touch()
            self.stats['hits'] += 1
            
            return entry.data
    
    def put(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """Put item in cache."""
        with self.lock:
            ttl = ttl or self.default_ttl
            now = time.time()
            
            entry = CacheEntry(
                data=value,
                created_at=now,
                last_accessed=now,
                ttl=ttl
            )
            
            self.cache[key] = entry
            self.cache.move_to_end(key)
            
            # Evict oldest if over max size
            while len(self.cache) > self.max_size:
                oldest_key = next(iter(self.cache))
                del self.cache[oldest_key]
                self.stats['evictions'] += 1
    
    def invalidate(self, pattern: Optional[str] = None) -> int:
        """Invalidate cache entries. If pattern provided, only matching keys."""
        with self.lock:
            if pattern is None:
                count = len(self.cache)
                self.cache.clear()
                return count
            
            # Remove keys matching pattern
            keys_to_remove = [k for k in self.cache.keys() if pattern in k]
            for key in keys_to_remove:
                del self.cache[key]
            
            return len(keys_to_remove)
    
    def cleanup_expired(self) -> int:
        """Remove expired entries from cache."""
        with self.lock:
            expired_keys = [
                key for key, entry in self.cache.items() 
                if entry.is_expired()
            ]
            
            for key in expired_keys:
                del self.cache[key]
            
            self.stats['expired'] += len(expired_keys)
            return len(expired_keys)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self.lock:
            total_requests = self.stats['hits'] + self.stats['misses']
            hit_rate = self.stats['hits'] / total_requests if total_requests > 0 else 0
            
            return {
                'size': len(self.cache),
                'max_size': self.max_size,
                'hits': self.stats['hits'],
                'misses': self.stats['misses'],
                'hit_rate': hit_rate,
                'evictions': self.stats['evictions'],
                'expired': self.stats['expired'],
                'total_requests': total_requests
            }

class SearchCache:
    """Specialized cache for search results."""
    
    def __init__(self, max_size: int = 500, default_ttl: float = 600.0):
        self.cache = LRUCache(max_size, default_ttl)
        logger.info(f"SearchCache initialized: max_size={max_size}, ttl={default_ttl}s")
    
    def get_search_results(self, query: str, repository: str = None, 
                          language: str = None, n_results: int = 10) -> Optional[List[MemoryQueryResult]]:
        """Get cached search results."""
        cache_key = self.cache._generate_key(
            'search', query=query, repository=repository, 
            language=language, n_results=n_results
        )
        
        results = self.cache.get(cache_key)
        if results:
            logger.debug(f"Cache HIT for search: '{query}' (key: {cache_key[:8]})")
        else:
            logger.debug(f"Cache MISS for search: '{query}' (key: {cache_key[:8]})")
        
        return results
    
    def cache_search_results(self, query: str, results: List[MemoryQueryResult],
                           repository: str = None, language: str = None, 
                           n_results: int = 10, ttl: float = None) -> None:
        """Cache search results."""
        cache_key = self.cache._generate_key(
            'search', query=query, repository=repository,
            language=language, n_results=n_results
        )
        
        self.cache.put(cache_key, results, ttl)
        logger.debug(f"Cached search results: '{query}' -> {len(results)} results (key: {cache_key[:8]})")
    
    def invalidate_search_cache(self, repository: str = None) -> int:
        """Invalidate search cache, optionally for specific repository."""
        pattern = f'"repository": "{repository}"' if repository else None
        count = self.cache.invalidate(pattern)
        logger.info(f"Invalidated {count} search cache entries" + 
                   (f" for repository '{repository}'" if repository else ""))
        return count
    
    def get_stats(self) -> Dict[str, Any]:
        """Get search cache statistics."""
        return self.cache.get_stats()

class StatsCache:
    """Specialized cache for repository statistics."""
    
    def __init__(self, max_size: int = 100, default_ttl: float = 1800.0):  # 30 minutes
        self.cache = LRUCache(max_size, default_ttl)
        logger.info(f"StatsCache initialized: max_size={max_size}, ttl={default_ttl}s")
    
    def get_stats(self, repository: str = None) -> Optional[Dict[str, Any]]:
        """Get cached repository statistics."""
        cache_key = self.cache._generate_key('stats', repository=repository)
        
        stats = self.cache.get(cache_key)
        if stats:
            logger.debug(f"Cache HIT for stats: repository='{repository}' (key: {cache_key[:8]})")
        else:
            logger.debug(f"Cache MISS for stats: repository='{repository}' (key: {cache_key[:8]})")
        
        return stats
    
    def cache_stats(self, stats: Dict[str, Any], repository: str = None, ttl: float = None) -> None:
        """Cache repository statistics."""
        cache_key = self.cache._generate_key('stats', repository=repository)
        
        self.cache.put(cache_key, stats, ttl)
        logger.debug(f"Cached stats: repository='{repository}' (key: {cache_key[:8]})")
    
    def invalidate_stats_cache(self, repository: str = None) -> int:
        """Invalidate stats cache, optionally for specific repository."""
        if repository:
            pattern = f'"repository": "{repository}"'
            count = self.cache.invalidate(pattern)
            logger.info(f"Invalidated stats cache for repository '{repository}'")
        else:
            count = self.cache.invalidate()
            logger.info("Invalidated all stats cache entries")
        return count
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache performance statistics."""
        return self.cache.get_stats()

class CacheManager:
    """Central cache manager for code intelligence system."""
    
    def __init__(self, search_cache_size: int = 500, stats_cache_size: int = 100,
                 search_ttl: float = 600.0, stats_ttl: float = 1800.0):
        self.search_cache = SearchCache(search_cache_size, search_ttl)
        self.stats_cache = StatsCache(stats_cache_size, stats_ttl)
        
        # Start background cleanup task
        self._start_cleanup_task()
        
        logger.info("CacheManager initialized with search and stats caches")
    
    def _start_cleanup_task(self) -> None:
        """Start background task to clean up expired entries."""
        def cleanup_worker():
            while True:
                time.sleep(300)  # Run every 5 minutes
                try:
                    search_expired = self.search_cache.cache.cleanup_expired()
                    stats_expired = self.stats_cache.cache.cleanup_expired()
                    
                    if search_expired > 0 or stats_expired > 0:
                        logger.info(f"Cleaned up expired cache entries: "
                                  f"search={search_expired}, stats={stats_expired}")
                except Exception as e:
                    logger.error(f"Error in cache cleanup task: {e}")
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
        logger.debug("Started background cache cleanup task")
    
    def invalidate_repository(self, repository: str) -> Dict[str, int]:
        """Invalidate all caches for a specific repository."""
        search_count = self.search_cache.invalidate_search_cache(repository)
        stats_count = self.stats_cache.invalidate_stats_cache(repository)
        
        logger.info(f"Invalidated all caches for repository '{repository}': "
                   f"search={search_count}, stats={stats_count}")
        
        return {
            'search_entries': search_count,
            'stats_entries': stats_count
        }
    
    def invalidate_all(self) -> Dict[str, int]:
        """Invalidate all caches."""
        search_count = self.search_cache.cache.invalidate()
        stats_count = self.stats_cache.cache.invalidate()
        
        logger.info(f"Invalidated all caches: search={search_count}, stats={stats_count}")
        
        return {
            'search_entries': search_count,
            'stats_entries': stats_count
        }
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics."""
        return {
            'search_cache': self.search_cache.get_stats(),
            'stats_cache': self.stats_cache.get_cache_stats()
        }

# Global cache manager instance
cache_manager = CacheManager()