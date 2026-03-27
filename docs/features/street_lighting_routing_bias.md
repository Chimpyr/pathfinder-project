## Routing Integration

> This section covers the **routing toggles** ("Prefer lit streets" /
> "Heavily avoid unlit streets"). These are entirely separate from the
> visual tile overlay described above. The overlay reads from PostGIS;
> the routing toggles read the `lit` tag directly from graph edges loaded
> by `OSMDataLoader`.

---

### Data Source

Lighting data for routing comes from the **in-memory graph**, not PostGIS.
`OSMDataLoader` calls `pyrosm` with:

```python
extra_attributes=['lit']
```

This attaches the raw OSM `lit` string directly to every edge in the
NetworkX graph. No normalisation is performed the routing code reads
the raw value as a lookup key.

Common OSM tag values and how they map to routing behaviour:

| OSM `lit` value            | Treated as              |
| -------------------------- | ----------------------- |
| `yes`, `automatic`, `24/7` | Lit (bonus applied)     |
| `limited`, `disused`       | Partially lit (penalty) |
| `no`                       | Unlit (penalty)         |
| absent / anything else     | Unknown (default used)  |

---

### Penalty Mechanism

Both toggles work as a **multiplicative post-WSM-cost modifier** applied in
`WSMNetworkXAStar.distance_between()`. The base WSM cost for an edge is
computed first, then scaled:

```
edge_cost = wsm_cost(distance, green, water, social, quiet, slope)
           x lit_multiplier(edge.lit)
```

This means:

- The lit penalty is **orthogonal** to the WSM weights. You can have high
  greenness weight AND prefer lit streets; the two penalties stack.
- The lit feature is **not a new WSM dimension** it does not interact
  with the OR-semantics cost formula or the weight sliders.
- When neither toggle is active, no multiplication occurs and routing is
  identical to the base WSM behaviour.

#### Prefer Lit Streets

| `lit` tag value            | Multiplier                           |
| -------------------------- | ------------------------------------ |
| `yes`, `automatic`, `24/7` | x 0.85 (bonus cheaper than baseline) |
| `limited`, `disused`       | x 1.3                                |
| `no`                       | x 1.8                                |
| Unknown / missing          | x 1.2                                |

A mild preference. The 15 % bonus for lit streets allows them to compete
with greener but darker alternatives without completely rerouting the path.
An unlit street costs 1.8 x its base WSM cost significant but not
prohibitive.

#### Heavily Avoid Unlit Streets

| `lit` tag value            | Multiplier              |
| -------------------------- | ----------------------- |
| `yes`, `automatic`, `24/7` | x 0.70 (strong bonus)   |
| `limited`, `disused`       | x 2.5                   |
| `no`                       | x 5.0 (near-impassable) |
| Unknown / missing          | x 3.0 (assumed dark)    |

A strong enforcement mode. An unlit edge at x 5.0 effectively appears five
times its physical length to the router it will be avoided unless no
alternative path to the goal exists. Streets with no lighting data are
treated conservatively as **likely unlit (x 3.0)**, because many paths and
rural lanes genuinely have no street lighting.

**Mutual exclusivity:** The two toggles are mutually exclusive in both UI
and backend. If `heavily_avoid_unlit=True` is sent to the API,
`prefer_lit` is still passed but `_compute_lit_multiplier` always uses the
heavy table when `heavily_avoid=True`. The UI enforces this by unchecking
the other toggle on change.

---

### WSM A\* (Point-to-Point)

The multiplier is applied inside `WSMNetworkXAStar.distance_between()`,
which is called for every edge relaxation. The heuristic
(`heuristic_cost_estimate`) is **not** adjusted it uses distance only
and remains the same whether lighting toggles are active or not.

**Call chain for standard routes:**

```
POST /api/route
  -> routes.py  (parses prefer_lit, heavily_avoid_unlit from JSON body)
  -> find_route() in route_finder.py
  -> WSMNetworkXAStar(graph, weights, prefer_lit=..., heavily_avoid_unlit=...)
  -> distance_between() applies lit multiplier per edge
```

For multi-route (distinct-paths) mode, both parameters are forwarded
identically through `find_distinct_paths()` to each of the three A\* calls.

**Heuristic admissibility note:** The base WSM heuristic assumes zero
scenic cost (optimistic lower bound). When `prefer_lit` is active, lit
edges receive a x 0.85 factor, meaning actual costs for all-lit paths may
be lower than the heuristic assumes. Technically, `h(n) <= actual_remaining_cost`
is no longer strictly guaranteed for paths through entirely lit streets.
In practice this effect is at most 15 % and A\* still finds near-optimal
results. The `heavily_avoid_unlit` bonus (x 0.70) increases this
theoretical gap slightly but likewise has minimal practical impact.

---

### Loop Mode

**Call chain for loop routes:**

```
POST /api/loop
  -> routes.py  (parses heavily_avoid_unlit)
  -> find_loop_route() in route_finder.py
  -> GeometricLoopSolver.find_loops(prefer_lit=..., heavily_avoid_unlit=...)
  -> _try_polygon() -> _route_leg() -> WSMNetworkXAStar(prefer_lit=..., heavily_avoid_unlit=...)
  -> _try_out_and_back() -> _route_leg() (same)
```

> Note: `prefer_lit` is threaded through the geometric solver chain but
> only `heavily_avoid_unlit` is currently parsed from the `/api/loop`
> request body. If `heavily_avoid_unlit` is True it takes precedence over
> `prefer_lit` inside `_compute_lit_multiplier`.

#### Bearing Selection No Direct Effect

The lighting toggles have **no direct effect on bearing selection**.
Bearings are chosen before any routing occurs, based on:

- `directional_bias` (user compass selection)
- Equidistant rotation (default)
- `use_smart_bearing` scenic sector analysis (greenness/water features only)

None of these mechanisms read lighting data. The initial skeleton
geometry (triangle or polygon) is placed independently of where lit
streets are.

#### Indirect Effect via Tortuosity (tau) Feedback

The lighting toggles **do** indirectly influence the geometric skeleton
through the tortuosity feedback loop.

The feedback loop works as:

```
ratio         = actual_dist / target_distance
clamped_ratio = clamp(ratio, 0.85, 1.15)
tau_new       = tau_current * clamped_ratio
```

When strong lit penalties are active:

1. The router detours onto lit streets rather than taking dark shortcuts,
   making each routed leg **longer** than its air-line distance.
2. `actual_dist` exceeds `target_distance`, so `ratio > 1.0` and tau
   grows (up to +15 % per iteration due to the clamp).
3. On the next retry the target skeleton shrinks (shorter arm lengths),
   producing a more compact loop that fits within the distance budget
   even after the lit-forced detours.

In practical terms, "Heavily avoid unlit streets" in a dense urban grid
tends to produce a **tighter, less wide loop** compared to the same
request with no lighting preference, because the solver uses lit corridor
streets rather than cutting across dark parks or footpaths.

#### Bridge-Leg Detour Check

Each leg is subject to:

```python
if routed_distance > BRIDGE_LEG_DETOUR_FACTOR * air_distance:
    # abort this polygon attempt
```

`BRIDGE_LEG_DETOUR_FACTOR = 3.0`. When lit preferences are active, routed
legs can legitimately be two or three times the air distance (e.g. routing
around a dark park rather than through it), so the 3.0 threshold is
intentionally relaxed. If a leg exceeds this threshold the polygon attempt
is aborted and the solver tries the next bearing or falls back to
out-and-back.

#### Waypoint Snapping Not Lighting-Aware

`_smart_snap()` scores candidate graph nodes by distance, connectivity,
degree, scenic quality (`norm_green`), flow awareness, and alignment
penalties. It does **not** score by lighting. The chosen waypoint (W1, W2,
etc.) may be on or adjacent to an unlit street; lit avoidance only
influences which path A\* takes **between** snapped waypoints.

---

### Logging

When either toggle is active, both `WSMNetworkXAStar` and
`GeometricLoopSolver` log the active mode:

```
[WSM A*] Using cost function: wsm_or, lit_mode: prefer_lit
[WSM A*] Using cost function: wsm_or, lit_mode: heavily_avoid_unlit
[GeometricSolver] Lit mode: prefer_lit
[GeometricSolver] Lit mode: heavily_avoid_unlit
[GeometricSolver] Lit mode: off
```

---

### Implementation Files

| File                                                    | Role                                                   |
| ------------------------------------------------------- | ------------------------------------------------------ |
| `.\app\services\routing\astar\wsm_astar.py`               | Penalty tables, `_compute_lit_multiplier()`, A\* apply |
| `.\app\services\routing\route_finder.py`                  | Passes both params to A\* and loop solver              |
| `.\app\services\routing\loop_solvers\geometric_solver.py` | Threads params through entire leg-routing chain        |
| `.\.flowbaby\venv\Lib\site-packages\aiofiles\base.py`             | Abstract `find_loops()` signature                      |
| `.\app\services\routing\distinct_paths_runner.py`         | Forwards to all three A\* calls in multi-route mode    |
| `.\app\routes.py`                                         | Parses `prefer_lit` / `heavily_avoid_unlit` from JSON  |
| `app/static/js/modules/routing_ui.js`                   | Mutual exclusivity logic, payload construction         |
| `app/templates/index.html`                              | UI toggles (sun icon / moon icon)                      |
