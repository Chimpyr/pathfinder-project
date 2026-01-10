"""
Processors Package

Edge attribute processors for scenic routing features.
Each processor adds specific cost attributes to graph edges.
"""

from app.services.processors.greenness import (
    process_graph_greenness_fast,
    process_graph_greenness_novack,
)
from app.services.processors.water import process_graph_water
from app.services.processors.social import process_graph_social
from app.services.processors.elevation import process_graph_elevation
from app.services.processors.quietness import process_graph_quietness
from app.services.processors.orchestrator import process_scenic_attributes

__all__ = [
    'process_graph_greenness_fast',
    'process_graph_greenness_novack',
    'process_graph_water',
    'process_graph_social',
    'process_graph_elevation',
    'process_graph_quietness',
    'process_scenic_attributes',
]
