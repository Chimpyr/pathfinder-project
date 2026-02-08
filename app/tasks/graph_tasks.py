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
    
    # Lazy import to avoid circular dependency
    from app.services.core.task_manager import get_task_manager
    
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
    
    finally:
        # Critical: Always clear the lock so subsequent requests can trigger new builds
        # if the cache is missing or deleted.
        try:
            tm = get_task_manager()
            tm.clear_lock(region_name, greenness_mode, elevation_mode)
            logger.info(f"[Task {task_id}] Cleared lock for {region_name}")
        except Exception as e:
            logger.error(f"[Task {task_id}] Failed to clear lock: {e}")


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


@celery.task(bind=True, name='tasks.build_tile')
def build_tile_task(
    self,
    tile_id: str,
    region_name: str,
    greenness_mode: str = 'FAST',
    elevation_mode: str = 'OFF',
    normalisation_mode: str = 'STATIC',
    tile_size_km: float = 15,
    tile_overlap_km: float = 1
) -> Dict[str, Any]:
    """
    Celery task to build and cache a single tile (ADR-007).
    
    This task builds a graph for a specific tile using the tile-based
    caching strategy. Multiple tiles can be built in parallel by
    separate workers.
    
    Args:
        tile_id: Tile identifier (e.g., '51.45_-2.55').
        region_name: Name identifier for the region (e.g., 'bristol').
        greenness_mode: Greenness processing mode.
        elevation_mode: Elevation processing mode.
        normalisation_mode: Normalisation mode.
        tile_size_km: Size of each tile in kilometres.
        tile_overlap_km: Overlap buffer for tile boundaries.
    
    Returns:
        Dictionary containing build metadata.
    """
    import time
    task_id = self.request.id[:8]  # Short ID for cleaner logs
    tile_tag = f"[TILE:{tile_id}]"  # Unique tag for filtering parallel logs
    
    # =========================================================================
    # STAGE 0: Initialisation
    # =========================================================================
    start_time = time.time()
    logger.info(f"{tile_tag} ========================================")
    logger.info(f"{tile_tag} TILE BUILD STARTED")
    logger.info(f"{tile_tag} Task ID: {task_id}")
    logger.info(f"{tile_tag} Region: {region_name}")
    logger.info(f"{tile_tag} Size: {tile_size_km}km, Overlap: {tile_overlap_km}km")
    logger.info(f"{tile_tag} Greenness: {greenness_mode}, Elevation: {elevation_mode}")
    logger.info(f"{tile_tag} ========================================")
    
    # Update task state
    self.update_state(
        state='BUILDING',
        meta={
            'tile_id': tile_id,
            'region_name': region_name,
            'stage': 'initialising',
            'progress': 0
        }
    )
    
    # Lazy import to avoid circular dependency
    from app.services.core.task_manager import get_task_manager
    from app.services.core.tile_utils import get_tile_bbox
    from app.services.core.data_loader import OSMDataLoader
    
    timings = {}
    
    try:
        # =====================================================================
        # STAGE 1: Calculate tile bounding box
        # =====================================================================
        stage_start = time.time()
        logger.info(f"{tile_tag} [STAGE 1/5] Calculating tile bbox...")
        
        tile_bbox = get_tile_bbox(tile_id, tile_size_km, tile_overlap_km)
        logger.info(f"{tile_tag} Tile bbox: ({tile_bbox[0]:.4f}, {tile_bbox[1]:.4f}) -> ({tile_bbox[2]:.4f}, {tile_bbox[3]:.4f})")
        
        timings['bbox_calc'] = time.time() - stage_start
        logger.info(f"{tile_tag} [STAGE 1/5] Complete ({timings['bbox_calc']:.2f}s)")
        
        self.update_state(state='BUILDING', meta={'tile_id': tile_id, 'stage': 'loading_pbf', 'progress': 10})
        
        # =====================================================================
        # STAGE 2: Ensure PBF data exists
        # =====================================================================
        stage_start = time.time()
        logger.info(f"{tile_tag} [STAGE 2/5] Ensuring PBF data...")
        
        loader = OSMDataLoader()
        loader.ensure_data_for_bbox(tile_bbox)
        logger.info(f"{tile_tag} PBF: {loader.file_path}")
        
        timings['pbf_check'] = time.time() - stage_start
        logger.info(f"{tile_tag} [STAGE 2/5] Complete ({timings['pbf_check']:.2f}s)")
        
        self.update_state(state='BUILDING', meta={'tile_id': tile_id, 'stage': 'building_graph', 'progress': 20})
        
        # =====================================================================
        # STAGE 3: Build the graph (most expensive)
        # =====================================================================
        stage_start = time.time()
        logger.info(f"{tile_tag} [STAGE 3/5] Building graph (this may take 2-3 minutes)...")
        
        result = build_graph(
            bbox=tile_bbox,
            region_name=region_name,
            greenness_mode=greenness_mode,
            elevation_mode=elevation_mode,
            normalisation_mode=normalisation_mode,
            save_to_cache=False  # We'll save with tile_id ourselves
        )
        
        timings['graph_build'] = time.time() - stage_start
        logger.info(f"{tile_tag} Graph built: {result.node_count:,} nodes, {result.edge_count:,} edges")
        logger.info(f"{tile_tag} [STAGE 3/5] Complete ({timings['graph_build']:.1f}s)")
        
        self.update_state(state='BUILDING', meta={'tile_id': tile_id, 'stage': 'saving_cache', 'progress': 80})
        
        # =====================================================================
        # STAGE 4: Save to cache with tile_id
        # =====================================================================
        stage_start = time.time()
        logger.info(f"{tile_tag} [STAGE 4/5] Saving to cache...")
        
        cache_mgr = get_cache_manager()
        cache_mgr.save_graph(
            result.graph, region_name, greenness_mode, elevation_mode,
            pbf_path=loader.file_path, tile_id=tile_id
        )
        
        timings['cache_save'] = time.time() - stage_start
        logger.info(f"{tile_tag} [STAGE 4/5] Complete ({timings['cache_save']:.2f}s)")
        
        self.update_state(state='BUILDING', meta={'tile_id': tile_id, 'stage': 'finalising', 'progress': 95})
        
        # =====================================================================
        # STAGE 5: Complete
        # =====================================================================
        total_time = time.time() - start_time
        timings['total'] = total_time
        
        logger.info(f"{tile_tag} ========================================")
        logger.info(f"{tile_tag} TILE BUILD COMPLETE")
        logger.info(f"{tile_tag} Total time: {total_time:.1f}s")
        logger.info(f"{tile_tag} Breakdown: bbox={timings['bbox_calc']:.1f}s, pbf={timings['pbf_check']:.1f}s, "
                    f"build={timings['graph_build']:.1f}s, save={timings['cache_save']:.1f}s")
        logger.info(f"{tile_tag} ========================================")
        
        return {
            'status': 'complete',
            'tile_id': tile_id,
            'timings': timings,
            **result.to_metadata()
        }
        
    except SoftTimeLimitExceeded:
        total_time = time.time() - start_time
        logger.error(f"{tile_tag} ❌ TIMEOUT after {total_time:.1f}s")
        return {
            'status': 'failed',
            'tile_id': tile_id,
            'region_name': region_name,
            'error': 'Tile build exceeded time limit.'
        }
        
    except Exception as e:
        total_time = time.time() - start_time
        logger.exception(f"{tile_tag} ❌ FAILED after {total_time:.1f}s: {str(e)}")
        return {
            'status': 'failed',
            'tile_id': tile_id,
            'region_name': region_name,
            'error': str(e)
        }
    
    finally:
        # Clear the tile-specific lock
        try:
            tm = get_task_manager()
            tm.clear_tile_lock(tile_id, region_name, greenness_mode, elevation_mode)
            logger.info(f"{tile_tag} Lock cleared")
        except Exception as e:
            logger.error(f"{tile_tag} Failed to clear lock: {e}")


