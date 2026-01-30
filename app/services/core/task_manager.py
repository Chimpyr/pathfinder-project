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
                return existing_task_id.decode('utf-8')
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
        # Check for existing task first
        existing_task_id = self.get_existing_task(region_name, greenness_mode, elevation_mode)
        if existing_task_id:
            logger.info(f"[TaskManager] Reusing existing task {existing_task_id} for {region_name}")
            return {
                'task_id': existing_task_id,
                'is_new': False,
                'error': None
            }
        
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
            
            # Set the lock to prevent duplicate tasks
            if self.redis_client:
                lock_key = self._get_lock_key(region_name, greenness_mode, elevation_mode)
                self.redis_client.setex(lock_key, self.lock_timeout, task_id)
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
