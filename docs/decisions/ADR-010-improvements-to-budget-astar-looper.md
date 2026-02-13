# ADR-010: Other Feature Adoption for Budget A\* Loop Solver

## Context

After stabilising the Budget A\* loop solver (Plans 001-003), we conducted a
detailed feature comparison against **Other** (`searchWorker.js`), an
open-source Web Worker–based loop routing engine. The goal was to identify
features that could improve route quality, diversity, or user control without
regressing existing WSM scenic scoring.

### Other Feature Set (relevant subset)

| Feature                                 | Other mechanism                                                                                                                                                                                                                                                                                                         | Present in ScenicPathFinder?                                                                                                                                                                                                   |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Pedestrian path preference**          | Road-type penalty function `ce()`: footway/path/pedestrian/cycleway = 0, residential = 1, tertiary = 3, primary = 6, motorway = 10. Accumulated as `wayTypePenaltyScore × 0.02` in heuristic when `preferPedestrianRoutes` is enabled.                                                                                  | Partially — `quietness.py` already classifies highway tags into NOISY/QUIET/NEUTRAL and bakes this into `norm_quiet` via WSM. However, there is **no independent toggle** to strongly prefer footpaths/cycleways in loop mode. |
| **Footfall / busy-area avoidance**      | OSM Overpass query fetches `landuse=retail\|commercial`, `building=retail\|commercial\|supermarket`, `shop=*`. Proximity-based penalty scored per node (`Re()` function — up to 200 for nodes within 10 m of retail, tapering to 0 at 100 m). Applied as `footfallPenaltyScore × 0.05` when `avoidFootfall` is enabled. | **No** — would require a new data processing pipeline (query retail/commercial polygons at tile-build time, compute per-node proximity scores, add `footfall_penalty` attribute).                                              |
| **Variety level** (route randomisation) | 4 levels (0-3) applying random weight multipliers (±10-30 %) to turn/bearing/wayChange penalties, plus ±2-8 % fScore noise. Produces different routes from the same start/direction on each run.                                                                                                                        | **No** — multi-strategy runs (5 tiers with different bearings) provide strategic diversity but not stochastic variety on repeat queries.                                                                                       |
| **Way-name / way-type continuity**      | Tracks `wayNameChanges` and `wayTypeChanges` during path extension. Penalised in heuristic: turns × 0.02 × target, wayChanges × 0.01 × target. Encourages staying on the same named road.                                                                                                                               | **No** — turn-angle penalties exist but way-name/type continuity is not tracked.                                                                                                                                               |
| **Frontier trimming**                   | Caps open set at 50 K entries, trims to 25 K (keeping lowest fScore) when exceeded.                                                                                                                                                                                                                                     | **No** — `max_states` (500 K) limits total expansions but the heap has no size cap, leading to unbounded memory growth on dense graphs.                                                                                        |
| **Route deduplication**                 | Grid-cell fingerprinting with Jaccard similarity > 85 % threshold (`RouteDeduplicator`).                                                                                                                                                                                                                                | Different approach — `_path_overlap_ratio()` + `select_diverse_candidates()` (edge-based Jaccard).                                                                                                                             |
| **Niceness scoring**                    | Distance-weighted proximity to parks/gardens/nature/water+wetland+wood/rivers/canals. Applied as `-nicenessScore × 0.01` (bonus).                                                                                                                                                                                       | Already covered by WSM edge scoring (`norm_green`, `norm_water`) via isovist-based greenness and water proximity — **more rigorous**.                                                                                          |

### ScenicPathFinder advantages over Other

- WSM multi-criteria edge scoring (greenness, water, quietness, social, slope)
  — pre-computed at tile build time with academic backing.
- Multiplicative directional bias (scales with edge cost; Other's is additive).
- Exploration penalty preventing out-and-back retracing.
- Adaptive 5-tier escalation strategy.
- State-augmented search (node + discretized distance).

## Decision

We adopt **seven** features that complement the existing WSM system. Four
originate from the Other comparison (§1, §2, §6, §7). Three are
new safety/comfort toggles identified during real-world testing (§3, §4, §5).
One feature (footfall avoidance, §8) is deferred as future work. One
investigation (§2a) is documented for a separate implementation effort.

### 1. Variety Level — fScore Noise (ADOPTED)

Add a `variety_level` parameter (0–3) that injects controlled randomness into
the search cost during expansion:

$$\text{wsm\_cost} \;\times=\; 1.0 + \text{uniform}(-\text{noise}, +\text{noise})$$

where $\text{noise} \in \{0, 0.03, 0.06, 0.10\}$ for levels 0-3.

This is the cheapest way to produce different routes from the same
start/direction on repeat queries. Unlike Other's separate weight
multipliers, we apply a single multiplicative noise to the unified WSM cost,
preserving the scenic scoring balance.

### 2. Pedestrian Path Preference Toggle (ADOPTED)

Add a `prefer_pedestrian` boolean that applies a **multiplicative road-type
penalty** during edge expansion:

| Highway tag                                                  | Penalty multiplier |
| ------------------------------------------------------------ | ------------------ |
| footway, path, pedestrian, cycleway, track, bridleway, steps | × 1.0 (no penalty) |
| residential, living_street, service                          | × 1.2              |
| unclassified, tertiary, tertiary_link                        | × 1.5              |
| secondary, secondary_link                                    | × 2.0              |
| primary, primary_link                                        | × 2.5              |
| trunk, trunk_link, motorway, motorway_link                   | × 3.0              |

This is distinct from the quietness WSM weight: quietness is a continuous
normalised factor baked into the cost at tile-build time, while the pedestrian
toggle is a hard multiplier in the search loop that strongly steers toward
footpaths regardless of other scenic qualities.

The highway tag is already available on graph edges (used by
`quietness.py`'s `classify_highway()`).

### 2a. Shared-Use Cycleway & Designated Path Gap (INVESTIGATION)

During real-world testing in **Stoke Park, Bristol**, I discovered that a
shared-use cycle path (the park's main pedestrian route) was absent from
generated routes despite the "Prefer paths & trails" toggle being enabled.

**Root cause — two separate issues:**

#### Issue 1: `highway=cycleway` excluded by pyrosm walking filter

Pyrosm's built-in walking network filter
(`pyrosm.config.osm_filters.walking`) **hard-excludes** all ways where
`highway=cycleway`, regardless of other access tags:

```python
# pyrosm walking filter exclusions (abbreviated)
highway = ["cycleway", "motor", "proposed", "construction",
           "abandoned", "platform", "raceway", "motorway", "motorway_link"]
foot = ["no"]
```

This means a way tagged:

```
highway=cycleway
designation=public_footpath
foot=designated
surface=asphalt
```

…is **silently dropped** before graph construction. The Stoke Park shared-use
path falls into this category — it is a designated public footpath that
happens to be tagged `highway=cycleway` in OSM.

This is a common tagging pattern in the UK for shared-use paths in parks and
along rivers, where the physical surface is a tarmac cycle path but
pedestrians are explicitly permitted (and often the majority of users).

#### Issue 2: `designation` tag not extracted

The `extra_attributes` list in `data_loader.py` does not include
`designation`. OSM's `designation` tag carries important UK-specific legal
access rights:

| `designation` value         | Meaning                                             |
| --------------------------- | --------------------------------------------------- |
| `public_footpath`           | Legal right of way on foot                          |
| `public_bridleway`          | Right of way on foot, horse, and bicycle            |
| `restricted_byway`          | Right of way for all non-motorised traffic          |
| `byway_open_to_all_traffic` | Full right of way (rare)                            |
| `permissive_footpath`       | Landowner-permitted foot access (not a legal right) |

These are **not captured** by the `highway` tag alone. A path tagged
`highway=track` + `designation=public_footpath` is a formal footpath but
currently gets no preferential treatment.

#### Tags already available but unused

Pyrosm's default `highway_columns` include `foot` and `bicycle` as standard
attributes, so these tags **are** present on graph edges:

- `foot=designated` — pedestrians have explicit legal access
- `foot=yes` — pedestrians are permitted
- `bicycle=designated` — cyclists have explicit legal access
- `bicycle=yes` — cyclists are permitted

These are currently unused by any processor or the solver.

#### Proposed fix — two layers

**Layer 1: Data pipeline (include shared cycleways + extract designation)**

1. Add `'designation'` to the `extra_attributes` list in `data_loader.py`
   so the tag is preserved on graph edges.
2. After loading the walking network, perform a **supplementary query** for
   shared-use cycleways and merge them into the graph:
   ```python
   # Fetch cycleways that allow pedestrians
   cycleway_filter = {
       "highway": ["cycleway"],
       "foot": ["yes", "designated", True]
   }
   cycleway_gdf = osm.get_data_by_custom_criteria(custom_filter=cycleway_filter)
   ```
   Alternatively, switch from `network_type="walking"` to a custom filter
   that replicates the walking filter but does **not** exclude
   `highway=cycleway` when `foot ∈ {yes, designated}`. This is the cleaner
   approach but requires maintaining the filter ourselves.

**Layer 2: Solver enhancement (boost designated paths)**

Extend `_road_type_penalty()` to check `foot` and `designation` tags in
addition to `highway`. When `prefer_pedestrian` is enabled:

| Condition                                            | Effect                     |
| ---------------------------------------------------- | -------------------------- |
| `foot=designated` or `designation=public_footpath`   | Apply a **bonus** (× 0.85) |
| `foot=yes` and `highway ∈ {cycleway, track, path}`   | Keep at × 1.0 (no change)  |
| `designation=public_bridleway` or `restricted_byway` | Apply a mild bonus (× 0.9) |

This would mean designated footpaths are **actively preferred** over
unmarked paths, while shared-use cycleways compete on equal footing with
regular footways.

**Alternatively**, this could be exposed as a separate frontend control:

- "Prefer Designated Paths" toggle — boosts `foot=designated` and
  `designation=public_footpath/public_bridleway` regardless of highway type.

This is distinct from "Prefer paths & trails" (which only penalises by
highway tag) and would be particularly useful in rural/park areas where
designated rights of way are the most scenic and well-maintained routes.

**Status: ADOPTED** — custom walking filter implemented in
`walking_filter.py`. Data pipeline changed from `network_type="walking"` to
`network_type="all"` + `apply_walking_filter()`. `designation` added to
`extra_attributes`. Tile caches must be rebuilt. Layer 2 (solver boost for
designated paths) is a follow-up enhancement.

### 3. Prefer Paved Surfaces (ADOPTED)

Add a `prefer_paved` boolean that applies a **multiplicative surface-type
penalty** during edge expansion. The `surface` tag is already available on
graph edges (included in both pyrosm's `highway_columns` and our
`extra_attributes`).

**Surface classification and penalties:**

| Surface tag                                                              | Category | Penalty multiplier |
| ------------------------------------------------------------------------ | -------- | ------------------ |
| paved, asphalt, concrete, concrete:plates, concrete:lanes, paving_stones | Hard     | × 1.0 (no penalty) |
| sett, cobblestone, cobblestone:flattened, metal, wood                    | Firm     | × 1.1              |
| compacted, fine_gravel, gravel                                           | Compact  | × 1.3              |
| dirt, earth, ground, mud, sand, grass, grass_paver, woodchips            | Soft/Wet | × 2.0              |
| _(missing/unknown)_                                                      | Unknown  | × 1.2              |

When enabled, edges with soft/wet surfaces become strongly disfavoured.
This is useful for:

- Wheelchair users or pushchairs requiring firm surfaces.
- Routes after heavy rain when muddy paths are impassable.
- Road cyclists wanting to avoid gravel/dirt sections.

The unknown penalty (× 1.2) is deliberately mild — many paved residential
streets lack a `surface` tag in OSM and should not be heavily penalised.

### 4. Prefer Lit Streets (ADOPTED)

Add a `prefer_lit` boolean that applies a **multiplicative lighting penalty**
during edge expansion. The `lit` tag is already available on graph edges.

**Lighting classification and penalties:**

| `lit` tag value            | Penalty multiplier |
| -------------------------- | ------------------ |
| `yes`, `automatic`, `24/7` | × 0.85 (**bonus**) |
| `limited`, `disused`       | × 1.3              |
| `no`                       | × 1.8              |
| _(missing/unknown)_        | × 1.2              |

Unlike the other toggles which only penalise, this feature **actively
rewards** lit streets with a bonus multiplier (< 1.0), making them cheaper
than the baseline. This is appropriate because:

- Users enabling this toggle are explicitly interested in evening/night
  safety, so lit streets should be strongly attracted toward.
- Many parks and footpaths lack lighting — without a bonus, lit residential
  streets may still lose to scenic but dark footpaths from WSM scoring.

The unknown penalty (× 1.2) gently steers away from roads with no lighting
data. Combined with "Prefer paths & trails", this creates a safety-oriented
profile: footpaths are preferred but only when lit.

### 5. Avoid Unsafe Roads (ADOPTED)

Add an `avoid_unsafe_roads` boolean that applies a **heavy penalty** to
primary, secondary, and tertiary roads **unless** they are explicitly marked
as safe for pedestrians.

**Logic:**

1. Only applies to edges where `highway ∈ {primary, primary_link, secondary,
secondary_link, tertiary, tertiary_link}`.
2. Check for pedestrian safety indicators on the edge:
   - `sidewalk` tag ∈ {`both`, `left`, `right`, `yes`, `separate`} → safe
   - `foot` tag ∈ {`yes`, `designated`} → safe
   - Neither present → **unsafe**, apply × 3.5 penalty
3. When a sidewalk or foot-access is confirmed, the edge keeps its normal
   penalty (from `_road_type_penalty()` if `prefer_pedestrian` is also
   enabled, otherwise × 1.0).

**Penalty table (when `avoid_unsafe_roads` enabled):**

| Condition                                              | Penalty        |
| ------------------------------------------------------ | -------------- |
| `highway=primary` with no sidewalk and no `foot=yes`   | × 3.5          |
| `highway=secondary` with no sidewalk and no `foot=yes` | × 3.5          |
| `highway=tertiary` with no sidewalk and no `foot=yes`  | × 3.5          |
| Any of the above WITH `sidewalk=both` or `foot=yes`    | × 1.0 (normal) |
| `highway=residential`, `footway`, etc.                 | × 1.0 (normal) |

This is distinct from "Prefer paths & trails" (§2):

- §2 penalises ALL non-pedestrian roads proportionally (residential × 1.2,
  primary × 2.5).
- §5 only penalises roads that are **actively dangerous** (no sidewalk +
  high traffic) and leaves safe roads untouched. A primary road with a
  good sidewalk gets no penalty from this toggle.

The two toggles can be combined: "Prefer paths & trails" + "Avoid unsafe
roads" creates a very safety-conscious profile that strongly favours
dedicated footpaths while also avoiding unsidewalked main roads.

The `sidewalk` and `foot` tags are already present on graph edges (both are
in pyrosm's default `highway_columns`). No data pipeline change is needed.

### 6. Frontier Trimming (ADOPTED)

Cap the heapq open set at 50 000 entries. When exceeded, extract all entries,
keep the 25 000 lowest-fScore items, and rebuild the heap.

This prevents unbounded memory growth on dense graphs such as central Bristol
where a 10 km loop can generate hundreds of thousands of frontier states.

### 7. Way-Name Continuity Penalty (ADOPTED)

During edge expansion, compare the `name` tag of the incoming edge with the
outgoing edge. If the names differ (and both are present), add a small
penalty:

$$\text{wsm\_cost} \;+=\; 0.05$$

This discourages zigzag routing between parallel streets with different names,
complementing the existing turn-angle penalty. Road name data is already
present on OSM edges via pyrosm.

### 8. Footfall Avoidance (DEFERRED)

Requires building a new data pipeline:

1. Query retail/commercial/shop polygons from OSM at tile-build time.
2. Compute per-node proximity scores via spatial indexing.
3. Store as `footfall_penalty` node attribute.
4. Apply during search when `avoid_footfall` is enabled.

Deferred due to implementation complexity (new processor module + spatial
indexing + tile cache invalidation). Documented here for future work.

## Implementation

### Backend changes (§1, §2, §6, §7 — DONE)

- **`budget_astar_solver.py`**: Add `variety_level`, `prefer_pedestrian` params
  to `_budget_astar_search()` and `BudgetAStarSolver.find_loops()`. Add
  `_road_type_penalty()` helper. Add frontier trimming. Add way-name
  continuity penalty.
- **`base.py`**: Add `variety_level` and `prefer_pedestrian` to
  `LoopSolverBase.find_loops()` abstract signature.
- **`route_finder.py`**: Forward new params from `find_loop_route()`.
- **`routes.py`**: Accept `variety_level` and `prefer_pedestrian` from
  request JSON.

### Backend changes (§3, §4, §5 — ADOPTED)

- **`budget_astar_solver.py`**: Add `prefer_paved`, `prefer_lit`,
  `avoid_unsafe_roads` params. Add `_surface_penalty()`, `_lit_penalty()`,
  and `_unsafe_road_penalty()` helpers. Apply multiplicatively during edge
  expansion.
- **`base.py`**: Add `prefer_paved`, `prefer_lit`, `avoid_unsafe_roads` to
  `LoopSolverBase.find_loops()` abstract signature.
- **`route_finder.py`**: Forward new params from `find_loop_route()`.
- **`routes.py`**: Accept `prefer_paved`, `prefer_lit`,
  `avoid_unsafe_roads` from request JSON.

### Backend changes (§2a — ADOPTED)

- **`walking_filter.py`** (NEW): Custom walking network filter module with
  clearly-named constants for every exclusion/inclusion rule. Replaces
  pyrosm's `network_type="walking"` filter. Key constant sets:
  `EXCLUDED_HIGHWAY_TAGS`, `CONDITIONAL_HIGHWAY_TAGS`,
  `PEDESTRIAN_FOOT_VALUES`, `PEDESTRIAN_DESIGNATION_VALUES`.
  `apply_walking_filter()` accepts a raw all-highway edges GeoDataFrame
  and returns walking-suitable edges.
- **`data_loader.py`**: Changed `network_type="walking"` → `network_type="all"`.
  Added `apply_walking_filter()` call between `get_network()` and
  `to_graph()`. Added `'designation'` to `extra_attributes` via
  `EXTRA_WALKING_ATTRIBUTES`.
- **`docs/features/custom_walking_filter.md`** (NEW): User-facing
  documentation explaining the filter rules and how to extend them.
- **Tile cache**: Existing caches must be invalidated after this change so
  shared-use cycleways are included in rebuilt graphs.

### Frontend changes

- **`index.html`**: Add "Prefer paths & trails", "Prefer paved surfaces",
  "Prefer lit streets", "Avoid unsafe roads" checkboxes and "Route variety"
  slider (0-3) to the loop distance group.
- **`main.js`**: Include all toggle states and `variety_level` in loop
  request payload.

## Consequences

- **Positive**: More natural pedestrian routes, different results on retry,
  bounded memory usage, smoother route shapes.
- **Positive (§3)**: Paved-surface preference helps wheelchair users,
  pushchairs, and after-rain routing. Uses existing `surface` tag.
- **Positive (§4)**: Lit-streets preference improves evening/night safety.
  Active bonus (× 0.85) attracts routes to lit streets rather than just
  penalising unlit ones.
- **Positive (§5)**: Unsafe-road avoidance targets specifically dangerous
  roads (no sidewalk + high traffic) while leaving safe main roads
  untouched. Combines well with §2 for a safety-first profile.
- **Positive (§2a, if adopted)**: Shared-use cycleways in parks/along rivers
  would appear in routes. Designated footpaths and bridleways would be
  actively preferred, producing more scenic/safe routes in rural and park
  areas.
- **Negative**: Variety noise may occasionally produce slightly sub-optimal
  scenic routes at level 3. Pedestrian preference may conflict with
  quietness weight (both favour footpaths — could over-bias).
- **Negative (§3)**: Many OSM ways lack a `surface` tag, so the unknown
  penalty (× 1.2) may inadvertently disfavour well-paved roads with
  incomplete tagging.
- **Negative (§4)**: `lit` tag coverage is sparse outside urban centres,
  especially in rural areas. The unknown penalty (× 1.2) may push routes
  toward major roads (which tend to have `lit=yes`) at the expense of
  scenic but well-lit side streets that lack the tag.
- **Negative (§5)**: Sidewalk data is inconsistent in OSM — some areas have
  thorough tagging, others have none. A heavily penalised road may actually
  have a wide pavement in reality.
- **Negative (§2a, if adopted)**: Including shared cycleways increases graph
  size slightly (~1-3 % more edges in urban areas). Tile caches must be
  rebuilt. The designation-based bonus may over-reward some paths that are
  legally designated but poorly maintained.
- **Neutral**: Frontier trimming discards some states that might lead to
  valid loops, but the 50 K threshold is generous enough for typical queries.

## Status

**Accepted** — February 2026
