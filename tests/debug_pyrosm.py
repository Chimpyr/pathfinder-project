import os
from pyrosm import OSM

def debug_load():
    # 1. Check path
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "app/data")
    pbf_path = os.path.join(data_dir, "bristol-260106.osm.pbf")
    
    print(f"Checking path: {pbf_path}")
    
    if not os.path.exists(pbf_path):
        print("File does NOT exist.")
        return
        
    size = os.path.getsize(pbf_path)
    print(f"File size: {size / 1024 / 1024:.2f} MB")
    
    if size < 1000:
        print("File is too small, likely corrupt.")
        return

    # 2. Try minimal Init
    print("Initializing OSM...")
    try:
        osm = OSM(pbf_path)
        print("OSM initialized.")
    except Exception as e:
        print(f"Failed to init OSM: {e}")
        return

    # 3. Try parsing something simple (nodelist)
    print("Parsing nodes (count)...")
    try:
        # Just getting the file path is safe, reading is the test.
        # get_network is heavy. 
        # let's try reading the bounding box from the file metadata if possible?
        # or simplified get_network
        net = osm.get_network(network_type="walking", nodes=False) # Simplified
        print(f"Network loaded. Edges: {len(net)}")
    except Exception as e:
        print(f"Failed to parse network: {e}")

if __name__ == "__main__":
    debug_load()
