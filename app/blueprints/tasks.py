"""
Task Status Blueprint

Provides endpoints for polling task status during async graph building.
Used when ASYNC_MODE is enabled and graph building is offloaded to Celery workers.

Endpoints:
    GET /api/task/<task_id> - Get task status and result

Author: ScenicPathFinder
"""

from flask import Blueprint, jsonify, current_app
from typing import Dict, Any

try:
    from celery.result import AsyncResult
    from celery_app import celery
    CELERY_AVAILABLE = True
except ImportError:
    CELERY_AVAILABLE = False
    celery = None
    AsyncResult = None


tasks_bp = Blueprint('tasks', __name__, url_prefix='/api/task')


@tasks_bp.route('/<task_id>', methods=['GET'])
def get_task_status(task_id: str) -> tuple:
    """
    Get the status of an asynchronous graph build task.
    
    Args:
        task_id: The Celery task ID returned when the task was enqueued.
    
    Returns:
        JSON response with task status and result data.
        
        Status values:
        - pending: Task is queued but not yet started
        - building: Task is actively processing
        - complete: Task finished successfully
        - failed: Task failed with an error
        - unknown: Celery is not available or task not found
    
    Response format:
        {
            "status": "pending" | "building" | "complete" | "failed" | "unknown",
            "task_id": "...",
            "result": { ... } | null,
            "error": "..." | null
        }
    """
    if not CELERY_AVAILABLE or celery is None:
        return jsonify({
            'status': 'unknown',
            'task_id': task_id,
            'error': 'Celery is not available. Async mode may not be properly configured.'
        }), 503
    
    try:
        result = AsyncResult(task_id, app=celery)
        
        # Map Celery states to our API states
        state = result.state
        
        if state == 'PENDING':
            # Task is waiting in queue
            return jsonify({
                'status': 'pending',
                'task_id': task_id,
                'result': None,
                'error': None
            })
            
        elif state == 'BUILDING':
            # Custom state: task is actively building graph
            meta = result.info or {}
            return jsonify({
                'status': 'building',
                'task_id': task_id,
                'result': {
                    'region_name': meta.get('region_name'),
                    'stage': meta.get('stage'),
                    'progress': meta.get('progress', 0)
                },
                'error': None
            })
            
        elif state == 'SUCCESS':
            # Task completed successfully
            task_result = result.result or {}
            
            # Check if the task itself reported failure
            if task_result.get('status') == 'failed':
                return jsonify({
                    'status': 'failed',
                    'task_id': task_id,
                    'result': None,
                    'error': task_result.get('error', 'Task reported failure')
                })
            
            return jsonify({
                'status': 'complete',
                'task_id': task_id,
                'result': {
                    'region_name': task_result.get('region_name'),
                    'node_count': task_result.get('node_count'),
                    'edge_count': task_result.get('edge_count'),
                    'total_time': task_result.get('total_time'),
                    'timings': task_result.get('timings')
                },
                'error': None
            })
            
        elif state == 'FAILURE':
            # Task raised an exception
            error_msg = str(result.result) if result.result else 'Unknown error'
            return jsonify({
                'status': 'failed',
                'task_id': task_id,
                'result': None,
                'error': error_msg
            })
            
        elif state == 'REVOKED':
            # Task was cancelled
            return jsonify({
                'status': 'failed',
                'task_id': task_id,
                'result': None,
                'error': 'Task was cancelled'
            })
            
        else:
            # Unknown state
            return jsonify({
                'status': 'unknown',
                'task_id': task_id,
                'result': None,
                'error': f'Unknown task state: {state}'
            })
            
    except Exception as e:
        current_app.logger.exception(f"Error checking task status: {task_id}")
        return jsonify({
            'status': 'unknown',
            'task_id': task_id,
            'result': None,
            'error': f'Error checking task status: {str(e)}'
        }), 500


@tasks_bp.route('/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id: str) -> tuple:
    """
    Cancel a running or pending task.
    
    Args:
        task_id: The Celery task ID to cancel.
    
    Returns:
        JSON response confirming cancellation.
    """
    if not CELERY_AVAILABLE or celery is None:
        return jsonify({
            'success': False,
            'task_id': task_id,
            'error': 'Celery is not available'
        }), 503
    
    try:
        result = AsyncResult(task_id, app=celery)
        result.revoke(terminate=True)
        
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': 'Task cancellation requested'
        })
        
    except Exception as e:
        current_app.logger.exception(f"Error cancelling task: {task_id}")
        return jsonify({
            'success': False,
            'task_id': task_id,
            'error': str(e)
        }), 500
