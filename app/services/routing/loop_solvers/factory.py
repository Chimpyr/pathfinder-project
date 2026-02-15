"""
Loop Solver Factory Module

Config-based instantiation of loop routing solvers.
Reads LOOP_SOLVER_ALGORITHM from config.py to determine which solver to use.

Usage:
    solver = LoopSolverFactory.create()
    candidates = solver.find_loops(graph, start_node, target_distance, weights)
"""

from typing import Optional
from app.services.routing.loop_solvers.base import LoopSolverBase


class LoopSolverFactory:
    """
    Factory for creating loop solver instances based on configuration.

    Supported algorithms:
        - BUDGET_ASTAR: Budget-constrained A* with state augmentation
        - GEOMETRIC: Triangle-plateau geometric skeleton + WSM A* legs
        - TREE_SEARCH: Tree search (single run, many routes)
        - RANDOM_WALK: Legacy two-phase random walk + A* return (deprecated)
    """

    # Registry of available solver classes (lazy-loaded)
    _registry = {}

    @classmethod
    def create(cls, algorithm: Optional[str] = None) -> LoopSolverBase:
        """
        Create a loop solver instance.

        Args:
            algorithm: Solver algorithm name. If None, reads from Flask
                       config or falls back to 'BUDGET_ASTAR'.

        Returns:
            LoopSolverBase instance ready for find_loops() calls.

        Raises:
            ValueError: If the requested algorithm is not available.
        """
        if algorithm is None:
            algorithm = cls._get_config_algorithm()

        algorithm = algorithm.upper()

        # Lazy import to avoid circular dependencies
        if algorithm == 'BUDGET_ASTAR':
            from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver
            return BudgetAStarSolver()

        elif algorithm == 'GEOMETRIC':
            from app.services.routing.loop_solvers.geometric_solver import GeometricLoopSolver
            return GeometricLoopSolver()

        elif algorithm == 'TREE_SEARCH':
            from app.services.routing.loop_solvers.tree_search_solver import TreeSearchSolver
            return TreeSearchSolver()

        elif algorithm == 'RANDOM_WALK':
            from app.services.routing.loop_solvers.random_walk_solver import RandomWalkSolver
            return RandomWalkSolver()

        else:
            available = ['BUDGET_ASTAR', 'GEOMETRIC', 'TREE_SEARCH', 'RANDOM_WALK']
            raise ValueError(
                f"Unknown loop solver algorithm: '{algorithm}'. "
                f"Available: {available}"
            )

    @staticmethod
    def _get_config_algorithm() -> str:
        """
        Read LOOP_SOLVER_ALGORITHM from Flask config or config.py.

        Returns:
            Algorithm name string (e.g. 'BUDGET_ASTAR').
        """
        try:
            from flask import current_app
            return current_app.config.get('LOOP_SOLVER_ALGORITHM', 'BUDGET_ASTAR')
        except RuntimeError:
            # Outside Flask context (testing, CLI)
            pass

        try:
            from config import Config
            return getattr(Config, 'LOOP_SOLVER_ALGORITHM', 'BUDGET_ASTAR')
        except ImportError:
            pass

        return 'BUDGET_ASTAR'

    @classmethod
    def available_algorithms(cls) -> list:
        """Return list of available algorithm names."""
        return ['BUDGET_ASTAR', 'GEOMETRIC', 'TREE_SEARCH', 'RANDOM_WALK']
