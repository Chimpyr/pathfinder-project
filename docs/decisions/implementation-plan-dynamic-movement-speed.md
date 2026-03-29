# Implementation Plan: Dynamic Movement Speed

**Status:** Proposed
**Date:** 2026-03-28
**Owner:** Routing and UX
**Related ADR:** [ADR-018](ADR-018-dynamic-movement-speed-profiles-and-unit-normalization.md)

## 1. Objective

Implement user-configurable movement speeds for walking and running (easy and race), support pace or speed input formats, support metric or imperial output units, and use selected profile speeds in Tobler-based ETA calculations across route and loop workflows.

## 2. Scope

In scope:

- User movement preferences persistence in database and browser local storage.
- Account UI for unit selection and walking/running speed configuration.
- Finder UI travel profile selector and helper tooltip.
- Routing and loop ETA calculations using selected profile speed and Tobler multipliers.
- UI output unit conversion for distances and pace/speed display.
- Documentation with direct method and formula references.

Out of scope:

- Re-optimizing route path selection based on profile speed alone (this feature targets ETA fidelity and display consistency first).
- GPS device integration changes.
- Historical analytics on user speed preferences.

## 3. Current Baseline Touchpoints

- `Config.WALKING_SPEED_KMH` and `Config.ACTIVITY_PARAMS` in [config.py](../../config.py).
- Tobler implementation in `calculate_tobler_cost`, `calculate_directional_gradients`, and `process_graph_elevation` in [app/services/processors/elevation.py](../../app/services/processors/elevation.py).
- ETA currently uses global walking speed in `_calculate_estimated_time` in [app/services/routing/route_finder.py](../../app/services/routing/route_finder.py).
- Loop ETA currently uses global walking speed in [app/routes.py](../../app/routes.py) (loop response assembly).
- User model currently has no movement settings in [app/models/user.py](../../app/models/user.py).
- Account, Finder, and Selected Route Details are in [app/templates/index.html](../../app/templates/index.html).
- Route result rendering currently assumes km in [app/static/js/modules/results_ui.js](../../app/static/js/modules/results_ui.js).

## 4. Requirements and Acceptance Criteria

| ID  | Requirement                                                | Acceptance Criteria                                                                                                                                                                                               |
| --- | ---------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | Default movement profile values exist in config            | Config defines defaults for walking, running_easy, running_race in km/h; app boots with no user preference rows; legacy behavior remains valid when no user is logged in.                                         |
| R2  | User model persists movement preferences                   | `users` table includes `preferred_distance_unit`, `walking_speed_kmh`, `running_easy_speed_kmh`, `running_race_speed_kmh`, `movement_prefs_updated_at`; migration is reversible; existing users receive defaults. |
| R3  | API supports movement preference read/write                | Authenticated user can `GET` and `PATCH` movement preferences; invalid payloads return 400 with field-level errors; unauthenticated requests return 401.                                                          |
| R4  | Local storage stores preferences for quick access          | Browser stores movement preferences under versioned key; values load on refresh before server roundtrip; malformed local payload is ignored safely.                                                               |
| R5  | Deterministic local/server sync exists                     | On login, merge policy is deterministic and timestamp-based; no silent data loss; resulting merged preferences are written to both local storage and DB.                                                          |
| R6  | Units support metric and imperial output                   | Distances and displayed pace/speed render as km or mi based on user preference; internal computations remain canonical in km and km/h.                                                                            |
| R7  | Account page supports walking + running (easy/race) inputs | Walking accepts speed input; running easy and race each accept speed or pace entry modes; pace supports per-km and per-mile; invalid inputs are blocked with clear errors.                                        |
| R8  | Finder exposes travel profile selector                     | Finder includes `walking`, `running_easy`, `running_race` selector above route actions; selected profile is sent in route and loop requests; tooltip indicates where speed settings are configured.               |
| R9  | Tobler ETA uses selected profile speed safely              | ETA is computed per edge at request time using selected speed and Tobler multiplier; no mutation of shared graph attributes per user request.                                                                     |
| R10 | Selected Route Details shows correct unit and profile pace | Selected Route Details displays distance, ETA, and assumed speed/pace matching selected travel profile and preferred unit for both route and loop modes.                                                          |
| R11 | Validation and trust boundaries enforced server-side       | Server validates all speeds, units, and profile enum values regardless of client source; out-of-range values are rejected; defaults applied when payload fields are absent.                                       |
| R12 | Documentation references methods and formulas directly     | Docs include direct references to methods in elevation and route finding modules, conversion formulas, request/response schema, and sync behavior.                                                                |
| R13 | Backward compatibility is preserved                        | Existing route requests without travel profile or preferences continue to return successful responses with walking defaults.                                                                                      |
| R14 | Performance impact is controlled                           | No per-user graph rebuild; additional ETA computation overhead remains bounded to route edge traversal already performed by request handling.                                                                     |

## 5. Data and Schema Design

### 5.1 Canonical Storage Rules

- Canonical speed unit: km/h.
- Canonical distance unit in backend payloads: km (`distance_km` remains source field).
- Display conversion to miles or mph occurs at API presentation layer and/or frontend formatting layer.

### 5.2 User Model Additions

Add to [app/models/user.py](../../app/models/user.py):

- `preferred_distance_unit`: string enum-like, values `km` or `mi`, default `km`.
- `walking_speed_kmh`: float, default from config.
- `running_easy_speed_kmh`: float, default from config.
- `running_race_speed_kmh`: float, default from config.
- `movement_prefs_updated_at`: timezone-aware datetime for conflict resolution.

Validation constraints:

- Walking speed: 2.0 to 9.0 km/h.
- Running easy speed: 4.0 to 20.0 km/h.
- Running race speed: 6.0 to 30.0 km/h.
- `running_race_speed_kmh >= running_easy_speed_kmh`.

### 5.3 Migration Plan

1. Create Alembic migration adding new columns with non-null defaults.
2. Backfill existing rows with config defaults.
3. Add check constraints for ranges.
4. Add downgrade path removing columns and constraints.

## 6. API Contract Design

### 6.1 New Endpoints

Add to [app/blueprints/user_data.py](../../app/blueprints/user_data.py):

- `GET /api/preferences/movement`
- `PATCH /api/preferences/movement`

### 6.2 PATCH Payload (canonical)

```json
{
  "preferred_distance_unit": "km",
  "walking_speed_kmh": 5.0,
  "running_easy_speed_kmh": 9.5,
  "running_race_speed_kmh": 12.0,
  "client_updated_at": "2026-03-28T12:34:56Z"
}
```

### 6.3 Route and Loop Request Additions

Add optional fields in existing request payloads:

```json
{
  "travel_profile": "walking|running_easy|running_race",
  "distance_unit": "km|mi"
}
```

Default behavior when absent:

- `travel_profile = walking`
- `distance_unit = km`

### 6.4 Response Additions

Add metadata under `stats` and/or top-level:

```json
{
  "stats": {
    "distance_km": "4.20",
    "time_min": 44,
    "assumed_speed_kmh": 5.7,
    "travel_profile": "walking"
  },
  "display": {
    "distance": "2.61",
    "distance_unit": "mi",
    "speed": "3.54",
    "speed_unit": "mph"
  }
}
```

## 7. Computation Design (Tobler and ETA)

### 7.1 Decision

Do not store user-specific speed-derived costs on graph edges. Shared graph attributes stay static and reusable.

### 7.2 Formula References

Use existing Tobler multiplier in `calculate_tobler_cost(gradient, activity)` from [app/services/processors/elevation.py](../../app/services/processors/elevation.py).

For request-time ETA:

- `speed_ms = speed_kmh * 1000 / 3600`
- `signed_gradient = uphill_gradient - downhill_gradient`
- `tobler_multiplier = calculate_tobler_cost(signed_gradient, activity)`
- `edge_time_seconds = (edge_length_m / speed_ms) * tobler_multiplier`
- `route_time_seconds = sum(edge_time_seconds)`

Activity mapping:

- `walking` -> activity `walking`
- `running_easy` and `running_race` -> activity `running`

### 7.3 Required Backend Changes

- Refactor [app/services/routing/route_finder.py](../../app/services/routing/route_finder.py):
  - Replace distance-only `_calculate_estimated_time(distance)` with route-edge aware ETA method that accepts travel profile and speed.
  - Thread `travel_profile` and selected speed through `find_route` and loop candidate time calculations.
- Update [app/routes.py](../../app/routes.py):
  - Parse `travel_profile` and unit preference.
  - Resolve selected speed from authenticated user preferences (fallback to defaults for anonymous).
  - Ensure both route and loop responses return consistent stats metadata.

## 8. Frontend Design

### 8.1 Local Storage Keys

- `movementPrefs:v1`
- `travelProfile:selected`

### 8.2 Account Page UX

Add controls in [app/templates/index.html](../../app/templates/index.html) and logic in auth/settings modules:

- Unit selector: km or mi.
- Walking speed input (speed only).
- Running easy and race sections with mode selector:
  - Speed mode input in km/h or mph (display unit aware).
  - Pace mode input in `mm:ss` with unit `per_km` or `per_mile`.

Client-side conversions:

- `speed_kmh = 60 / pace_min_per_km`
- `speed_kmh = (60 * 1.609344) / pace_min_per_mile`
- `speed_mph = speed_kmh / 1.609344`
- `distance_mi = distance_km / 1.609344`

### 8.3 Finder UX

In [app/templates/index.html](../../app/templates/index.html):

- Add travel profile selector directly above route action button(s).
- Add info tooltip clarifying speed configuration is in Account settings.

### 8.4 Selected Route Details

Update [app/static/js/modules/results_ui.js](../../app/static/js/modules/results_ui.js):

- Render distance and speed in preferred unit.
- Render assumed profile label and pace/speed consistently.
- Apply same formatter for loop cards and route cards.

## 9. Sync and Conflict Resolution

Merge policy on login:

1. If only one source exists, use it.
2. If both exist, prefer newer `updated_at`.
3. If timestamps equal, prefer server copy.
4. Persist merged result to both sources.

Failure behavior:

- If preference sync fails, route calls continue with local values and log warning.
- If both local and server invalid, fallback to config defaults.

## 10. Delivery Sequence

1. Add config defaults and user model columns.
2. Add migration and run migration tests.
3. Add movement preference API endpoints and validation.
4. Implement backend travel profile ETA pipeline changes.
5. Implement Account and Finder UI changes.
6. Implement output unit formatting in results components.
7. Add documentation updates and run full test matrix.

## 11. Test Matrix

| Test ID | Requirements | Layer       | Scenario                                                      | Expected Result                                                       |
| ------- | ------------ | ----------- | ------------------------------------------------------------- | --------------------------------------------------------------------- |
| UT-01   | R6, R7       | Unit        | Convert pace `6:00 /km` to km/h                               | Result is `10.0 km/h` (within tolerance).                             |
| UT-02   | R6, R7       | Unit        | Convert pace `8:00 /mi` to km/h                               | Result is `12.07008 km/h` (within tolerance).                         |
| UT-03   | R6           | Unit        | Convert `10 km/h` to mph                                      | Result is `6.21371 mph` (rounded for UI only).                        |
| UT-04   | R9           | Unit        | Tobler multiplier at flat grade for walking                   | Multiplier approximately `1.0`.                                       |
| UT-05   | R9           | Unit        | ETA sum over edges with mixed gradients                       | Edge-wise ETA sum matches expected fixture value.                     |
| UT-06   | R11          | Unit        | Invalid `travel_profile` enum                                 | Validation error 400 with deterministic message.                      |
| UT-07   | R11          | Unit        | Out-of-range running race speed                               | Validation error 400; no DB write.                                    |
| IT-01   | R2, R13      | Integration | Migrate existing DB with users                                | Migration succeeds; defaults present for existing rows.               |
| IT-02   | R3           | Integration | `GET /api/preferences/movement` authenticated                 | Returns persisted values and unit.                                    |
| IT-03   | R3, R11      | Integration | `PATCH /api/preferences/movement` invalid payload             | Returns 400 with field error map.                                     |
| IT-04   | R3, R13      | Integration | Route request without profile fields                          | Response success with walking defaults.                               |
| IT-05   | R8, R9       | Integration | `travel_profile=running_easy` on `/api/route`                 | ETA lower than walking for same route, profile echoed in response.    |
| IT-06   | R8, R9       | Integration | `travel_profile=running_race` on `/api/loop`                  | ETA lower than running_easy for same loop distance and gradients.     |
| IT-07   | R6, R10      | Integration | `distance_unit=mi` in route response path                     | Display payload or frontend formatter outputs miles/mph consistently. |
| IT-08   | R5           | Integration | Local newer than server on login merge                        | Local values win and are pushed to server.                            |
| IT-09   | R5           | Integration | Server newer than local on login merge                        | Server values win and overwrite local cache.                          |
| E2E-01  | R7, R10      | E2E         | Set running race via pace on Account page then route          | Selected Route Details shows converted speed and updated ETA.         |
| E2E-02  | R8, R10      | E2E         | Switch Finder profile walking -> running_easy -> running_race | ETA updates in expected direction each switch.                        |
| E2E-03  | R8           | E2E         | Hover info tooltip near travel profile selector               | Tooltip content explains where to set preferred speeds.               |
| E2E-04  | R4, R5       | E2E         | Reload page and re-login after changing prefs                 | Preferences persist locally and from DB across session boundary.      |
| REG-01  | R13          | Regression  | Existing GPX export and save-query flow                       | No functional regressions in export/save paths.                       |
| PERF-01 | R14          | Performance | Compare route API latency before/after                        | P95 regression within agreed threshold (target <= 10%).               |

## 12. Documentation Deliverables

Update or add documents with direct references:

- [docs/decisions/ADR-018-dynamic-movement-speed-profiles-and-unit-normalization.md](ADR-018-dynamic-movement-speed-profiles-and-unit-normalization.md)
- [docs/features](../features) entry for user-visible behavior and screenshots.
- Method references to:
  - `calculate_tobler_cost` in [app/services/processors/elevation.py](../../app/services/processors/elevation.py)
  - `find_route` and ETA helper in [app/services/routing/route_finder.py](../../app/services/routing/route_finder.py)
  - Route and loop API handlers in [app/routes.py](../../app/routes.py)

## 13. Definition of Done

- All requirements R1-R14 have passing tests from the matrix.
- ADR-018 is committed and indexed.
- User can configure speeds, choose travel profile, and see accurate unit-aware ETA in route details.
- No breakage to existing route generation and saved data flows.
