"""
Task Manager Module

Handles task enqueueing with duplicate prevention using Redis locks.
Prevents multiple workers from building the same region simultaneously.

Author: ScenicPathFinder
"""

import logging
from typing import Dict, Any, Optional, Tuple

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None

try:
    from flask import current_app, has_app_context
except ImportError:
    current_app = None
    def has_app_context(): return False

from app.services.core.tile_utils import DEFAULT_TILE_SIZE_KM, DEFAULT_TILE_OVERLAP_KM


# Configure logging
logger = logging.getLogger(__name__)


def get_redis_client() -> Optional['redis.Redis']:
    """
    Get a Redis client instance using configuration from Flask app.
    
    Returns:
        Redis client or None if Redis is not available.
    """
    if not REDIS_AVAILABLE:
        logger.warning("Redis package not installed")
        return None
    
    try:
        if has_app_context() and current_app:
            broker_url = current_app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
        else:
            import os
            broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
        
        # Parse Redis URL and create client
        return redis.from_url(broker_url)
    except Exception as e:
        logger.exception(f"Failed to create Redis client: {e}")
        return None


class TaskManager:
    """
    Manages task enqueueing with duplicate prevention.
    
    Uses Redis locks to ensure only one task is running for a given region
    at any time. If a task is already running for a region, returns the
    existing task ID instead of creating a new one.
    
    Attributes:
        lock_timeout: How long (seconds) the lock persists before expiring.
    """
    
    def __init__(self, lock_timeout: int = 900):
        """
        Initialise the TaskManager.
        
        Args:
            lock_timeout: Lock expiry time in seconds (default: 15 minutes).
        """
        self.lock_timeout = lock_timeout
        self._redis_client = None
    
    @property
    def redis_client(self) -> Optional['redis.Redis']:
        """Lazy-loaded Redis client."""
        if self._redis_client is None:
            self._redis_client = get_redis_client()
        return self._redis_client
    
    def _get_lock_key(self, region_name: str, greenness_mode: str, elevation_mode: str) -> str:
        """
        Generate a unique lock key for a region + mode combination.
        
        Args:
            region_name: Name of the region being built.
            greenness_mode: Greenness processing mode.
            elevation_mode: Elevation processing mode.
        
        Returns:
            Redis key string.
        """
        return f"building:{region_name}:{greenness_mode}:{elevation_mode}"
    
    def get_existing_task(
        self,
        region_name: str,
        greenness_mode: str = 'FAST',
        elevation_mode: str = 'OFF'
    ) -> Optional[str]:
        """
        Check if a task is already running for this region.
        
        Args:
            region_name: Name of the region.
            greenness_mode: Greenness processing mode.
            elevation_mode: Elevation processing mode.
        
        Returns:
            Existing task ID if found, None otherwise.
        """
        if not self.redis_client:
            return None
        
        lock_key = self._get_lock_key(region_name, greenness_mode, elevation_mode)
        
        try:
            existing_task_id = self.redis_client.get(lock_key)
            if existing_task_id:
                task_id = existing_task_id.decode('utf-8')
                
                # Check actual task state
                # If the task is finished but lock remains (stale), we should clear it
                from celery.result import AsyncResult
                # Import celery_app to ensure backend is configured
                from celery_app import celery
                
                result = AsyncResult(task_id, app=celery)
                if result.state in ['SUCCESS', 'FAILURE', 'REVOKED']:
                    logger.info(f"[TaskManager] Found stale lock for {region_name} (Task {task_id} is {result.state}). Clearing.")
                    self.redis_client.delete(lock_key)
                    return None
                
                return task_id
                
        except Exception as e:
            logger.exception(f"Error checking existing task: {e}")
        
        return None
    
    def enqueue_graph_build(
        self,
        region_name: str,
        bbox: Optional[Tuple[float, float, float, float]],
        greenness_mode: str = 'FAST',
        elevation_mode: str = 'OFF',
        normalisation_mode: str = 'STATIC'
    ) -> Dict[str, Any]:
        """
        Enqueue a graph build task, preventing duplicates.
        
        If a task is already running for this region + mode combination,
        returns the existing task ID instead of creating a new one.
        
        Args:
            region_name: Name of the region to build.
            bbox: Bounding box tuple (min_lat, min_lon, max_lat, max_lon).
            greenness_mode: Greenness processing mode.
            elevation_mode: Elevation processing mode.
            normalisation_mode: Normalisation mode.
        
        Returns:
            Dictionary with:
            - task_id: The Celery task ID
            - is_new: True if we created a new task, False if reusing existing
            - error: Error message if enqueueing failed
        """
        # Atomically claim the build slot BEFORE enqueueing using a single
        # SET key placeholder NX PX ttl_ms Redis call.  This is indivisible:
        # only one of N simultaneous callers succeeds; all others read the
        # winner's task ID once the key is updated with the real value.
        lock_key = self._get_lock_key(region_name, greenness_mode, elevation_mode)
        ttl_ms = self.lock_timeout * 1000

        if self.redis_client:
            claimed = self.redis_client.set(lock_key, "building", nx=True, px=ttl_ms)
            if not claimed:
                # Lost the race — return whoever won
                existing = self.redis_client.get(lock_key)
                if existing:
                    existing_id = existing.decode("utf-8")
                    if existing_id != "building":
                        logger.info(f"[TaskManager] Reusing existing task {existing_id} for {region_name}")
                        return {"task_id": existing_id, "is_new": False, "error": None}
                # Placeholder still set (winner not yet written real task_id)
                # Fall through — rare edge case: let this caller also enqueue
        else:
            # No Redis — non-atomic fallback
            existing_task_id = self.get_existing_task(region_name, greenness_mode, elevation_mode)
            if existing_task_id:
                return {"task_id": existing_task_id, "is_new": False, "error": None}

        # Import here to avoid circular imports
        try:
            from app.tasks.graph_tasks import build_graph_task
        except ImportError as e:
            logger.error(f"Failed to import Celery tasks: {e}")
            return {
                'task_id': None,
                'is_new': False,
                'error': 'Celery tasks not available'
            }
        
        try:
            # Enqueue the task
            task = build_graph_task.delay(
                region_name=region_name,
                bbox=bbox,
                greenness_mode=greenness_mode,
                elevation_mode=elevation_mode,
                normalisation_mode=normalisation_mode
            )
            task_id = task.id
            
            # Update the lock with the real task ID (replaces "building" placeholder)
            if self.redis_client:
                self.redis_client.set(lock_key, task_id, px=ttl_ms)
                logger.info(f"[TaskManager] Set lock {lock_key} for task {task_id}")
            
            logger.info(f"[TaskManager] Enqueued new task {task_id} for {region_name}")
            
            return {
                'task_id': task_id,
                'is_new': True,
                'error': None
            }
            
        except Exception as e:
            logger.exception(f"Failed to enqueue graph build task: {e}")
            return {
                'task_id': None,
                'is_new': False,
                'error': str(e)
            }
    
    def clear_lock(
        self,
        region_name: str,
        greenness_mode: str = 'FAST',
        elevation_mode: str = 'OFF'
    ) -> bool:
        """
        Manually clear a task lock (e.g., after task completion or failure).
        
        Args:
            region_name: Name of the region.
            greenness_mode: Greenness processing mode.
            elevation_mode: Elevation processing mode.
        
        Returns:
            True if lock was cleared, False otherwise.
        """
        if not self.redis_client:
            return False
        
        lock_key = self._get_lock_key(region_name, greenness_mode, elevation_mode)
        
        try:
            self.redis_client.delete(lock_key)
            logger.info(f"[TaskManager] Cleared lock {lock_key}")
            return True
        except Exception as e:
            logger.exception(f"Error clearing lock: {e}")
            return False
    
    # =========================================================================
    # Tile-Based Caching Methods (ADR-007)
    # =========================================================================
    
    def _get_tile_lock_key(
        self,
        tile_id: str,
        region_name: str,
        greenness_mode: str,
        elevation_mode: str
    ) -> str:
        """
        Generate a unique lock key for a tile + mode combination.
        
        Args:
            tile_id: Tile identifier (e.g., '51.45_-2.55').
            region_name: Name of the region.
            greenness_mode: Greenness processing mode.
            elevation_mode: Elevation processing mode.
        
        Returns:
            Redis key string.
        """
        return f"building_tile:{region_name}:{tile_id}:{greenness_mode}:{elevation_mode}"
    
    def get_existing_tile_task(
        self,
        tile_id: str,
        region_name: str,
        greenness_mode: str = 'FAST',
        elevation_mode: str = 'OFF'
    ) -> Optional[str]:
        """
        Check if a tile build task is already running.
        
        Args:
            tile_id: Tile identifier.
            region_name: Name of the region.
            greenness_mode: Greenness processing mode.
            elevation_mode: Elevation processing mode.
        
        Returns:
            Existing task ID if found, None otherwise.
        """
        if not self.redis_client:
            return None
        
        lock_key = self._get_tile_lock_key(tile_id, region_name, greenness_mode, elevation_mode)
        
        try:
            existing_task_id = self.redis_client.get(lock_key)
            if existing_task_id:
                task_id = existing_task_id.decode('utf-8')
                
                # Check actual task state
                from celery.result import AsyncResult
                from celery_app import celery
                
                result = AsyncResult(task_id, app=celery)
                if result.state in ['SUCCESS', 'FAILURE', 'REVOKED']:
                    logger.info(f"[TaskManager] Found stale tile lock for {tile_id} (Task {task_id} is {result.state}). Clearing.")
                    self.redis_client.delete(lock_key)
                    return None
                
                return task_id
                
        except Exception as e:
            logger.exception(f"Error checking existing tile task: {e}")
        
        return None
    
        # Import constants for defaults (lazy import to resolve ONLY if needed, or assume top-level if safe)
        # However, for signature defaults, we need them at definition time.
        # We'll import them at top level of file.
        
    def enqueue_tile_build(
        self,
        tile_id: str,
        region_name: str,
        greenness_mode: str = 'FAST',
        elevation_mode: str = 'OFF',
        normalisation_mode: str = 'STATIC',
        tile_size_km: float = DEFAULT_TILE_SIZE_KM,
        tile_overlap_km: float = DEFAULT_TILE_OVERLAP_KM
    ) -> Dict[str, Any]:
        """
        Enqueue a tile build task, preventing duplicates.
        
        If a task is already running for this tile, returns the existing
        task ID instead of creating a new one.
        
        Args:
            tile_id: Tile identifier.
            region_name: Name of the region.
            greenness_mode: Greenness processing mode.
            elevation_mode: Elevation processing mode.
            normalisation_mode: Normalisation mode.
            tile_size_km: Size of each tile in kilometres.
            tile_overlap_km: Overlap buffer for tile boundaries.
        
        Returns:
            Dictionary with task_id, is_new, and error (if any).
        """
        # Atomically claim the tile build slot BEFORE enqueueing.
        # A single SET key placeholder NX PX ttl_ms call is indivisible:
        # only one of N simultaneous callers succeeds; the rest return
        # immediately with the winner's task ID once the key is updated.
        lock_key = self._get_tile_lock_key(tile_id, region_name, greenness_mode, elevation_mode)
        ttl_ms = self.lock_timeout * 1000

        if self.redis_client:
            claimed = self.redis_client.set(lock_key, "building", nx=True, px=ttl_ms)
            if not claimed:
                # Lost the race — return whoever won
                existing = self.redis_client.get(lock_key)
                if existing:
                    existing_id = existing.decode("utf-8")
                    if existing_id != "building":
                        logger.info(f"[TaskManager] Reusing existing task {existing_id} for tile {tile_id}")
                        return {"task_id": existing_id, "is_new": False, "error": None}
                # Placeholder still set (winner not yet written real task_id)
                # Fall through — rare edge case: let this caller also enqueue
        else:
            # No Redis — non-atomic fallback
            existing_task_id = self.get_existing_tile_task(tile_id, region_name, greenness_mode, elevation_mode)
            if existing_task_id:
                return {"task_id": existing_task_id, "is_new": False, "error": None}

        # Import here to avoid circular imports
        try:
            from app.tasks.graph_tasks import build_tile_task
        except ImportError as e:
            logger.error(f"Failed to import Celery tile task: {e}")
            return {
                'task_id': None,
                'is_new': False,
                'error': 'Celery tile tasks not available'
            }
        
        try:
            # Enqueue the task
            task = build_tile_task.delay(
                tile_id=tile_id,
                region_name=region_name,
                greenness_mode=greenness_mode,
                elevation_mode=elevation_mode,
                normalisation_mode=normalisation_mode,
                tile_size_km=tile_size_km,
                tile_overlap_km=tile_overlap_km
            )
            task_id = task.id
            
            # Update the lock with the real task ID (replaces "building" placeholder)
            if self.redis_client:
                self.redis_client.set(lock_key, task_id, px=ttl_ms)
                logger.info(f"[TaskManager] Set tile lock {lock_key} for task {task_id}")
            
            logger.info(f"[TaskManager] Enqueued new tile task {task_id} for tile {tile_id}")
            
            return {
                'task_id': task_id,
                'is_new': True,
                'error': None
            }
            
        except Exception as e:
            logger.exception(f"Failed to enqueue tile build task: {e}")
            return {
                'task_id': None,
                'is_new': False,
                'error': str(e)
            }
    
    def clear_tile_lock(
        self,
        tile_id: str,
        region_name: str,
        greenness_mode: str = 'FAST',
        elevation_mode: str = 'OFF'
    ) -> bool:
        """
        Clear a tile-specific task lock.
        
        Args:
            tile_id: Tile identifier.
            region_name: Name of the region.
            greenness_mode: Greenness processing mode.
            elevation_mode: Elevation processing mode.
        
        Returns:
            True if lock was cleared, False otherwise.
        """
        if not self.redis_client:
            return False
        
        lock_key = self._get_tile_lock_key(tile_id, region_name, greenness_mode, elevation_mode)
        
        try:
            self.redis_client.delete(lock_key)
            logger.info(f"[TaskManager] Cleared tile lock {lock_key}")
            return True
        except Exception as e:
            logger.exception(f"Error clearing tile lock: {e}")
            return False


# Module-level singleton
_task_manager: Optional[TaskManager] = None


def get_task_manager() -> TaskManager:
    """
    Get the singleton TaskManager instance.
    
    Returns:
        TaskManager instance.
    """
    global _task_manager
    if _task_manager is None:
        # Get lock timeout from config if available
        lock_timeout = 900  # Default 15 minutes
        if has_app_context() and current_app:
            lock_timeout = current_app.config.get('TASK_LOCK_TIMEOUT', 900)
        _task_manager = TaskManager(lock_timeout=lock_timeout)
    return _task_manager

