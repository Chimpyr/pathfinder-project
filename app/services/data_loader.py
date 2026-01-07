import os
import requests
from pyrosm import OSM

try:
    from pyrosm import to_graph
except ImportError:
    # Attempt fallback or local definition if missing in this version
    to_graph = None

class OSMDataLoader:
    """
    Handles the robust downloading and parsing of local OSM PBF files.
    Designed for performance and offline capability.
    """

    def __init__(self, pbf_filename: str = "bristol-260106.osm.pbf", data_dir: str = "app/data"):
        """
        Initialize the loader. Checks if the PBF file exists locally.
        
        Args:
            pbf_filename (str): Name of the PBF file. Defaults to Bristol.
            data_dir (str): Relative directory to store data.
        """
        # Ensure we construct absolute paths for safety
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.data_dir = os.path.join(base_dir, data_dir)
        self.file_path = os.path.join(self.data_dir, pbf_filename)
        
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        # File Integrity Check
        if os.path.exists(self.file_path):
            if os.path.getsize(self.file_path) < 1024 * 1024:  # < 1MB
                print(f"[OSMDataLoader] Local PBF is too small (<1MB). Deleting corrupt file: {self.file_path}")
                os.remove(self.file_path)

        if not os.path.exists(self.file_path):
            error_msg = (
                f"\n[OSMDataLoader] CRITICAL: Local PBF file not found at: {self.file_path}\n"
                f"Automated downloads are blocked by Geofabrik.\n"
                f"PLEASE MANUALLY DOWNLOAD THE REGION PBF (e.g., Bristol or England) FROM:\n"
                f"https://download.geofabrik.de/europe/great-britain/england.html\n"
                f"And place it in: {self.data_dir}\n"
            )
            print(error_msg)
            raise FileNotFoundError(error_msg)
        else:
            print(f"[OSMDataLoader] Found valid local PBF: {self.file_path}")

    def load_graph(self, bbox=None):
        """
        Parses the PBF and returns a NetworkX graph with specific walking attributes.

        Args:
            bbox (list, optional): [min_lon, min_lat, max_lon, max_lat] bounding box to filter.
                                   Note: Pyrosm uses [minx, miny, maxx, maxy].

        Returns:
            networkx.MultiDiGraph: The loaded graph.
        """
        print("[OSMDataLoader] Parsing PBF data... (This uses pyrosm for speed)")
        
        try:
            # Initialize Pyrosm
            osm = OSM(self.file_path, bounding_box=bbox)
            
            # Custom filter for Weighted Sum Model
            extra_attributes = [
                'surface', 'lit', 'incline', 'smoothness', 'footway', 'sac_scale', 'amenity', 'shop'
            ]
            
            # Force retrieval of nodes and edges as GDFs first, then convert.
            # This seems more robust given the version ambiguity.
            print("[OSMDataLoader] Fetching network data...")
            try:
                # We request nodes=True to ensure we get all data, but this might return a tuple
                nodes, edges = osm.get_network(
                    network_type="walking",
                    extra_attributes=extra_attributes,
                    nodes=True
                )
            except ValueError:
                # If unpacking fails (e.g. returns just graph or something else)
                result = osm.get_network(
                    network_type="walking",
                    extra_attributes=extra_attributes,
                    nodes=True
                )
                if isinstance(result, tuple) and len(result) == 2:
                    nodes, edges = result
                elif hasattr(result, "nodes"):
                    # It's a graph already
                    print(f"[OSMDataLoader] Graph loaded directly: {len(result.nodes)} nodes.")
                    return result
                else:
                     raise ValueError(f"Unexpected return type from pyrosm: {type(result)}")

            # Convert to Graph
            print(f"[OSMDataLoader] Converting to NetworkX graph... (Nodes: {len(nodes)}, Edges: {len(edges)})")
            # Use instance method to_graph
            if hasattr(osm, "to_graph"):
                graph = osm.to_graph(nodes, edges, graph_type="networkx", network_type="walking")
            else:
                raise ImportError("OSM.to_graph method not found.")
            
            print(f"[OSMDataLoader] Graph loaded: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
            return graph
            
        except Exception as e:
            print(f"[OSMDataLoader] Error parsing PBF: {e}")
            raise
