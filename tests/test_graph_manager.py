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
    
    # First call
    print("Calling get_graph (first time)...")
    graph1 = GraphManager.get_graph(bbox=(0,0,0,0)) # bbox is ignored
    
    assert isinstance(graph1, nx.MultiDiGraph)
    assert len(graph1.nodes) > 0
    assert len(graph1.edges) > 0
    
    # Second call
    print("Calling get_graph (second time)...")
    graph2 = GraphManager.get_graph(bbox=(0,0,0,0))
    
    # Should be identical object
    assert graph1 is graph2
    print("Graph caching verified.")

def test_graph_has_attributes():
    """
    Test that the loaded graph has the expected attributes from OSMDataLoader.
    """
    GraphManager._graph = None
    graph = GraphManager.get_graph()
    
    # Check random edge for 'surface' or 'lit' or other tags
    found_tags = False
    for u, v, k, data in graph.edges(keys=True, data=True):
        if 'surface' in data or 'lit' in data or 'footway' in data:
            found_tags = True
            break
            
    assert found_tags, "Graph should contain edges with extracted tags like surface, lit, etc."
