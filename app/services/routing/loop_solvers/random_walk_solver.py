"""
Random Walk Solver (Legacy Wrapper)

Wraps the existing LoopAStar two-phase algorithm (guided random walk + A*
return) as a LoopSolverBase implementation for backward compatibility.

This solver is DEPRECATED in favour of BudgetAStarSolver.
Use config LOOP_SOLVER_ALGORITHM = 'RANDOM_WALK' only for comparison.

See 002-loop-route-refactor.md for deprecation rationale.
"""

import time
from typing import Dict, List, Optional

from app.services.routing.loop_solvers.base import (
    LoopCandidate,
    LoopSolverBase,
    calculate_quality_score,
    select_diverse_candidates,
)


class RandomWalkSolver(LoopSolverBase):
    """
    Legacy two-phase loop solver wrapped in the LoopSolverBase interface.

    Phase 1: Guided random walk outward for ~half the target distance.
    Phase 2: A* return to start with soft penalty on outbound edges.

    Multiple random attempts are made and the best candidates are returned.
    """

    def find_loops(
        self,
        graph,
        start_node: int,
        target_distance: float,
        weights: Dict[str, float],
        combine_nature: bool = False,
        directional_bias: str = "none",
        num_candidates: int = 3,
        distance_tolerance: float = 0.15,
        max_search_time: float = 120,
    ) -> List[LoopCandidate]:
        """
        Find loop candidates using the legacy random walk approach.

        Generates multiple candidates via the old LoopAStar and wraps
        them as LoopCandidate objects.
        """
        from app.services.routing.astar.loop_astar import LoopAStar

        t0 = time.time()

        solver = LoopAStar(
            graph=graph,
            weights=weights,
            target_distance=target_distance,
            combine_nature=combine_nature,
            directional_bias=directional_bias,
            distance_tolerance=distance_tolerance,
            max_search_time=max_search_time,
        )

        result = solver.astar(start_node, start_node)
        elapsed = time.time() - t0

        if result is None:
            return []

        route = list(result)
        distance = solver._route_distance(route)
        scenic_cost = solver._route_cost(route)
        deviation = abs(distance - target_distance) / target_distance

        quality = calculate_quality_score(deviation, scenic_cost)

        candidate = LoopCandidate(
            route=route,
            distance=distance,
            scenic_cost=scenic_cost,
            deviation=deviation,
            quality_score=quality,
            algorithm='random_walk',
            label='Random Walk',
            metadata={
                'elapsed_seconds': round(elapsed, 2),
                'directional_bias': directional_bias,
            },
        )

        return select_diverse_candidates([candidate], k=min(num_candidates, 1))
