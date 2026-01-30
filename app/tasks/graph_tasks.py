"""
Graph Building Celery Tasks

Contains asynchronous task definitions for graph building operations.
These tasks are executed by Celery workers and communicate results
via Redis.

Author: ScenicPathFinder
"""

import logging
from typing import Dict, Any, Optional, Tuple

from celery import current_task
from celery.exceptions import SoftTimeLimitExceeded

# Import from parent package's celery app
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
from celery_app import celery

from app.services.core.graph_builder import build_graph, find_region_for_bbox
from app.services.core.cache_manager import get_cache_manager


# Configure logging for tasks
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@celery.task(bind=True, name='tasks.build_graph')
def build_graph_task(
    self,
    region_name: str,
    bbox: Optional[Tuple[float, float, float, float]],
    greenness_mode: str = 'FAST',
    elevation_mode: str = 'OFF',
    normalisation_mode: str = 'STATIC'
) -> Dict[str, Any]:
    """
    Celery task to build and process a graph for the specified region.
    
    This task handles the expensive graph building process asynchronously,
    allowing the Flask API to return immediately with a task ID.
    
    Args:
        region_name: Name identifier for the region (e.g., 'bristol').
        bbox: Bounding box tuple (min_lat, min_lon, max_lat, max_lon).
        greenness_mode: Greenness processing mode ('FAST', 'EDGE_SAMPLING', 'NOVACK').
        elevation_mode: Elevation processing mode ('OFF', 'API', 'LOCAL').
        normalisation_mode: Normalisation mode ('STATIC', 'DYNAMIC').
    
    Returns:
        Dictionary containing build metadata:
        - status: 'complete' or 'failed'
        - region_name: Name of the region
        - node_count: Number of nodes in the graph
        - edge_count: Number of edges in the graph
        - timings: Processing time breakdown
        - error: Error message (only if status is 'failed')
    
    Note:
        The graph itself is NOT returned; it is saved to the disk cache.
        The API should load the graph from cache after task completion.
    """
    task_id = self.request.id
    logger.info(f"[Task {task_id}] Starting graph build for region: {region_name}")
    logger.info(f"[Task {task_id}] Modes - Greenness: {greenness_mode}, Elevation: {elevation_mode}")
    
    # Update task state to show we're actively building
    self.update_state(
        state='BUILDING',
        meta={
            'region_name': region_name,
            'stage': 'initialising',
            'progress': 0
        }
    )
    
    try:
        # Build the graph using the stateless builder
        result = build_graph(
            bbox=bbox,
            region_name=region_name,
            greenness_mode=greenness_mode,
            elevation_mode=elevation_mode,
            normalisation_mode=normalisation_mode,
            save_to_cache=True  # Always save to disk cache
        )
        
        logger.info(
            f"[Task {task_id}] Graph build complete for {region_name}: "
            f"{result.node_count} nodes, {result.edge_count} edges"
        )
        
        # Return metadata only (NOT the graph - that's in disk cache)
        return {
            'status': 'complete',
            **result.to_metadata()
        }
        
    except SoftTimeLimitExceeded:
        # Task took too long - log and return failure
        logger.error(f"[Task {task_id}] Soft time limit exceeded for region: {region_name}")
        return {
            'status': 'failed',
            'region_name': region_name,
            'error': 'Graph build exceeded time limit. Try a smaller region or simpler processing mode.'
        }
        
    except Exception as e:
        # Unexpected error - log full traceback
        logger.exception(f"[Task {task_id}] Graph build failed for region: {region_name}")
        return {
            'status': 'failed',
            'region_name': region_name,
            'error': str(e)
        }


@celery.task(name='tasks.check_cache')
def check_cache_task(
    region_name: str,
    greenness_mode: str = 'FAST',
    elevation_mode: str = 'OFF',
    pbf_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Celery task to check if a cached graph exists and is valid.
    
    This is a lightweight task that can be used to check cache status
    before deciding whether to enqueue a full build.
    
    Args:
        region_name: Name identifier for the region.
        greenness_mode: Greenness processing mode.
        elevation_mode: Elevation processing mode.
        pbf_path: Optional path to the PBF file for modification time check.
    
    Returns:
        Dictionary containing:
        - is_valid: Boolean indicating if cache is valid
        - region_name: Name of the region
    """
    cache_mgr = get_cache_manager()
    is_valid = cache_mgr.is_cache_valid(region_name, greenness_mode, elevation_mode, pbf_path)
    
    return {
        'is_valid': is_valid,
        'region_name': region_name,
        'greenness_mode': greenness_mode,
        'elevation_mode': elevation_mode
    }
