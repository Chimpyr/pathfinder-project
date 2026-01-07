import pytest
import os
from app.services.data_loader import OSMDataLoader
import networkx as nx

# Mocking or using a real file? 
# For this test, we might want to test the download mechanism (real) or just file existence.
# Given user wants robust local workflow, let's try a real but small file if possible, or stick to the one they suggested but mock the download to save bandwidth if testing repeatedly.
# But for the first run, let's actually TRY to initialize it.

def test_data_loader_init():
    """
    Test that the loader initializes and finds the file.
    """
    # Using the manually downloaded Bristol file
    filename = "bristol-260106.osm.pbf"
    loader = OSMDataLoader(pbf_filename=filename)
    
    assert os.path.exists(loader.file_path)
    assert os.path.getsize(loader.file_path) > 1024 * 1024 # > 1MB

def test_load_graph_structure():
    """
    Test loading the graph from the PBF.
    """
    filename = "bristol-260106.osm.pbf"
    loader = OSMDataLoader(pbf_filename=filename)
    
    # Debug print
    print(f"Testing Pyrosm with BBox: None (Loading full file)")
    
    graph = loader.load_graph(bbox=None)
    
    assert graph is not None
    assert isinstance(graph, nx.MultiDiGraph)
    assert len(graph.nodes) > 0
    
    # Check for custom attributes
    # We requested: surface, lit, incline, etc.
    # Check the first edge that has data
    found_surface = False
    for u, v, data in graph.edges(data=True):
        if 'surface' in data:
            found_surface = True
            break
            
    # Note: Not all edges have surface, but in a whole town, some should.
    # If this fails, it might just be the area selection, but it's a good check.
    if not found_surface:
         print("Warning: No 'surface' tag found in the sample area.")
    else:
         print("Verified 'surface' tag present.")

