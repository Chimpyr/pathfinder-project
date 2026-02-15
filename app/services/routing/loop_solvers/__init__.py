"""
Loop Solvers Package

Plug-and-play framework for loop (round-trip) routing algorithms.

Provides:
    - LoopSolverBase: Abstract base class for all loop solvers
    - LoopCandidate: Standardised data structure for loop results
    - LoopSolverFactory: Config-based solver instantiation

Available solvers:
    - BudgetAStarSolver: Budget-constrained A* with state augmentation
    - TreeSearchSolver: Tree search (single run, many routes)
    - (Legacy) LoopAStar: Two-phase random walk + A* return (deprecated)

Usage:
    from app.services.routing.loop_solvers import LoopSolverFactory
    solver = LoopSolverFactory.create(graph, weights)
    candidates = solver.find_loops(graph, start_node, target_distance, weights)
"""

from app.services.routing.loop_solvers.base import LoopSolverBase, LoopCandidate
from app.services.routing.loop_solvers.factory import LoopSolverFactory

__all__ = ['LoopSolverBase', 'LoopCandidate', 'LoopSolverFactory']
