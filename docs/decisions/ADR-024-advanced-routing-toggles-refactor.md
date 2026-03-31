# ADR 024: Advanced Routing Toggles Refactor

## Status

Accepted

## Context

The previous "Advanced Options" feature set enabled specific routing modifiers but faced usability and algorithmic clarity challenges. We initially had toggles for lighting and safety that were sometimes conflicting (e.g., both lit and unlit enabled) or conceptually murky on how they affected the A\* cost function. Additionally, features like promoting distinct geometry across loop routes lacked strong, explicit tagging controls, and "Prefer Nature" / "Prefer Dedicated Pavements" options were not formalised as categorical modes.

To give users more agency and ensure route calculations are mathematically distinct, the Advanced Options front-end UI and the underlying WSM A\* logic required restructuring into mutually logical groups: Environmental Constraints (surface type & physical environment) and Safety Options (lighting, road categorization).

## Decision

1. **Categorised Toggles:** We restructued the Advanced Options into grouped modes:
   - **Environment Types (Mutually Exclusive):**
     - `prefer_dedicated`: Rewards designated walking/cycling paths (`highway=pedestrian/path`, etc.) and paves surfaces. Penalises vehicular shared roads (e.g., residential/secondary).
     - `prefer_nature`: Rewards natural paths/trails (`highway=path`, `surface=dirt/grass`, etc.). Penalises hard paving and heavy vehicular areas.
   - **Lighting Options (Mutually Exclusive):**
     - `prefer_lit`: Rewards edges tagged or mapped as lit in the council dataset.
     - `avoid_unlit`: Applies a heavy severe multiplier ($5 \times$) to unlit streets, forcing alternatives.
   - **Safety Options:**
     - `avoid_unsafe`: Targets fast/heavy vehicular roads (like primary or motorways lacking strong pedestrian attributes) and avoids them heavily.

2. **UI Governance:** Replaced simple checkboxes with robust javascript toggle managers (`routing_ui.js`). Logic enforces mutual exclusivity (e.g., selecting 'Prefer Nature Trails' deselects and disables 'Prefer Dedicated Pavements', turning on 'Heavily Avoid Unlit' disables 'Prefer Lit').

3. **Backend Canonicalization:** Implemented a robust parsing step to ensure default API calls to `/api/loop` and `/api/route` coerce legacy or null toggle payload attributes to standard boolean flags (`preferred_dedicated`, `preferred_nature`, `preferred_lit`, `avoid_unlit`, `avoid_unsafe`).

4. **Multiplicative Edge Costs:** The modifiers are applied explicitly via proportional A\* multipliers in `calculate_wsm_cost()`. 'Nature' triggers a $0.4 \times$ cost reduction on natural surfaces and limits penalties, whilst 'Dedicated' heavily avoids $2.0 \times$ car roads, ensuring profound geometric separation of generated loop routes.

## Consequences

- **Positive:** Route geometry is distinct and strictly adheres to intuitive user requests for dedicated versus nature trails.
- **Positive:** Improved frontend constraints prevent contradictory request parameters.
- **Negative:** Increased number of active multipliers requires slightly heavier logic on node expansion in `wsm_astar.py`, although benchmarked correctly to not exceed runtime constraints.
- **Maintenance:** The schema for saved routes required mapping these new options into `RoutePreferences` parametrised storage.
