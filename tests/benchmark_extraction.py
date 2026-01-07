import time
import os
import sys
# Ensure app is in path
sys.path.append(os.getcwd())
from app.services.data_loader import OSMDataLoader
from pyrosm import OSM

def benchmark():
    base_dir = "app/data"
    # Ensure we use Bristol
    pbf_path = os.path.join(base_dir, "bristol.osm.pbf")
    if not os.path.exists(pbf_path):
        # Fallback to older name if needed or download
        loader = OSMDataLoader()
        loader.ensure_data_for_bbox((51.44, -2.60, 51.46, -2.58))
        pbf_path = loader.file_path

    print(f"Benchmarking feature extraction on: {pbf_path}")
    osm = OSM(pbf_path)
    loader = OSMDataLoader()
    
    start_time = time.time()
    features = loader._extract_features(osm)
    end_time = time.time()
    
    print(f"Extraction took: {end_time - start_time:.4f} seconds")
    print(f"Extracted {len(features)} features.")

if __name__ == "__main__":
    benchmark()
