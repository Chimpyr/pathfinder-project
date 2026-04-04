# Street Lighting Testing Suite

This test suite validates street lighting across both runtime consumers:

- Overlay path: PostGIS/Martin vector tiles
- Routing path: in-memory graph edge costs (`prefer_lit_streets`, `avoid_unlit_streets`)

---

## Goals

1. Prove routing toggles use council-enriched edge lighting, not only raw OSM tags.
2. Prevent regressions where council augmentation stops affecting route selection.
3. Keep docs, code, and data pipeline behavior aligned.

---

## System Under Test (Visual)

```
Council GPKG + OSM PBF
  -> graph build pipeline (OSMDataLoader + scenic orchestrator + streetlights processor)
  -> in-memory graph edge attributes (`lit`, `lit_source`, `lit_source_detail`)
  -> WSM A* lit multipliers
  -> /api/route and /api/loop results

Council GPKG + OSM PBF
  -> seeder SQL pipeline
  -> PostGIS street_lighting
  -> Martin MVT endpoints
  -> frontend street-lighting overlay + filters + hover cards
```

---

## Automated Suite

### 1) Unit and Integration Tests (Pytest)

Run these as the core regression pack:

```bash
pytest -q \
  tests/test_streetlights_processor.py \
  tests/test_street_lighting_routing_integration.py \
  tests/test_distinct_paths.py
```

Coverage intent:

- `tests/test_streetlights_processor.py`
  - Validates council point snapping and edge promotion (`lit='yes'`, council provenance fields).
- `tests/test_street_lighting_routing_integration.py`
  - Validates both routing toggles reroute toward council-promoted lit edges.
  - Validates lit multiplier handling on council-promoted edges.
- `tests/test_distinct_paths.py`
  - Validates baseline route purity (lit toggles do not leak into baseline route run).

### 2) Optional Wider Routing Regression

```bash
pytest -q \
  tests/test_wsm_astar.py \
  tests/test_loop_solvers.py
```

These confirm broader A\* and loop behavior remains stable while lighting tests evolve.

---

## Manual/API Test Matrix

| ID      | Scenario                             | Steps                                                                          | Expected Result                                                                        |
| ------- | ------------------------------------ | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| SL-R-01 | Prefer lit uses council augmentation | Enable `prefer_lit_streets`, request route crossing known council-lit corridor | Route shifts toward lit segments when feasible                                         |
| SL-R-02 | Heavy avoid unlit strongest behavior | Enable `avoid_unlit_streets`                                                   | Route strongly avoids unlit/unknown segments unless no alternative                     |
| SL-R-03 | Mutual exclusivity                   | Toggle one lighting option then the other in UI                                | Only one remains checked                                                               |
| SL-R-04 | Distinct paths baseline purity       | Multi-route enabled with lighting toggles on                                   | Baseline route remains shortest-path style; lit toggle affects extremist/balanced runs |
| SL-O-01 | Overlay source filtering             | Overlay ON, switch source filter among `all/council/osm/bristol/south_glos`    | Tiles update and match selected source semantics                                       |
| SL-O-02 | Regime filtering                     | Switch regime filters                                                          | Visible segments update according to regime values                                     |
| SL-O-03 | Hover evidence split                 | Hover edge with both council and OSM evidence                                  | Card shows separate council and OSM evidence sections                                  |

---

## Data Integrity Checks (SQL)

Run in PostGIS container to confirm overlay data assumptions:

```sql
-- Source distribution sanity
SELECT lit_source_primary, COUNT(*)
FROM street_lighting
GROUP BY lit_source_primary;

-- Council-match enrichment presence
SELECT COUNT(*) AS council_rows
FROM street_lighting
WHERE lit_source_primary = 'council';

-- OSM evidence retained after council promotion
SELECT COUNT(*) AS dual_evidence_rows
FROM street_lighting
WHERE lit_source_primary = 'council'
  AND osm_lit_raw IS NOT NULL;
```

Expected:

- `lit_source_primary='council'` rows exist when council dataset is loaded.
- Some council-primary rows still retain OSM evidence (`osm_lit_raw`) by design.

---

## Test Data Preconditions

1. `app/data/streetlight/combined_streetlights.gpkg` exists for council augmentation tests.
2. Routing graph build uses `STREETLIGHT_MODE=FAST`.
3. Relevant map area has enough connected alternatives for lit-routing behavior to be observable.

---

## Documentation Sync Checklist

Whenever lighting logic changes, update all of:

- `docs/features/street_lighting.md`
- `docs/features/street_lighting_routing_bias.md`
- `docs/testing/street_lighting_test_suite.md`
- ADRs if decision-level behavior changed (for example source precedence, UX evidence model)

---

## Pass Criteria

A release is considered lighting-safe when:

1. Core pytest pack passes.
2. Manual matrix SL-R-01 to SL-O-03 passes in local environment.
3. SQL integrity checks confirm council and OSM evidence assumptions.
4. Documentation sync checklist is complete.
