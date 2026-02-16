# Geometric Loop Solver ("Natural Loops")

## 1. High-Level Summary (Simply)
The **Geometric Loop Solver** creates a round-trip route by virtually placing "waypoints" (checkpoints) in a shape around your start location—like drawing a triangle or square on a map.

-   **Smart Bearing**: Instead of guessing where to go, the solver looks at the map to find the "greenest" direction (parks, water, forests) and points the loop that way.
-   **Natural Shapes**: To avoid boring, rigid triangles, it uses flexible shapes (Quadrilaterals, Pentagons) and slightly "wiggles" the points so the route looks organic rather than robotic.
-   **No U-Turns**: The solver is smart enough to avoid sending you down a street just to make you turn around immediately. It looks for "through" streets and intersections.
-   **Flow Awareness**: It tries to predict where you are going next and snaps waypoints to roads that align with that direction, ensuring a smooth run or walk without awkward zig-zags.

---

## 2. The Problem
The previous loop generation algorithm ("v1") had several flaws:
1.  **Rigidity**: It strictly adhered to a perfect equilateral triangle. If a waypoint landed in a river or on a highway, the route would fail or create massive detours.
2.  **Blindness**: It picked directions (0°, 120°, 240°) regardless of whether those directions led to a scenic park or an industrial estate.
3.  **Spikes & Spurs**: It would often verify a waypoint by snapping to a dead-end street or a mid-block driveway, forcing the runner to run 50m down a road, turn 180°, and run back ("Lollipop" or "Fishhook" artifacts).
4.  **Failure Rate**: Strict filtering often meant "No candidates found" if the perfect mathematical point didn't land near a valid road.

---

## 3. The Solution (v2 Features)

### 3.1 Smart Bearing & Sector Analysis
Before plotting the loop, the solver scans the map around the start node (approx. 5km radius).
-   **Sector Analysis**: It divides the area into 12 "sectors" (like a clock face).
-   **Scoring**: Each sector is scored based on the density of "Green" (Parks, Woods) and "Blue" (Water) features.
-   **Result**: The loop is oriented towards the highest-scoring sectors. If you live near a park to your West, the loop will automatically head West.

### 3.2 Flexible Polygons & Perturbation
Instead of a single fixed triangle, the solver attempts multiple shapes:
-   **Triangles** (3 points)
-   **Quadrilaterals** (4 points)
-   **Pentagons** (5 points)

**Vertex Perturbation**: The angle and distance of each waypoint are randomly "jittered" (by ~10-15%). This prevents the route from looking like a perfect CAD drawing and helps it find better snapping candidates if the rigid point lands in a bad spot (e.g., a river).

### 3.3 Flow-Aware Snapping
When picking a real road node to match a virtual waypoint, the solver is now "Flow Aware":
-   **Vector Alignment**: It calculates the vector from the *Previous* point and to the *Next* point.
-   **Angle Check**: It strongly penalizes nodes that would require a sharp turn (>90°) to continue the loop. This aligns the route with the natural flow of traffic/travel.
-   **Junction Priority**: It heavily penalizes "Degree 2" nodes (mid-block segments) and favors "Degree 3+" nodes (intersections). This ensures turns happen at actual street corners, not in the middle of a road.

### 3.4 Robust Candidate Search (The Fix)
Previously, if the nearest node was a highway, the solver gave up.
**Now**, it expands the search:
1.  Query the **500 nearest nodes** (sorted by distance).
2.  Iterate through them until one passes all filters:
    -   Not a Motorway/Trunk (unless no other option).
    -   Not a Dead End (Degree > 1).
    -   Aligned with the loop direction (Flow Aware).
This ensures reliable loop generation even in difficult sparse or urban environments.

### 3.5 Spur Pruning (The "Haircut")
As a final polish, a post-processing algorithm scans the generated route for `A -> B -> A` patterns.
-   **Scenario**: The router enters a cul-de-sac or driveway and immediately reverses.
-   **Action**: The pruner detects this sequence and snips it out, connecting `A` directly to the next valid node.
-   **Result**: Clean, flowing routes without "hooks".

---

## 4. Interaction with User Preferences

## 4. Interaction with User Criteria (The "Influence Matrix")

It is important to distinguish between **Shape Generation** (where the waypoints go) and **Routing** (how we get there).

| Frontend Control | Affects Shape / Bearing? | Affects Path / Routing? | Notes |
| :--- | :--- | :--- | :--- |
| **Target Distance** | **YES** | **YES** | Determines loop radius (Shape) and A* heuristic (Routing). |
| **Greenness Weight** | No (Hardcoded*) | **YES** | *Smart Bearing assumes "Green + Water" is always good. <br>The Router actively detours to parks if weight is High. |
| **Water Weight** | No (Hardcoded*) | **YES** | *Smart Bearing treats Water bodies as scenic targets. <br>The Router actively detours to rivers/canals if weight is High. |
| **Quietness / Social**| No | **YES** | Only affects the A* cost function (preferring secondary roads or social hubs). |
| **Avoid Unsafe** | **Indirectly** | **YES** | Snapper penalizes main roads. Router heavily penalizes them. |
| **Prefer Paths** | **Indirectly** | **YES** | Snapper prefers valid paths. Router lowers cost for paths. |
| **Prefer Paved** | No | **YES** | Router increases cost for unpaved edges. |
| **Prefer Lit** | No | **YES** | Router increases cost for unlit edges (if data exists). |
| **Prefer Flat** | No | **YES** | Router penalizes edges with high gradient (`slope` weight). |
| **Shortest Path** | No | **YES** | Increases `Distance` weight relative to scenic weights. |
| **Route Variety** | **YES** | No | **Low**: Triangles only. <br>**High**: Adds Quads & Pentagons + high irregularity. |
| **Directional Bias** | **YES (Overrides)** | No | If user selects "North", Smart Bearing is disabled/constrained to North. |

* **Note on Smart Bearing**: The "Smart Bearing" analysis currently aggregates *all* scenic features (Green and Water) into a single "Scenic Score". It *does not* currently adjust this score based on the user's specific sliders (e.g. if you set Water=0, it might still point you towards a lake, though the *Router* will try not to run alongside it).

### 4.1 "Layman's" Explanation of Interaction
Think of the **Loop Solver** as a "Travel Agent" and the **Router** as the "Driver".

1.  **The Agent (Geometric Solver)** looks at the map and says: *"The nicest area is to the West (Smart Bearing), so I'll book you three stops in that direction."*
    -   It cares about general "niceness" (Parks, Water) but doesn't look at the tiny details of every road.
    -   It ensures the *shape* of the trip lands in a good neighborhood.

2.  **The Driver (A* Router)** actually drives the car from stop to stop.
    -   If you said *"Avoid Unsafe Roads"*, the Driver will take side streets.
    -   If you said *"Maximum Greenness"*, the Driver will weave through every park on the way to the stops.
    -   If you said *"Prefer Water"*, the Driver will hug the riverbank whenever possible.

**Result**: You get a loop that *heads* towards the best area (Agent) and *uses* the best roads to get there (Driver).

---

## 5. Performance
-   **Speed**: The geometric calculation is near-instant (~0.01s). The heavy lifting is the **A* Routing** between points.
-   **Efficiency**: By checking "Critical Legs" (the bridge/cross-country leg) first, the solver aborts bad candidates early, saving processing power.
-   **Comparison**: Compared to "Genetic Algorithms" or "Iterative Deepening", this approach is **significantly faster** (O(1) geometry + O(N) routing) while offering more predictable shapes than purely random walks.

## 6. Technical Flow
1.  **Analyze Sectors**: Determine best bearing.
2.  **Generate Skeleton**: Create N-gon polygon.
3.  **Smart Snap**: Find real graph nodes for each vertex (filtering dead ends/highways).
4.  **Route Legs**: A* route from $Start \to W1 \to W2 \to \dots \to Start$.
5.  **Validate**: Check total distance is within tolerance (-5% to +15% of target).
6.  **Prune**: Remove spurs.
7.  **Return**: Present top 3 diverse options to user.
