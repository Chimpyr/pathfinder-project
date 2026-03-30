# ADR-005: Async Task Lock Management and Cache Reliability

**Status:** Accepted  
**Date:** 2026-01-30

---

## Context

During testing of the async graph building pipeline, several critical bugs were discovered that caused unreliable cache hits and infinite request loops.

### Observed Symptoms

| Symptom                                  | Impact                                                  |
| ---------------------------------------- | ------------------------------------------------------- |
| Infinite retry loop after cache deletion | Browser continuously sent requests, server unresponsive |
| "Unknown error" on successful route      | Admin test UI showed failure despite route working      |
| Duplicate graph builds                   | Cache savings lost; 80+ second builds repeated          |

---

## Problem Analysis

### Bug 1: Stale Redis Task Locks

**Flow:**

1. Task enqueued, Redis lock set: `building:bristol:EDGE_SAMPLING:LOCAL → task_id`
2. Task completes successfully (graph saved to disk)
3. **Lock NOT cleared** (original implementation had no `finally` block)
4. Cache deleted via admin panel
5. New route request → TaskManager finds lock → Returns old task ID
6. Frontend polls old task → Sees `SUCCESS` → Retries route
7. Repeat forever (infinite loop)

**Root cause:** `graph_tasks.py` did not release the Redis lock upon task completion.

### Bug 2: Cache Key Mismatch in GraphManager

**Flow:**

1. Worker builds graph, saves with `clip_bbox` hash: `bbox_00e2b1b4`
2. Task completes, frontend retries route
3. `routes.py` calls `GraphManager.get_graph(bbox)`
4. `GraphManager.is_cache_valid()` called **without bbox parameter**
5. Cache key generated without bbox hash → Different key → Cache MISS
6. Synchronous build triggered in API container

**Root cause:** `GraphManager.get_graph()` did not compute or pass `clip_bbox` to cache operations.

### Bug 3: Missing Success Field in API Response

**Flow:**

1. Route calculated successfully
2. API returns `{route_coords: [...], stats: {...}}`
3. Admin JavaScript checks `data.success` → `undefined`
4. Throws "Unknown error"

**Root cause:** `routes.py` response lacked `success: true` field.

---

## Decisions

### Decision 1: Always Release Locks in Finally Block

```python
# graph_tasks.py
def build_graph_task(self, region_name, bbox, ...):
    try:
        result = build_graph(...)
        return {'status': 'complete', ...}
    except Exception as e:
        return {'status': 'failed', 'error': str(e)}
    finally:
        # Critical: Always clear lock regardless of success/failure
        tm = get_task_manager()
        tm.clear_lock(region_name, greenness_mode, elevation_mode)
```

**Rationale:** Locks must be ephemeral. A completed task (success or failure) should never block future requests.

### Decision 2: Validate Lock State Before Reusing Task ID

```python
# task_manager.py
def get_existing_task(self, region_name, ...):
    existing_task_id = self.redis_client.get(lock_key)
    if existing_task_id:
        result = AsyncResult(task_id, app=celery)
        if result.state in ['SUCCESS', 'FAILURE', 'REVOKED']:
            # Stale lock - task finished but lock remained
            self.redis_client.delete(lock_key)
            return None  # Allow new task
        return task_id  # Task still running
    return None
```

**Rationale:** Defense-in-depth. Even if `finally` block fails, TaskManager self-heals by checking actual task state.

### Decision 3: Compute clip_bbox in GraphManager

```python
# graph_manager.py
def get_graph(cls, bbox):
    # Calculate clip_bbox (must match GraphBuilder's calculation)
    clip_bbox = None
    if bbox is not None:
        buffer_km = 5
        buffer_deg = buffer_km / 111.0
        clip_bbox = (
            bbox[0] - buffer_deg,
            bbox[1] - buffer_deg,
            bbox[2] + buffer_deg,
            bbox[3] + buffer_deg
        )

    # Now cache operations use correct key
    if cache_mgr.is_cache_valid(..., bbox=clip_bbox):
        return cache_mgr.load_graph(..., bbox=clip_bbox)
```

**Rationale:** All code paths that touch the cache must use identical key generation. The `clip_bbox` computation is defined once (5km buffer) and replicated where needed.

### Decision 4: Include Success Field in API Response

```python
# routes.py
response_data = {
    'success': True,  # Required by admin.html JavaScript
    'route_coords': route_coords,
    'stats': {...}
}
```

**Rationale:** Explicit success flag enables reliable client-side success detection.

---

## Consequences

### Positive

- **No infinite loops**: Stale locks are cleared proactively
- **Reliable cache hits**: All code paths use matching cache keys
- **Self-healing**: TaskManager detects and clears orphaned locks
- **Clear API contract**: `success: true` is explicit

### Negative

- **Slight overhead**: TaskManager makes Celery API call to check task state
- **Code duplication**: `clip_bbox` calculation in 3 files (could be extracted)

---

## Files Modified

| File                           | Changes                                                |
| ------------------------------ | ------------------------------------------------------ |
| `graph_tasks.py`               | Added `finally` block to clear lock on completion      |
| `task_manager.py`              | Added task state validation before returning cached ID |
| `graph_manager.py`             | Added `clip_bbox` calculation, passed to cache ops     |
| `routes.py`                    | Added `success: True` to response                      |
| `admin.html`                   | Fixed JavaScript to read `data.stats.distance_km`      |
| `docs/architecture/caching.md` | Added implementation notes section                     |

---

## Testing Validation

| Test                                      | Before          | After                  |
| ----------------------------------------- | --------------- | ---------------------- |
| Clear cache → Run test → Wait → Run again | Infinite loop   | ✅ Cache hit, 4s load  |
| Task completes → Immediate retry          | 80s rebuild     | ✅ Cache hit, 4s load  |
| Admin test panel success display          | "Unknown error" | ✅ "4.82km, 269 nodes" |

---

## References

- [ADR-004: BBox Clipping](ADR-004-bbox-clipping.md)
- [Caching Architecture](../architecture/caching.md)
- [Celery Redis Architecture](../architecture/celery_redis_architecture.md)
