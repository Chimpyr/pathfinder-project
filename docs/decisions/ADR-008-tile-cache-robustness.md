# ADR-008: Tile Cache Robustness and Performance

**Status:** Accepted  
**Date:** 2026-02-08  
**Supplements:** [ADR-007](./ADR-007-tile-based-caching.md) (Tile-Based Caching)

---

## Context

During implementation and testing of ADR-007's tile-based caching system, several critical issues emerged that prevented cache hits from working correctly in a Dockerised multi-worker environment. This ADR documents the discovered issues and their solutions.

### Symptoms Observed

1. **Cache rebuilt every request** despite tiles existing on disk
2. **Stale task polling** after cache should have been hit
3. **Half of tiles missing** from manifest after parallel builds
4. **~45 second delays** on every request (disk reload + merge)

---

## Issue 1: PBF Modification Time Precision

### Problem

```
[CacheManager] PBF modified since cache creation for bristol_tile_51.62_-2.57 
(cached: 1767811769.123456, current: 1767811769.123457)
```

The cache validation compared PBF file modification times using floating-point equality. Docker volume mounts can cause microsecond-level timing differences between containers viewing the same file.

### Root Cause

```python
# BROKEN: Float comparison with microsecond precision
if entry.get("pbf_mtime") != os.path.getmtime(pbf_path):
    return False  # Always fails due to float precision!
```

### Solution

Use integer timestamps (1-second precision) for both storage and comparison:

```python
# FIXED: Integer comparison at 1-second granularity
pbf_mtime = int(os.path.getmtime(pbf_path))
cached_mtime = entry.get("pbf_mtime")
if cached_mtime is not None and int(cached_mtime) != pbf_mtime:
    return False
```

**File:** `cache_manager.py` lines 165-175, 257

---

## Issue 2: PBF Path Mismatch Across Tiles

### Problem

```
[CacheManager] PBF modified since cache creation for tile_51.62_-2.57
(cached: 1767811769, current: 1767811023)
```

The cached mtime was *higher* than current mtime—impossible if checking the same file.

### Root Cause

The route bbox determines which single PBF file to check (e.g., `bristol.osm.pbf`), but individual tiles may have been built using different PBF files (e.g., `gloucestershire.osm.pbf`) because their bboxes fall in different regions.

```python
# BROKEN: Route picks one PBF, but tiles may use different PBFs
loader.ensure_data_for_bbox(route_bbox)  # Picks bristol.osm.pbf
if cache_mgr.is_cache_valid(..., loader.file_path, tile_id=tid):
    # Compares bristol.osm.pbf mtime against tile built from gloucestershire.osm.pbf!
```

### Solution

Skip the pbf_path check when validating tiles. Each tile's `pbf_mtime` was recorded at build time—the tile is self-validating.

```python
# FIXED: Tiles self-validate, don't cross-check with route's PBF
if cache_mgr.is_cache_valid(..., pbf_path=None, tile_id=tile_id):
    # Only checks manifest entry exists and version matches
```

**Files:** `routes.py` line 294, `graph_manager.py` line 330

---

## Issue 3: Manifest Race Condition

### Problem

After parallel tile builds, only some tiles appeared in `manifest.json`:

```json
{
  "entries": {
    "tile_51.62_-2.43": {...},   // Worker A saved this
    "tile_51.49_-2.57": {...}    // Worker B overwrote, lost tiles 1 & 4!
  }
}
```

### Root Cause

Multiple Celery workers saving to the same manifest file concurrently:

```
Worker A: Read manifest → Add tile 1 → Write manifest
                                    ↑
Worker B: Read manifest (same version!) → Add tile 2 → Write manifest
                                                      ↳ Overwrites tile 1!
```

### Solution

Use file locking with reload-merge-save pattern:

```python
def _save_manifest(self):
    import filelock
    lock = filelock.FileLock(self.cache_dir / "manifest.lock")
    
    with lock:
        # Reload from disk (catches other workers' changes)
        disk_manifest = self._load_manifest()
        
        # Merge our entries into disk manifest
        for key, entry in self._manifest.get("entries", {}).items():
            disk_manifest.setdefault("entries", {})[key] = entry
        
        # Write merged manifest
        with open(self.manifest_path, 'w') as f:
            json.dump(disk_manifest, f)
```

**File:** `cache_manager.py` lines 61-91  
**Dependency:** Added `filelock>=3.0.0` to `requirements.txt`

---

## Issue 4: Performance (Repeated Disk Loads)

### Problem

Every request loaded tiles from disk (~5s per 250MB pickle) and re-merged them (~20s for 4 tiles), even when requesting the same route repeatedly.

```
[TileCache] HIT: 51.49_-2.43  → Load 250MB from disk (5s)
[TileCache] HIT: 51.49_-2.57  → Load 250MB from disk (5s)
[GraphManager] Merging 4 tiles...  → Merge 830K edges (20s)
```

### Root Cause

No in-memory caching layer—every cache "hit" still required full disk I/O and CPU-intensive merging.

### Solution

Implement 3-tier hierarchical caching:

```
┌─────────────────────────────────────────────────────────────┐
│ TIER 1: Merged Graph Cache (instant)                        │
│ Key: (frozenset(tile_ids), region, modes)                   │
│ Returns pre-merged graph immediately                         │
├─────────────────────────────────────────────────────────────┤
│ TIER 2: Tile Memory Cache (fast)                            │
│ Key: "region_mode_tile_id"                                  │
│ LRU eviction, max 12 tiles (~3GB RAM)                       │
├─────────────────────────────────────────────────────────────┤
│ TIER 3: Disk Cache (slow but persistent)                    │
│ Pickle files survive container restarts                     │
└─────────────────────────────────────────────────────────────┘
```

**Performance comparison:**

| Scenario | Before | After |
|----------|--------|-------|
| Same route, 2nd request | ~45s | **<1s** |
| Different route, same tiles | ~45s | **~20s** (merge only) |
| Same tiles, after container restart | ~45s | **~25s** (disk load + cache populate) |

**File:** `graph_manager.py` lines 77-85, 279-290, 325-370

---

## Configuration Added

```python
# graph_manager.py (class variables)
_tile_cache: Dict[str, Tuple[nx.MultiDiGraph, float]] = {}
_max_cached_tiles: int = 12  # ~3GB memory limit

_merged_cache: Dict[frozenset, Tuple[nx.MultiDiGraph, float]] = {}
# Max 5 merged graph combinations
```

---

## Files Modified

| File | Changes |
|------|---------|
| `cache_manager.py` | Integer mtime precision, filelock manifest saving |
| `graph_manager.py` | 3-tier cache hierarchy, LRU eviction |
| `routes.py` | Skip pbf_path for tile validation |
| `requirements.txt` | Added `filelock>=3.0.0` |
| `Dockerfile` | Fixed stray backtick syntax error |

---

## Lessons Learned

1. **Docker volumes introduce timing quirks** — Avoid sub-second precision comparisons
2. **Multi-region routing complicates validation** — Tiles are self-validating units
3. **Concurrent writes need coordination** — File locks are essential for shared state
4. **Disk is not a cache** — Memory caching is crucial for interactive performance

---

## References

- [ADR-007: Tile-Based Caching](./ADR-007-tile-based-caching.md)
- [Python filelock documentation](https://py-filelock.readthedocs.io/)
