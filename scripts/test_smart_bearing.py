
import sys
import os
import logging
from typing import Dict

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.core.data_loader import OSMDataLoader
from app.services.routing.loop_solvers.geometric_solver import GeometricLoopSolver

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_smart_bearing():
    """
    Test Smart Bearing vs Equidistant Bearing generation.
    """
    print("Initializing OSMDataLoader...")
    loader = OSMDataLoader()
    
    # Use a known bbox or download a small one
    # Bristol Center roughly
    bbox = (51.44, -2.62, 51.47, -2.57) 
    
    print("Loading graph (this might take a moment)...")
    # We need a graph with features loaded
    # Using 'network_type'='walk'
    graph = loader.load_graph(bbox=bbox)
    
    if not hasattr(graph, 'features') or graph.features is None:
        print("[ERROR] Graph features not loaded. Cannot test Smart Bearing.")
        return

    print(f"Graph loaded: {len(graph.nodes)} nodes, {len(graph.features)} scenic features.")

    # Pick a start node
    # Center of Bristol
    import osmnx as ox
    start_lat, start_lon = 51.4545, -2.5879
    start_node = ox.nearest_nodes(graph, start_lon, start_lat)
    print(f"Start Node: {start_node} ({start_lat}, {start_lon})")

    solver = GeometricLoopSolver()
    
    target_dist = 5000.0 # 5km
    weights = {'distance': 1.0, 'greenness': 5.0}

    print("\n--- Test 1: Standard Equidistant Bearings ---")
    candidates_std = solver.find_loops(
        graph, start_node, target_dist, weights, 
        num_candidates=3, 
        max_search_time=10, # Short time, we just want to see logs
        use_smart_bearing=False
    )
    
    print("\n--- Test 2: Smart Bearings ---")
    candidates_smart = solver.find_loops(
        graph, start_node, target_dist, weights, 
        num_candidates=3, 
        max_search_time=10, 
        use_smart_bearing=True
    )

    print("\n--- Comparison ---")
    print(f"Standard candidates: {len(candidates_std)}")
    print(f"Smart candidates: {len(candidates_smart)}")
    
    # Note: We can't easily assert exact bearings without parsing logs or inspecting internals
    # But observing the logs during run (or output) will confirm the behavior.

if __name__ == "__main__":
    test_smart_bearing()
