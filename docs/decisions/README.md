# Architectural Decision Records (ADRs)

This folder contains records of significant architectural and design decisions made during the development of ScenicPathFinder.

## What is an ADR?

An Architectural Decision Record captures a decision that has significant impact on the system's design, along with the context and consequences. This helps future developers understand _why_ decisions were made, not just _what_ was implemented.

## ADR Format

Each ADR follows this structure:

1. **Title** - Short descriptive name
2. **Status** - Proposed / Accepted / Deprecated / Superseded
3. **Context** - The situation and problem being addressed
4. **Decision** - What we decided to do
5. **Consequences** - The resulting effects, both positive and negative
6. **Alternatives Considered** - Other options that were evaluated

## Index

| ID                                                                                 | Title                                                                         | Status   | Date       |
| ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- | -------- | ---------- |
| [ADR-001](ADR-001-wsm-or-semantics.md)                                             | WSM OR-Semantics for Multi-Criteria Routing                                   | Accepted | 2026-01-19 |
| [ADR-002](ADR-002-greenness-detection-method.md)                                   | Greenness Detection Method Selection                                          | Accepted | 2025-11    |
| [ADR-003](ADR-003-weighted-min-and-slider-scale.md)                                | Weighted-MIN Algorithm and 0-5 Slider Scale                                   | Accepted | 2026-01-19 |
| [ADR-004](ADR-004-bbox-clipping.md)                                                | Bounding Box Clipping for Graph Loading                                       | Accepted | 2026-01-30 |
| [ADR-005](ADR-005-async-task-cache-reliability.md)                                 | Async Task Lock Management and Cache Reliability                              | Accepted | 2026-01-30 |
| [ADR-011](ADR-011-restricted-access-pruning.md)                                    | Restricted-Access Edge and Node Pruning                                       | Accepted | 2026-02-22 |
| [ADR-012](ADR-012-dual-database-segregation.md)                                    | Dual-Database Segregation for User Persistence                                | Accepted | 2026-02-22 |
| [ADR-013](ADR-013-automated-database-bootstrapping.md)                             | Automated Database Bootstrapping                                              | Accepted | 2026-02-22 |
| [ADR-014](ADR-014-parametrised-route-storage.md)                                   | Parametrised Route Storage Strategy                                           | Accepted | 2026-02-22 |
| [ADR-015](ADR-015-connection-pool-tuning.md)                                       | Connection Pool Tuning for Dual-Database Architecture                         | Accepted | 2026-02-22 |
| [ADR-016](ADR-016-alembic-migration-safety.md)                                     | Alembic Migration Safety — include_object Firewall                            | Accepted | 2026-02-22 |
| [ADR-018](ADR-018-dynamic-movement-speed-profiles-and-unit-normalization.md)       | Dynamic Movement Speed Profiles and Unit Normalization                        | Proposed | 2026-03-28 |
| [ADR-019](ADR-019-council-streetlight-data.md)                                     | Council-First Street Lighting Integration and Overlay Source Transparency     | Accepted | 2026-03-29 |
| [ADR-020](ADR-020-street-lighting-hover-provenance-cards.md)                       | Street Lighting Hover Provenance Cards                                        | Accepted | 2026-03-29 |
| [ADR-021](ADR-021-advanced-options-activation-and-compare-mode.md)                 | Advanced Options Activation and Baseline Compare Mode                         | Accepted | 2026-03-29 |
| [ADR-022](ADR-022-daytime-aware-lighting-and-designated-active-travel-priority.md) | Daytime-Aware Lighting Penalties and Designated Active-Travel Priority        | Proposed | 2026-03-29 |
| [ADR-023](ADR-023-way-id-canonicalization-and-runtime-cache-consistency.md)        | Way-ID Canonicalization and Runtime Cache Consistency for Streetlight Routing | Accepted | 2026-03-29 |

## Related Documentation

- [WSM Feature Documentation](../features/routing/wsm_feature.md) - Technical details of the cost function
- [Greenness Methods Comparison](../features/research/greenness_methods_comparison.md) - Research on greenness detection approaches
- [Custom Walking Filter](../features/custom_walking_filter.md) - Walking network filter and restricted-access pruning
- [User Accounts & Authentication](../features/user_accounts.md) - User registration, login, and session management
- [Saved Data (Pins & Routes)](../features/saved_data.md) - CRUD API for user-saved locations and routes
- [Street Lighting Feature](../features/street_lighting.md) - Overlay pipeline, schema, and filter semantics
