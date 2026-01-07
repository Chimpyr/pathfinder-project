import pytest
from app.services.graph_manager import GraphManager
import networkx as nx

def test_get_graph_singleton():
    """
    Test that get_graph loads the graph and returns the same instance on subsequent calls.
    """
    # Force reset
    GraphManager._graph = None
    GraphManager._loader = None
    
    # First call - Use Bristol BBox to hit local file
    print("Calling get_graph (first time)...")
    bristol_bbox = (51.44, -2.60, 51.46, -2.58)
    graph1 = GraphManager.get_graph(bbox=bristol_bbox)
    
    assert isinstance(graph1, nx.MultiDiGraph)
    assert len(graph1.nodes) > 0
    assert len(graph1.edges) > 0
    
    # Second call
    print("Calling get_graph (second time)...")
    graph2 = GraphManager.get_graph(bbox=bristol_bbox)
    
    # Should be identical object
    assert graph1 is graph2
    print("Graph caching verified.")

def test_graph_has_attributes():
    """
    Test that the loaded graph has the expected attributes from OSMDataLoader.
    """
    GraphManager._graph = None
    # Pass bbox to trigger correct file loading
    bristol_bbox = (51.44, -2.60, 51.46, -2.58)
    graph = GraphManager.get_graph(bbox=bristol_bbox)
    
    # Check random edge for 'surface' or 'lit' or other tags
    found_tags = False
    for u, v, k, data in graph.edges(keys=True, data=True):
        if 'surface' in data or 'lit' in data or 'footway' in data:
            found_tags = True
            break
            
    assert found_tags, "Graph should contain edges with extracted tags like surface, lit, etc."
