"""
Celery Application Configuration

This module configures the Celery application for asynchronous graph building.
Uses Redis as the message broker and result backend.

Usage:
    Start worker: celery -A celery_app worker --loglevel=info
    
Author: ScenicPathFinder
"""

import os
import warnings
from celery import Celery

# Suppress noisy pandas warnings from pyrosm library
# These are internal to pyrosm and don't affect our functionality
warnings.filterwarnings('ignore', category=FutureWarning, module='pyrosm')
warnings.filterwarnings('ignore', message='.*ChainedAssignment.*')
warnings.filterwarnings('ignore', message='.*copy of a DataFrame.*')


def make_celery() -> Celery:
    """
    Create and configure the Celery application.
    
    Returns:
        Celery: Configured Celery application instance.
    """
    # Broker and result backend URLs from environment or defaults
    broker_url = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    result_backend = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
    
    celery_app = Celery(
        'scenic_pathfinder',
        broker=broker_url,
        backend=result_backend,
        include=['app.tasks.graph_tasks']
    )
    
    # Configuration
    celery_app.conf.update(
        # Serialisation - using pickle for NetworkX graph compatibility
        # Note: Only primitives should be returned from tasks, not graphs
        task_serializer='pickle',
        result_serializer='json',  # Results are primitives only
        accept_content=['pickle', 'json'],
        
        # Task execution settings
        task_time_limit=1200,  # 20 minutes hard limit (NOVACK mode can be slow)
        task_soft_time_limit=1100,  # 18 minutes soft limit for graceful cleanup
        
        # Worker settings
        worker_prefetch_multiplier=1,  # Process one task at a time
        worker_concurrency=1,  # Single worker thread (graph building is CPU-heavy)
        worker_max_tasks_per_child=1,  # Force restart after each task to release memory (CRITICAL for large graphs)
        
        # Result settings
        result_expires=3600,  # Results expire after 1 hour
        
        # Task tracking
        task_track_started=True,  # Track when tasks start
        task_send_sent_event=True,  # Send event when task is sent to worker
    )
    
    return celery_app


# Create the Celery application instance
celery = make_celery()


if __name__ == '__main__':
    # Allow running celery directly for testing
    celery.start()
