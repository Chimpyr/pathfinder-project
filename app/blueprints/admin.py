"""
Admin Blueprint

Provides administrative endpoints for monitoring the async pipeline,
viewing cache status, and inspecting worker health.

These endpoints are intended for development and debugging purposes.
In production, consider adding authentication.

Endpoints:
    GET /admin/ - Dashboard overview (HTML)
    GET /admin/tasks/active - Active Celery tasks (JSON)
    GET /admin/cache - Cache statistics (JSON)
    GET /admin/workers - Worker health (JSON)
    GET /admin/config - Current configuration (JSON)

Author: ScenicPathFinder
"""

from flask import Blueprint, jsonify, render_template_string, current_app
from typing import Dict, Any

try:
    from celery_app import celery
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    celery = None

from app.services.core.cache_manager import get_cache_manager
from app.services.core.graph_manager import GraphManager


admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


# Simple HTML dashboard template
DASHBOARD_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>ScenicPathFinder Admin</title>
    <style>
        body { font-family: system-ui, -apple-system, sans-serif; padding: 2rem; background: #f5f5f5; }
        h1 { color: #2d3748; }
        .card { background: white; border-radius: 8px; padding: 1.5rem; margin: 1rem 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
        .card h2 { margin-top: 0; color: #4a5568; font-size: 1.25rem; }
        .status-ok { color: #38a169; }
        .status-warning { color: #d69e2e; }
        .status-error { color: #e53e3e; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 0.75rem; text-align: left; border-bottom: 1px solid #e2e8f0; }
        th { color: #718096; font-weight: 600; font-size: 0.875rem; }
        pre { background: #2d3748; color: #e2e8f0; padding: 1rem; border-radius: 4px; overflow-x: auto; }
        .btn { display: inline-block; padding: 0.5rem 1rem; background: #4299e1; color: white; text-decoration: none; border-radius: 4px; margin-right: 0.5rem; }
        .btn:hover { background: #3182ce; }
    </style>
</head>
<body>
    <h1>🗺️ ScenicPathFinder Admin</h1>
    
    <div class="card">
        <h2>🔧 Configuration</h2>
        <table>
            <tr><th>Setting</th><th>Value</th></tr>
            <tr><td>Async Mode</td><td class="{{ 'status-ok' if config.async_mode else 'status-warning' }}">{{ 'Enabled' if config.async_mode else 'Disabled' }}</td></tr>
            <tr><td>Greenness Mode</td><td>{{ config.greenness_mode }}</td></tr>
            <tr><td>Elevation Mode</td><td>{{ config.elevation_mode }}</td></tr>
            <tr><td>Water Mode</td><td>{{ config.water_mode }}</td></tr>
            <tr><td>Cost Function</td><td>{{ config.cost_function }}</td></tr>
        </table>
    </div>
    
    <div class="card">
        <h2>📦 Cache Status</h2>
        <table>
            <tr><th>Metric</th><th>Value</th></tr>
            <tr><td>Cached Regions (Memory)</td><td>{{ cache_info.cache_size }}</td></tr>
            <tr><td>Max Regions</td><td>{{ cache_info.max_regions }}</td></tr>
            <tr><td>Current Region</td><td>{{ cache_info.current_region or 'None' }}</td></tr>
        </table>
        {% if cache_info.cached_regions %}
        <h3>Cached Regions:</h3>
        <ul>
            {% for region in cache_info.cached_regions %}
            <li>{{ region }}</li>
            {% endfor %}
        </ul>
        {% endif %}
    </div>
    
    <div class="card">
        <h2>⚡ Workers</h2>
        {% if workers_available %}
            <p class="status-ok">✓ Celery workers connected</p>
            <pre>{{ workers | tojson(indent=2) }}</pre>
        {% else %}
            <p class="status-error">✗ No workers available (Celery not connected)</p>
        {% endif %}
    </div>
    
    <div class="card">
        <h2>📋 Active Tasks</h2>
        {% if active_tasks %}
            <pre>{{ active_tasks | tojson(indent=2) }}</pre>
        {% else %}
            <p>No active tasks</p>
        {% endif %}
    </div>
    
    <div class="card">
        <h2>🔗 API Endpoints</h2>
        <p><a class="btn" href="/admin/tasks/active">Tasks JSON</a>
           <a class="btn" href="/admin/cache">Cache JSON</a>
           <a class="btn" href="/admin/workers">Workers JSON</a>
           <a class="btn" href="/admin/config">Config JSON</a></p>
    </div>
</body>
</html>
'''


@admin_bp.route('/')
def dashboard():
    """
    Admin dashboard with overview of system status.
    
    Returns:
        HTML page with system overview.
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
    
    return render_template_string(
        DASHBOARD_TEMPLATE,
        config=config,
        cache_info=cache_info,
        workers_available=workers_available,
        workers=workers,
        active_tasks=active_tasks
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
