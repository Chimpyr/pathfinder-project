# ADR-023: Way-ID Canonicalization and Runtime Cache Consistency for Streetlight Routing

**Status:** Accepted
**Date:** 2026-03-29

## Context

Night-time route checks identified a regression in a known corridor:

- OSM Way `1472097444` (designated cycleway corridor) should remain preferred.
- Instead, the selected route briefly detoured via OSM Way `1351563140` (Long Down Avenue) under `heavily_avoid_unlit` with night context.

This mismatch was confusing because overlay diagnostics showed strong council lighting evidence, while routing behavior still reflected unknown lighting on many relevant routing edges.

The investigation found multiple contributing defects.

### Specific Code-Level Issues

1. Way propagation key mismatch for mixed `osmid` formats
   - Way-level propagation depended on direct string conversion of `osmid` values.
   - Real data contained mixed numeric representations of the same OSM way (for example `1472097444` and `1472097444.0`).
   - These values were treated as different keys, so council matches were not propagated to all edges of the same way.

2. Incomplete council metadata on routing edges
   - Routing edges did not consistently carry full council-derived lighting semantics (`lighting_regime`, source provenance), reducing fidelity of night-time penalties.

3. Runtime cache masking
   - In-memory merged/tile caches could continue serving pre-fix graphs (`MERGED CACHE HIT`) even after disk tile updates, making fixes appear ineffective.

4. Cache artifact portability mismatch
   - A tile pickle generated in a different runtime dependency context caused API unpickle failure (`No module named numpy._core.numeric`) after restart, delaying clean validation.

## Decision

### 1. Canonicalize way IDs before propagation lookups

Streetlight processing will canonicalize `osmid` values into a stable key before building way-to-edge maps.

Policy:

- Treat integer-like numeric variants as equivalent (`N` and `N.0` map to the same canonical key).
- Support scalar and collection-valued `osmid` fields consistently.

### 2. Preserve council-first semantics on routing edges

When council points match an edge (and propagated way edges), routing-edge fields are updated with council-authoritative metadata, including regime/provenance values used by routing explainability and penalty logic.

### 3. Enforce runtime-consistent cache validation workflow

For route behavior verification after processor changes:

- Refresh tile data in the same runtime environment that serves the API.
- Clear in-memory graph caches (or restart API) before concluding behavior.
- Treat stale merged cache hits as non-authoritative for post-fix validation.

## Consequences

### Positive

- Way-wide council propagation now survives mixed `osmid` encoding in real datasets.
- Night-time routing behavior is more consistent with council-enriched lighting evidence.
- Validation outcomes are more reliable because cache/runtime provenance is explicit.

### Tradeoffs

- Slightly more normalization logic in processor code.
- Operational validation now requires explicit cache/runtime hygiene steps.
- Cross-environment pickle artifacts remain a risk if cache files are moved between incompatible dependency stacks.

## Alternatives Considered

1. Keep raw `osmid` string matching only.
   - Rejected: fails on mixed numeric encodings seen in production-like data.

2. Rebuild full tiles only for every lighting processor tweak.
   - Rejected: expensive and unnecessary when targeted reprocessing and canonicalization are sufficient.

3. Disable merged in-memory cache for all routing calls.
   - Rejected: unacceptable performance cost; controlled cache clearing/restart is sufficient for verification workflows.

## Implementation References

- Processor changes:
  - `app/services/processors/streetlights.py`
- Regression coverage updates:
  - `tests/test_streetlights_processor.py`
  - `tests/test_street_lighting_routing_integration.py`
- Related ADRs:
  - [ADR-019: Council-First Street Lighting Integration and Overlay Source Transparency](ADR-019-council-streetlight-data.md)
  - [ADR-022: Daytime-Aware Lighting Penalties and Designated Active-Travel Priority](ADR-022-daytime-aware-lighting-and-designated-active-travel-priority.md)
