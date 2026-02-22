# Architectural Decision Records (ADRs)

This folder contains records of significant architectural and design decisions made during the development of ScenicPathFinder.

## What is an ADR?

An Architectural Decision Record captures a decision that has significant impact on the system's design, along with the context and consequences. This helps future developers understand *why* decisions were made, not just *what* was implemented.

## ADR Format

Each ADR follows this structure:

1. **Title** - Short descriptive name
2. **Status** - Proposed / Accepted / Deprecated / Superseded
3. **Context** - The situation and problem being addressed
4. **Decision** - What we decided to do
5. **Consequences** - The resulting effects, both positive and negative
6. **Alternatives Considered** - Other options that were evaluated

## Index

| ID | Title | Status | Date |
|----|-------|--------|------|
| [ADR-001](ADR-001-wsm-or-semantics.md) | WSM OR-Semantics for Multi-Criteria Routing | Accepted | 2026-01-19 |
| [ADR-002](ADR-002-greenness-detection-method.md) | Greenness Detection Method Selection | Accepted | 2025-11 |
| [ADR-003](ADR-003-weighted-min-and-slider-scale.md) | Weighted-MIN Algorithm and 0-5 Slider Scale | Accepted | 2026-01-19 |
| [ADR-004](ADR-004-bbox-clipping.md) | Bounding Box Clipping for Graph Loading | Accepted | 2026-01-30 |
| [ADR-005](ADR-005-async-task-cache-reliability.md) | Async Task Lock Management and Cache Reliability | Accepted | 2026-01-30 |
| [ADR-011](ADR-011-restricted-access-pruning.md) | Restricted-Access Edge and Node Pruning | Accepted | 2026-02-22 |

## Related Documentation

- [WSM Feature Documentation](../wsm_feature.md) - Technical details of the cost function
- [Greenness Methods Comparison](../greenness_methods_comparison.md) - Research on greenness detection approaches
- [Custom Walking Filter](../features/custom_walking_filter.md) - Walking network filter and restricted-access pruning
