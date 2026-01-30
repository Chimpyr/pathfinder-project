"""
Admin Blueprint

Provides administrative endpoints for monitoring the async pipeline,
viewing cache status, managing caches, and running test scenarios.

Endpoints:
    GET  /admin/                - Dashboard overview (HTML)
    GET  /admin/tasks/active    - Active Celery tasks (JSON)
    GET  /admin/cache           - Cache statistics (JSON)
    DELETE /admin/cache/<key>   - Delete specific cache file
    DELETE /admin/cache/all     - Delete all cache files
    GET  /admin/workers         - Worker health (JSON)
    GET  /admin/config          - Current configuration (JSON)

Author: ScenicPathFinder
"""

from flask import Blueprint, jsonify, render_template, current_app
from typing import Dict, Any, List
import os

try:
    from celery_app import celery
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    celery = None

from app.services.core.cache_manager import get_cache_manager
from app.services.core.graph_manager import GraphManager


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# Test scenarios for one-click testing
TEST_SCENARIOS: List[Dict[str, Any]] = [
    {
        'id': 'uwe-fishponds',
        'name': 'UWE → Fishponds',
        'description': 'Bristol local route through Stoke Park',
        'start_lat': 51.500,
        'start_lon': -2.549,
        'end_lat': 51.476,
        'end_lon': -2.524
    },
    {
        'id': 'bath-city',
        'name': 'Bath City Centre',
        'description': 'Short urban route in Bath',
        'start_lat': 51.381,
        'start_lon': -2.359,
        'end_lat': 51.389,
        'end_lon': -2.341
    },
    {
        'id': 'oxford',
        'name': 'Oxford Route',
        'description': 'Different region test (Oxfordshire)',
        'start_lat': 51.818,
        'start_lon': -1.286,
        'end_lat': 51.804,
        'end_lon': -1.275
    },
    {
        'id': 'bristol-harbour',
        'name': 'Bristol Harbour',
        'description': 'Water feature test route',
        'start_lat': 51.449,
        'start_lon': -2.600,
        'end_lat': 51.454,
        'end_lon': -2.587
    }
]


@admin_bp.route('/')
def dashboard():
    """
    Admin dashboard with overview of system status.
    
    Returns:
        HTML page with system overview, test scenarios, and cache management.
    """
    # Get configuration
    config = {
        'async_mode': current_app.config.get('ASYNC_MODE', False),
        'greenness_mode': current_app.config.get('GREENNESS_MODE', 'FAST'),
        'elevation_mode': current_app.config.get('ELEVATION_MODE', 'OFF'),
        'water_mode': current_app.config.get('WATER_MODE', 'FAST'),
        'cost_function': current_app.config.get('COST_FUNCTION', 'WSM_ADDITIVE'),
    }
    
    # Get cache info
    cache_info = GraphManager.get_cache_info()
    
    # Get cache files
    cache_mgr = get_cache_manager()
    cache_files = []
    try:
        if cache_mgr.cache_dir.exists():
            for cache_file in cache_mgr.cache_dir.glob('*.pickle'):
                stat = cache_file.stat()
                cache_files.append({
                    'filename': cache_file.name,
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'modified': stat.st_mtime
                })
    except Exception as e:
        current_app.logger.warning(f"Failed to list cache files: {e}")
    
    # Get worker info
    workers_available = False
    workers = {}
    active_tasks = {}
    
    if CELERY_AVAILABLE and celery:
        try:
            inspect = celery.control.inspect()
            ping_result = inspect.ping()
            if ping_result:
                workers_available = True
                workers = ping_result
                active_tasks = inspect.active() or {}
        except Exception as e:
            current_app.logger.warning(f"Failed to inspect Celery workers: {e}")
    
    return render_template(
        'admin/admin.html',
        config=config,
        cache_info=cache_info,
        cache_files=cache_files,
        workers_available=workers_available,
        workers=workers,
        active_tasks=active_tasks,
        test_scenarios=TEST_SCENARIOS
    )


@admin_bp.route('/tasks/active')
def active_tasks() -> tuple:
    """
    Get currently active Celery tasks.
    
    Returns:
        JSON response with active and reserved tasks.
    """
    if not CELERY_AVAILABLE or celery is None:
        return jsonify({
            'error': 'Celery not available',
            'active': {},
            'reserved': {}
        }), 503
    
    try:
        inspect = celery.control.inspect()
        return jsonify({
            'active': inspect.active() or {},
            'reserved': inspect.reserved() or {},
            'scheduled': inspect.scheduled() or {}
        })
    except Exception as e:
        current_app.logger.exception(f"Failed to get active tasks: {e}")
        return jsonify({
            'error': str(e),
            'active': {},
            'reserved': {}
        }), 500


@admin_bp.route('/cache')
def cache_status() -> tuple:
    """
    Get cache statistics.
    
    Returns:
        JSON response with memory and disk cache info.
    """
    # Memory cache info from GraphManager
    memory_cache = GraphManager.get_cache_info()
    
    # Disk cache info from CacheManager
    cache_mgr = get_cache_manager()
    disk_cache = {
        'cache_directory': str(cache_mgr.cache_dir),
        'cache_files': []
    }
    
    # List cache files if directory exists
    try:
        if cache_mgr.cache_dir.exists():
            for cache_file in cache_mgr.cache_dir.glob('*.pickle'):
                stat = cache_file.stat()
                disk_cache['cache_files'].append({
                    'filename': cache_file.name,
                    'size_mb': round(stat.st_size / (1024 * 1024), 2),
                    'modified': stat.st_mtime
                })
    except Exception as e:
        current_app.logger.warning(f"Failed to list cache files: {e}")
    
    return jsonify({
        'memory_cache': memory_cache,
        'disk_cache': disk_cache
    })


@admin_bp.route('/cache/<filename>', methods=['DELETE'])
def delete_cache_file(filename: str) -> tuple:
    """
    Delete a specific cache file.
    
    Args:
        filename: Name of the cache file to delete.
    
    Returns:
        JSON response indicating success or failure.
    """
    cache_mgr = get_cache_manager()
    cache_path = cache_mgr.cache_dir / filename
    
    # Security check - prevent path traversal
    try:
        cache_path = cache_path.resolve()
        if not str(cache_path).startswith(str(cache_mgr.cache_dir.resolve())):
            return jsonify({
                'success': False,
                'error': 'Invalid path'
            }), 400
    except Exception:
        return jsonify({
            'success': False,
            'error': 'Invalid filename'
        }), 400
    
    if not cache_path.exists():
        return jsonify({
            'success': False,
            'error': 'File not found'
        }), 404
    
    try:
        cache_path.unlink()
        current_app.logger.info(f"Deleted cache file: {filename}")
        return jsonify({
            'success': True,
            'deleted': filename
        })
    except Exception as e:
        current_app.logger.exception(f"Failed to delete cache file: {filename}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@admin_bp.route('/cache/all', methods=['DELETE'])
def delete_all_cache() -> tuple:
    """
    Delete all cache files.
    
    Returns:
        JSON response with count of deleted files.
    """
    cache_mgr = get_cache_manager()
    deleted_count = 0
    errors = []
    
    try:
        if cache_mgr.cache_dir.exists():
            for cache_file in cache_mgr.cache_dir.glob('*.pickle'):
                try:
                    cache_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    errors.append(f"{cache_file.name}: {str(e)}")
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
    current_app.logger.info(f"Deleted {deleted_count} cache files")
    
    return jsonify({
        'success': True,
        'deleted_count': deleted_count,
        'errors': errors if errors else None
    })


@admin_bp.route('/workers')
def worker_status() -> tuple:
    """
    Get Celery worker health information.
    
    Returns:
        JSON response with worker ping, stats, and registered tasks.
    """
    if not CELERY_AVAILABLE or celery is None:
        return jsonify({
            'error': 'Celery not available',
            'ping': {},
            'stats': {},
            'registered': {}
        }), 503
    
    try:
        inspect = celery.control.inspect()
        return jsonify({
            'ping': inspect.ping() or {},
            'stats': inspect.stats() or {},
            'registered': inspect.registered() or {}
        })
    except Exception as e:
        current_app.logger.exception(f"Failed to get worker status: {e}")
        return jsonify({
            'error': str(e),
            'ping': {},
            'stats': {},
            'registered': {}
        }), 500


@admin_bp.route('/config')
def config_info() -> tuple:
    """
    Get current application configuration.
    
    Returns:
        JSON response with relevant configuration values.
    """
    return jsonify({
        'async_mode': current_app.config.get('ASYNC_MODE', False),
        'greenness_mode': current_app.config.get('GREENNESS_MODE', 'FAST'),
        'elevation_mode': current_app.config.get('ELEVATION_MODE', 'OFF'),
        'water_mode': current_app.config.get('WATER_MODE', 'FAST'),
        'social_mode': current_app.config.get('SOCIAL_MODE', 'FAST'),
        'normalisation_mode': current_app.config.get('NORMALISATION_MODE', 'STATIC'),
        'cost_function': current_app.config.get('COST_FUNCTION', 'WSM_ADDITIVE'),
        'max_cached_regions': current_app.config.get('MAX_CACHED_REGIONS', 3),
        'task_lock_timeout': current_app.config.get('TASK_LOCK_TIMEOUT', 900),
        'celery_broker_url': current_app.config.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    })


@admin_bp.route('/scenarios')
def get_scenarios() -> tuple:
    """
    Get available test scenarios.
    
    Returns:
        JSON response with test scenario definitions.
    """
    return jsonify({
        'scenarios': TEST_SCENARIOS
    })
