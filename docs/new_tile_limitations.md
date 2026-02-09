# Tile-Based Routing: Bug Investigation & Lessons Learned

**Date:** 9 February 2026  
**Status:** ✅ RESOLVED — Osmium pre-extraction implemented  
**Symptom:** "Find Route" button produces no visible route; map zooms to wrong area

---

## 1. The Symptom

When requesting a route from Stoke Park → Fishponds (both in Bristol, ~2km apart):

- No polyline drawn on the map
- Map zooms to an unexpected location
- API returns HTTP 200 but with a degenerate 1-node "route"

**Key log evidence:**

```
[VERBOSE] Start Node ID: 808115971
[VERBOSE] End Node ID: 808115971      ← SAME NODE for two points 2km apart
[VERBOSE] Route found: 1 nodes        ← Can't draw a polyline with 1 point
```

---

## 2. Root Cause #1: Inconsistent `tile_size_km` Defaults (FIXED)

### Problem

`config.py` defines `TILE_SIZE_KM = 30` and `TILE_OVERLAP_KM = 2`, but **9 function signatures** across the codebase had hardcoded defaults of `15` and `1`. When any code path fell back to defaults instead of passing config values explicitly, it computed different tile IDs, loaded a wrong/stale cached tile, and both coordinates snapped to the same distant node.

### Files Fixed (all defaults → 30 / 2)

| File               | Functions                                                                                |
| ------------------ | ---------------------------------------------------------------------------------------- |
| `tile_utils.py`    | `get_tile_id()`, `get_tiles_for_route()`, `get_tile_bbox()`, `get_tiles_for_bbox()` (×2) |
| `graph_manager.py` | `get_graph_for_route()` → `get_config()` defaults                                        |
| `routes.py`        | async path tile_size_km / tile_overlap_km defaults                                       |
| `task_manager.py`  | `enqueue_tile_build()` defaults                                                          |
| `graph_tasks.py`   | `build_tile_task()` defaults                                                             |

### Status: ✅ FIXED — all 9 locations updated to 30/2

---

## 3. Root Cause #2: PBF Extract Mismatch (PARTIALLY FIXED — OOM blocker)

### Problem

The 30km tile `51.35_-2.43` has its centre at `(51.35, -2.43)`. The route points (Stoke Park ~51.49, Fishponds ~51.48) are in **Bristol** on Geofabrik. But the tile centre falls in **Somerset** on Geofabrik.

**Bristol and Somerset are separate Geofabrik extracts** (separate administrative regions). Somerset's PBF does NOT contain Bristol's walking network. So when the worker built the tile graph from `somerset.osm.pbf`, it had no data for the route area. Both route points snapped to the same distant boundary node.

### How PBF Selection Worked (Before Fix)

`ensure_data_for_bbox(bbox)` reduced the bbox to its **centre point** and called `_find_pbf_url_for_location(lat, lon)`, which found the smallest Geofabrik polygon containing that single point:

```
Tile bbox: (51.20, -2.58) → (51.50, -2.28)
Centre:    (51.35, -2.43)
           ↓
Bristol polygon:  area=0.016, contains centre? ❌ (Bristol boundary ~51.40 at south)
Somerset polygon: area=0.636, contains centre? ✅ ← SELECTED (smallest match)
```

Meanwhile, the **API** derived `region_name` from the **route** bbox (centre ~51.49 → Bristol), creating a cache key mismatch:

- API cache key: `bristol_edge_sampling_local_tile_51.35_-2.43`
- Worker saved: `bristol_edge_sampling_local_tile_51.35_-2.43` (region_name passed from API)
- But data inside pickle was from `somerset.osm.pbf` → missing Bristol walking network

### Fix Attempt #1: bbox-cover lookup (Applied, but caused OOM)

Added `_find_pbf_url_for_bbox()` — finds the smallest Geofabrik extract whose polygon **fully contains the entire tile bbox** (all 4 corners, not just centre). Also updated `find_region_for_bbox()` in both `graph_builder.py` and `graph_manager.py` to derive `region_name` from the tile bbox.

**Result:** Correctly identified **England** as the smallest extract covering the full 30km tile. Downloaded `england-latest.osm.pbf` (1.51 GB) successfully. But parsing it in pyrosm (even with bbox clipping) **exceeded Docker container memory** → worker SIGKILL'd (OOM).

```
england.osm.pbf: 100%|##########| 1.51G/1.51G [01:38<00:00, 16.5MiB/s]
[OSMDataLoader] Parsing PBF data: /app/app/data/england.osm.pbf
[OSMDataLoader] Clipping to bbox: (51.15, -2.63, 51.55, -2.23)
... worker killed by signal 9 (SIGKILL) — out of memory
```

**Key insight:** pyrosm loads the entire PBF into memory before applying the bbox clip. A 1.5GB PBF expands to several GB in RAM during parsing.

### Current State of Code Changes

The following edits are **still in place** from this attempt:

1. **`data_loader.py`** — `_load_geofabrik_index()` extracted as helper; `_find_pbf_url_for_bbox()` added; `ensure_data_for_bbox()` calls `_find_pbf_url_for_bbox()` instead of centre-point
2. **`graph_builder.py`** — `find_region_for_bbox()` calls `_find_pbf_url_for_bbox()`
3. **`graph_manager.py`** — `_find_region_for_bbox()` calls `_find_pbf_url_for_bbox()`; `get_graph_for_route()` derives region from tile bbox
4. **`routes.py`** — async path derives region from tile bbox (already applied earlier, working correctly)

---

## 4. Possible Solutions (Not Yet Attempted)

### Option A: Merge Multiple Small PBFs

Download both `bristol.osm.pbf` (12MB) and `somerset.osm.pbf` (44MB), parse them separately, and merge the resulting NetworkX graphs. Memory-friendly since each PBF is small.

**Pros:** Uses existing small extracts, no large downloads  
**Cons:** Requires graph merge logic, potential edge duplication at boundaries, adds complexity

### Option B: Memory-Capped PBF Selection

Add a **max file size threshold** (e.g. 200MB) to `_find_pbf_url_for_bbox()`. If the smallest bbox-covering extract exceeds this, fall back to the centre-point extract but log a warning. Accept that southern parts of the tile may have gaps.

**Pros:** Simple, prevents OOM  
**Cons:** Tile may have incomplete data near boundaries; doesn't fix the original problem for routes at the boundary

### Option C: Increase Docker Memory Limit

Increase the worker container's memory limit in `docker-compose.yml` (e.g. to 4–6GB). England PBF parsing might work with enough RAM.

**Pros:** No code changes needed  
**Cons:** Requires more system resources; parsing England PBF would be slow (~minutes)

Dont do this idea...

### Option D: Use Route Points for PBF, Tile for Cache Key

The fundamental insight: **the cache key should be derived from the tile bbox** (for consistency between API and worker), but **the PBF should be chosen based on the route points** (since the graph only needs to cover the area where the route actually goes).

Implementation: pass route start/end coordinates through to the worker alongside `tile_id`, so the worker can call `ensure_data_for_bbox(route_bbox)` for PBF selection while still building the tile-sized graph. The graph may have gaps far from the route, but nearest_nodes will find correct nodes for the actual route points.

**Pros:** Uses small PBFs, no OOM risk, minimal code change  
**Cons:** Tiles built from different routes could use different PBFs → inconsistent data within the same tile ID. Would need to include PBF identity in the cache key, or accept the inconsistency.

### Option E: Pre-Download Region-Specific PBFs (Recommended for Demo)

For the dissertation demo, simply pre-download `bristol.osm.pbf` and ensure the system uses it for Bristol-area routes. Hardcode or configure a preference for Bristol when route points fall within the Bristol area.

**Pros:** Simple, reliable for demo  
**Cons:** Not generalised; only works for pre-configured regions

### Option F: Osmium Tool — Extract a Custom Region

Use the `osmium` CLI tool to extract a custom bbox from the England PBF _before_ loading into pyrosm. This produces a small PBF that pyrosm can handle without OOM.

```bash
osmium extract -b -2.63,51.15,-2.23,51.55 england.osm.pbf -o tile_51.35_-2.43.osm.pbf
```

**Pros:** Small output file, memory-efficient, precise  
**Cons:** Requires `osmium-tool` in Docker image; adds a pre-processing step

Wait, we mightved cooked here

---

## 5. Key Architectural Lessons

1. **Tile centre ≠ route centre.** A 30km tile can easily straddle multiple Geofabrik extracts. Any logic that reduces a bbox to its centre point for PBF selection is fragile.

2. **Geofabrik boundaries are administrative, not geographic.** Bristol (city) and Somerset (county) are adjacent but separate. There is no "South West England" intermediate extract — the next level up is all of England.

3. **pyrosm loads the full PBF into memory before clipping.** Even with `bounding_box=` parameter, a 1.5GB PBF will expand to multi-GB RAM. This rules out using large national extracts in memory-constrained containers.

4. **Cache key consistency requires a single source of truth.** The API and worker must derive `region_name` from the same input (tile bbox, not route bbox) or cache lookups will miss/mismatch.

5. **Default parameter values must match config.** Having `tile_size_km=15` as a function default when config says `30` creates silent bugs that only manifest at runtime with wrong tile IDs.

---

## 6. Files Modified During Investigation

| File                                 | Change                                                                                              | Status                                   |
| ------------------------------------ | --------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| `app/services/core/tile_utils.py`    | All defaults → 30/2                                                                                 | ✅ Done                                  |
| `app/services/core/graph_manager.py` | Defaults → 30/2; region from tile bbox; bbox-cover lookup                                           | ✅ Done                                  |
| `app/services/core/graph_builder.py` | `find_region_for_bbox` → bbox-cover lookup                                                          | ✅ Done                                  |
| `app/services/core/data_loader.py`   | Added `_find_pbf_url_for_bbox()`, `_load_geofabrik_index()`; `ensure_data_for_bbox` uses bbox-cover | ✅ Done (causes OOM with large extracts) |
| `app/routes.py`                      | Defaults → 30/2; region from tile bbox                                                              | ✅ Done                                  |
| `app/services/core/task_manager.py`  | Defaults → 30/2                                                                                     | ✅ Done                                  |
| `app/tasks/graph_tasks.py`           | Defaults → 30/2                                                                                     | ✅ Done                                  |

---

## 7. To Resume

1. Pick an approach from Section 4 (Option D or F recommended)
2. Revert or modify `_find_pbf_url_for_bbox` to avoid selecting England-sized extracts
3. Clear all cache: `Remove-Item app\data\cache\*.pickle` + delete `manifest.json`
4. Optionally delete `england.osm.pbf` from `app/data/` to reclaim 1.5GB
5. Restart Docker and test Stoke Park → Fishponds route

---

## 8. Resolution and Performance Analysis (Implemented Fix)

### Solution Overview: Hybrid Osmium + Pyrosm Pipeline

We implemented **Option F** (Osmium Pre-Extraction). This approach leverages the strengths of two different tools:
1. **Osmium (`osmium-tool`)**: A high-performance C++ CLI tool used to extract a small bounding box from a massive PBF file. It streams data and has a very low memory footprint.
2. **Pyrosm**: The existing Python library used to parse PBFs into NetworkX graphs. It is memory-hungry but convenient for graph building.

By using Osmium to create a tiny "clip" of the PBF *before* Pyrosm tries to load it, we bypass the memory bottleneck completely.

### Implementation Details

#### 1. Infrastructure Changes
- **Dockerfile**: Added `osmium-tool` (installed via `apt-get install -y osmium-tool`).
- **Python Dependencies**: No new Python packages required (wraps the CLI tool via `subprocess`).

#### 2. Workflow Logic (`data_loader.py`)
1. **Size Check**: Before loading a PBF, checking if its size exceeds `MAX_PYROSM_PBF_SIZE` (set to 100MB).
2. **Conditional Extraction**:
   - If **Small PBF** (<100MB): Load directly with Pyrosm (fastest).
   - If **Large PBF** (>100MB, e.g., `england.osm.pbf` at 1.5GB):
     - Generate a filename hash for the clip (e.g., `extracted_51.15_-2.63_51.55_-2.23.osm.pbf`).
     - Check if this clip already exists in cache.
     - If not, execute `osmium extract -b <bbox> ...` to create it.
3. **State Propagation**: A new instance variable `_active_pbf_path` tracks the path of the *actual* file being used (either the original or the clip).
4. **Unified Feature Extraction**: All downstream feature extractors (`extract_green_areas`, `extract_buildings`, `extract_water`, `extract_pois`) were updated to use `_active_pbf_path`. This ensures they also benefit from the small PBF and don't accidentally reload the 1.5GB file.

### Performance & Efficiency

#### Memory Usage (RAM)
- **Before (Pyrosm direct)**: >6GB. `pyrosm` attempts to load the index and checking nodes for the 1.5GB file, causing immediate OOM (SIGKILL) in the Docker container.
- **After (Osmium hybrid)**: Estimated Peak < 1GB.
  - `osmium` uses minimal RAM (streaming parser).
  - `pyrosm` only loads the ~40MB clipped file.
  - **Improvement**: Infinite (enables functionality that was previously impossible).

#### Latency Impact
The trade-off for stability is the time taken to run the extraction command.

| Step | Time Taken (approx) | Notes |
|------|---------------------|-------|
| **Osmium Extraction** | **~37 seconds** | One-time cost per tile (cached for future runs). Extracting 40MB from 1.5GB. |
| **Graph Loading** | ~73 seconds | Parsing the 40MB file into NetworkX (511k nodes). |
| **Feature Extraction** | ~250 seconds | Dominating factor is "Greenness Edge Sampling" (calculating visibility for 1M edges). |
| **Total Tile Build** | **~363 seconds** | (~6 minutes) |

**Analysis**:
- The **37s overhead** from Osmium is roughly **10%** of the total build time.
- This is a highly acceptable trade-off for eliminating OOM crashes.
- Since the extracted PBF is cached, subsequent graph rebuilds (e.g., if changing scoring logic) will skip the extraction step, reducing the overhead to 0s.

#### Storage
- **Input**: 1.51 GB (`england.osm.pbf`)
- **Output Clip**: ~45 MB (`extracted_...osm.pbf`)
- **Overhead**: Negligible disk usage increase compared to the reliability gains.

### Final Verification Results
- **Route**: Stoke Park → Fishponds
- **Distance**: 2.63 km
- **Time**: 31 min
- **Graph Nodes**: 511,594
- **Graph Edges**: 1,096,600
- **Status**: **Success** ✅

---

## 9. Final Resolution: Cache Tuning and Tile Sizing (9 Feb 2026)

### The Issue: Multi-Tile Route OOM
After deploying the Osmium fix, single-tile routes worked perfectly. However, a route from **Stoke Park → Southmead** caused a massive **14GB OOM crash**, freezing the Docker daemon.

**Analysis**:
1. **Tile Boundary**: Southmead (-2.59) is just outside the Stoke Park tile boundary (-2.58).
2. **Concurrent High Memory**: 
   - **API Container**: Held the *previous* tile (Stoke Park) in memory (~4GB+).
   - **Worker Container**: Started building the *new* tile (Southmead).
   - **Combined Usage**: >14GB, exceeding system limits.
3. **Tile Size**: We had tentatively increased `TILE_SIZE_KM` to 30, which made individual tiles huge (6-8GB build spikes).

### The Fix

1. **Revert to 15km Tiles**:
   - `config.py`: `TILE_SIZE_KM = 15`.
   - **Strict Enforcement**: Refactored `tile_utils.py` to be the single source of truth for this constant, preventing the 9-location inconsistency from recurring.
   - **Result**: Build memory spikes reduced from ~8GB to ~2GB per tile.

2. **Aggressive API Caching Limits**:
   - Reduced `_max_cached_tiles` from 12 to **4**.
   - With 15km tiles, 4 cached tiles consume ~1.5GB RAM (safe).

3. **Worker Process Recycling**:
   - Configured `celery_app.py` with `worker_max_tasks_per_child=1`.
   - **Why?**: Python/Celery can fragmemt memory or hold references to large graphs. Restarting the process after *every* tile build guarantees 100% memory reclamation.

### Observed Behavior
- **Memory**: Stable. Worker spikes to ~2-3GB during build, then drops to near zero. API holds steady at ~1-2GB.
- **Tile Dimensions**: A "15km" tile actually corresponds to a ~19km x 19km loaded area due to the 2km buffer on all sides (`TILE_OVERLAP_KM`).
  - Core Grid: 15km step.
  - Loaded Area: 15 + 2 (left) + 2 (right) = 19km width.
  - This explains why user measurements showed ~18.7km tiles on the map.


---

## 10. Performance Analysis (15km Tiles)

**Run Date:** 9 February 2026 (Post-Fix)
**Configuration:** 
- Tile Size: 15km (19km loaded area)
- Parallel Workers: 4 (Configured), 1 (Active for single route)
- Mode: Async (Celery)

**Timing Breakdown (Stoke Park → Southmead):**
- **Osmium Extraction**: ~36s (Extracting 29km bbox from 1.5GB PBF)
- **Graph Loading (Pyrosm)**: ~47s (Loading smaller cut-out)
- **Feature Extraction**: ~201s (3m 21s)
  - Dominant step: Greenness Edge Sampling
- **Total Build Time**: ~284s (4m 44s)

**Comparison:**
- **Vs 30km Tiles**: 
  - 30km build crashed (OOM) or took >6 mins. 
  - 15km build is stable and ~22% faster.
- **Vs Raw Pyrosm**: Infinite improvement (Raw Pyrosm crashes on load).



