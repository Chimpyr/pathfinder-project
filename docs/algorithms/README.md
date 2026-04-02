# Routing Algorithms

This section covers the core pathfinding algorithms used in ScenicPathFinder.

## Algorithms

### Weighted Sum Model (WSM) A\* Routing

The primary scenic routing algorithm that combines multiple criteria into a single cost function for A\* pathfinding.

**Key features:**

- Multi-criteria route optimisation (greenness, water, quietness, social vitality, slope)
- Weight normalisation from user preferences
- Admissible heuristic for guaranteed optimality

**See:** [docs/features/routing/wsm_feature.md](../features/routing/wsm_feature.md)

**Design decisions:** [docs/decisions/ADR-001-wsm-or-semantics.md](../decisions/ADR-001-wsm-or-semantics.md)

### Geometric Loop Solver

Specialised algorithm for finding circular routes with target distance constraints.

**Key features:**

- Budget-constrained pathfinding
- Smart bearing heuristics to avoid dead-ends
- Variety control to prevent repetitive edges

**See:** [Geometric Loop Solver Internals](loop/geometric_loop_solver.md)

## Related Documentation

- **Cost Calculation:** [Architecture - WSM Implementation](../architecture/architecture.md#wsm-a-implementation)
- **Testing:** Efficacy benchmarks in [benchmarks/benchmark_wsm.py](../../benchmarks/benchmark_wsm.py)
