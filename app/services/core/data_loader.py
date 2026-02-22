import os
import requests
import json
from tqdm import tqdm
import pandas as pd
from pyrosm import OSM
from shapely.geometry import shape, Point

from app.services.core.walking_filter import (
    apply_walking_filter,
    EXTRA_WALKING_ATTRIBUTES,
)

try:
    from flask import current_app, has_app_context
except ImportError:
    # For CLI usage, there is no Flask app context, so we mock these
    current_app = None
    def has_app_context(): return False

class OSMDataLoader:
    """
    Handles the robust downloading and parsing of local OSM PBF files.
    Uses Geofabrik Index for file discovery.
    """
    
    INDEX_URL = "https://download.geofabrik.de/index-v1.json"
    INDEX_FILE = "geofabrik_index.json"
    
    # PBFs larger than this will be pre-extracted using osmium to avoid OOM
    # pyrosm loads the full PBF into memory before clipping, so large files
    # (like england.osm.pbf at 1.5GB) will exceed container memory limits
    MAX_PYROSM_PBF_SIZE = 100 * 1024 * 1024  # 100MB

    def log(self, message):
        """
        Logs a message if VERBOSE_LOGGING is enabled in Flask config, 
        or if force_verbose is set (for testing).
        ALWAYS logs critical info? No, user asked for verbose logging for these features.
        We will print if verbose OR if it's a critical error/status.
        Actually, let's just print if verbose, and print criticals always.
        """
        should_log = False
        if has_app_context():
            if current_app.config.get('VERBOSE_LOGGING') or current_app.config.get('DEBUG'):
                should_log = True
        else:
            # Default to verbose in CLI/Test mode? Or quiet?
            # Let's default to True for now as CLI usage usually implies debugging.
            should_log = True

        if should_log:
            print(message)


    def __init__(self, data_dir: str = "app/data"):
        """
        Initialise the loader.
        
        Args:
            data_dir (str): Relative directory to store data.
        """
        # Navigate from app/services/core/ up to project root (4 levels)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.data_dir = os.path.join(base_dir, data_dir)
        
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
            
        self.file_path = None # Will be set dynamically by ensure_data_for_bbox
        self._active_pbf_path = None  # Tracks the PBF used for last load_graph (may be osmium-extracted)
    
    def _extract_bbox_with_osmium(self, source_pbf: str, clip_bbox: tuple, output_pbf: str) -> bool:
        """
        Use osmium-tool to extract a bbox region from a large PBF file.
        
        This is memory-efficient because osmium streams the data rather than
        loading it all into memory like pyrosm does.
        
        Args:
            source_pbf: Path to the large source PBF file
            clip_bbox: (min_lat, min_lon, max_lat, max_lon) to extract
            output_pbf: Path for the extracted output PBF
            
        Returns:
            True if extraction succeeded, False otherwise
        """
        import subprocess
        
        # osmium extract uses format: left,bottom,right,top (min_lon,min_lat,max_lon,max_lat)
        bbox_str = f"{clip_bbox[1]},{clip_bbox[0]},{clip_bbox[3]},{clip_bbox[2]}"
        
        cmd = [
            "osmium", "extract",
            "-b", bbox_str,
            source_pbf,
            "-o", output_pbf,
            "--overwrite"  # Allow overwriting if file exists
        ]
        
        self.log(f"[OSMDataLoader] Running osmium extract: {' '.join(cmd)}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                self.log(f"[OSMDataLoader] Osmium extraction complete: {output_pbf}")
                return True
            else:
                self.log(f"[OSMDataLoader] Osmium extraction failed: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            self.log("[OSMDataLoader] Osmium extraction timed out after 5 minutes")
            return False
        except FileNotFoundError:
            self.log("[OSMDataLoader] osmium-tool not installed, cannot extract bbox")
            return False
        except Exception as e:
            self.log(f"[OSMDataLoader] Osmium extraction error: {e}")
            return False

    def ensure_data_for_bbox(self, bbox: tuple):
        """
        Ensures the correct PBF file for the given bbox is available.
        Resolves the location to a Geofabrik extract and downloads it if missing.

        Args:
            bbox (tuple): (min_lat, min_lon, max_lat, max_lon)
        """
        if not bbox:
            # Default to Bristol if no bbox provided
             self.log("[OSMDataLoader] No BBox provided, defaulting to Bristol.")
             self.file_path = os.path.join(self.data_dir, "bristol-260106.osm.pbf")
             return

        # Find the smallest extract that covers the ENTIRE bbox (not just the centre)
        # This prevents tiles whose centre falls in one region from using the wrong PBF
        pbf_url, name = self._find_pbf_url_for_bbox(bbox)
        
        if not pbf_url:
            self.log("[OSMDataLoader] Could not find a specific extract, defaulting to England fallback.")
            pbf_url = "https://download.geofabrik.de/europe/great-britain/england-latest.osm.pbf"
            name = "england-latest"

        # 2. Determine local filename
        filename = f"{name}.osm.pbf"
        self.file_path = os.path.join(self.data_dir, filename)
        
        # 3. Check and Download
        if not os.path.exists(self.file_path) or os.path.getsize(self.file_path) < 1024 * 1024:
             if os.path.exists(self.file_path):
                 print(f"[OSMDataLoader] File too small/corrupt, removing: {self.file_path}")
                 os.remove(self.file_path)
                 
             self.log(f"[OSMDataLoader] Need data for {name}. Downloading from {pbf_url}...")
             self._download_file(pbf_url, self.file_path)
        else:
             self.log(f"[OSMDataLoader] Using existing valid PBF: {self.file_path}")

    def load_graph(self, bbox=None, clip_bbox=None):
        """
        Parses the PBF and returns a NetworkX graph with specific walking attributes.
        
        Args:
            bbox: Bounding box for data lookup (determines which PBF file to use)
            clip_bbox: Optional bounding box to clip the graph to (min_lat, min_lon, max_lat, max_lon).
                       If provided, only nodes/edges within this bbox are loaded, dramatically
                       reducing memory usage (e.g., 1.1M nodes -> ~50K for a typical route).
        """
        if not self.file_path:
            # If ensure_data_for_bbox wasn't called manually, try to infer or error
             self.log("[OSMDataLoader] File path not set. Calling ensure_data_for_bbox...")
             self.ensure_data_for_bbox(bbox)
             
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"PBF file not found: {self.file_path}")

        # Check if PBF is too large for pyrosm to handle directly
        # pyrosm loads the entire PBF into memory before clipping, so large files
        # will cause OOM. We use osmium to pre-extract the bbox region instead.
        pbf_size = os.path.getsize(self.file_path)
        actual_pbf_path = self.file_path
        temp_extracted_pbf = None
        
        if pbf_size > self.MAX_PYROSM_PBF_SIZE and clip_bbox:
            self.log(f"[OSMDataLoader] PBF is {pbf_size / (1024*1024):.1f}MB (> {self.MAX_PYROSM_PBF_SIZE / (1024*1024):.0f}MB limit)")
            self.log("[OSMDataLoader] Using osmium to pre-extract bbox region to avoid OOM...")
            
            # Create a temporary output path for the extracted PBF
            # Include bbox in filename to allow caching of extracted regions
            bbox_id = f"{clip_bbox[0]:.2f}_{clip_bbox[1]:.2f}_{clip_bbox[2]:.2f}_{clip_bbox[3]:.2f}"
            extracted_filename = f"extracted_{bbox_id}.osm.pbf"
            temp_extracted_pbf = os.path.join(self.data_dir, extracted_filename)
            
            # Check if we already have this extracted region cached
            if os.path.exists(temp_extracted_pbf) and os.path.getsize(temp_extracted_pbf) > 1024:
                self.log(f"[OSMDataLoader] Using cached extracted PBF: {temp_extracted_pbf}")
                actual_pbf_path = temp_extracted_pbf
            else:
                # Run osmium extraction
                if self._extract_bbox_with_osmium(self.file_path, clip_bbox, temp_extracted_pbf):
                    actual_pbf_path = temp_extracted_pbf
                else:
                    # Fallback: try pyrosm anyway and hope for the best
                    self.log("[OSMDataLoader] Osmium failed, attempting pyrosm direct load (may OOM)...")
        
        # Store the active PBF path for feature extraction methods to use
        self._active_pbf_path = actual_pbf_path
        
        self.log(f"[OSMDataLoader] Parsing PBF data: {actual_pbf_path} (This uses pyrosm for speed)")
        
        try:
            # Initialise Pyrosm - optionally clip to bbox for memory efficiency
            # If we pre-extracted with osmium, the PBF is already small so pyrosm bounding_box
            # is less critical but still useful for exact clipping
            if clip_bbox:
                # Convert from (min_lat, min_lon, max_lat, max_lon) to pyrosm format [min_lon, min_lat, max_lon, max_lat]
                bounding_box = [clip_bbox[1], clip_bbox[0], clip_bbox[3], clip_bbox[2]]
                self.log(f"[OSMDataLoader] Clipping to bbox: {clip_bbox}")
                osm = OSM(actual_pbf_path, bounding_box=bounding_box)
            else:
                osm = OSM(actual_pbf_path)
            
            # Custom filter for Weighted Sum Model
            # We request extra OSM tags so they appear as edge columns.
            # EXTRA_WALKING_ATTRIBUTES adds tags needed by the custom filter
            # (e.g. 'designation') that pyrosm would not include by default.
            extra_attributes = list(dict.fromkeys(
                ['surface', 'lit', 'incline', 'smoothness', 'footway',
                 'sac_scale', 'amenity', 'shop']
                + EXTRA_WALKING_ATTRIBUTES
            ))
            
            # Fetch ALL highway ways then apply our own walking filter.
            # This replaces pyrosm's built-in walking filter which
            # hard-excludes highway=cycleway even when foot=designated.
            # See walking_filter.py and ADR-010 §2a for details.
            self.log("[OSMDataLoader] Fetching road network (all highway types)...")
            try:
                # We request nodes=True to ensure we get all data.
                # Logic to handle tuple/graph return types from Pyrosm
                # TODO: Currently walking is the only network type supported, in the future accept cycling and running (consider these as separate networks)
                result = osm.get_network(
                    network_type="all",
                    extra_attributes=extra_attributes,
                    nodes=True
                )
                
                nodes = None
                edges = None
                graph = None
                
                if isinstance(result, tuple) and len(result) == 2:
                    nodes, edges = result
                elif hasattr(result, "nodes"):
                    graph = result
                else:
                    # Retry without nodes=True if it failed weirdly?
                     raise ValueError(f"Unexpected return type: {type(result)}")
                     
            except Exception:
                 # Retry fallback logic
                 # ...
                 raise

            # Apply our custom walking filter to the raw edges
            # Pass nodes so barrier resolution (locked gates) can work
            if graph is None and nodes is not None and edges is not None:
                pre_filter = len(edges)
                edges = apply_walking_filter(edges, nodes=nodes)
                self.log(
                    f"[OSMDataLoader] Walking filter: {pre_filter} → {len(edges)} edges "
                    f"(removed {pre_filter - len(edges)})"
                )

            # Convert to Graph if we got nodes/edges
            if graph is None and nodes is not None and edges is not None:
                self.log(f"[OSMDataLoader] Converting to NetworkX graph... (Nodes: {len(nodes)}, Edges: {len(edges)})")
                if hasattr(osm, "to_graph"):
                    graph = osm.to_graph(nodes, edges, graph_type="networkx", network_type="walking")
                else:
                    raise ImportError("OSM.to_graph method not found.")
            
            # Final validation
            if graph and hasattr(graph, "nodes"):
                self.log(f"[OSMDataLoader] Graph loaded: {len(graph.nodes)} nodes, {len(graph.edges)} edges.")
                
                # Extract and attach additional features
                print("[OSMDataLoader] Extracting additional features (POIs, Greenery, Water)...")
                features_gdf = self._extract_features(osm)
                graph.features = features_gdf
                
                return graph
            else:
                raise ValueError("Failed to load a valid graph object.")
            
        except Exception as e:
            print(f"[OSMDataLoader] Error parsing PBF: {e}")
            raise

    def _extract_features(self, osm):
        """
        Extracts POIs, Green Spaces, and Water in a Single Pass for performance.
        Returns a combined GeoDataFrame.
        """
        self.log("[OSMDataLoader] Extracting additional features (Single Pass Optimisation)...")
        
        # Define combined filter for all features we want
        # This forces pyrosm to read the file once and grab everything matching these tags.
        custom_filter = {
            'amenity': True, 
            'shop': True, 
            'tourism': True,
            'landuse': ['grass', 'forest', 'recreation_ground', 'village_green', 'allotments', 'meadow', 'reservoir', 'basin'],
            'natural': ['wood', 'scrub', 'heath', 'moor', 'water', 'wetland'],
            'leisure': ['park', 'garden', 'playground', 'nature_reserve', 'common'],
            'waterway': ['river', 'canal', 'stream', 'riverbank', 'drain', 'ditch']
        }
        
        try:
            # Single pass read
            gdf = osm.get_data_by_custom_criteria(custom_filter=custom_filter)
            
            if gdf is None or gdf.empty:
                self.log("  [Warn] No features found.")
                return pd.DataFrame()

            # Initialise feature_group
            gdf['feature_group'] = 'other'

            # --- Categorisation Logic ---
            
            # 1. POIs
            # Any non-null value in these columns counts as a POI
            poi_cols = [c for c in ['amenity', 'shop', 'tourism'] if c in gdf.columns]
            if poi_cols:
                # If any of these columns are not null, it's a POI
                # We use a mask
                mask = gdf[poi_cols].notna().any(axis=1)
                gdf.loc[mask, 'feature_group'] = 'poi'

            # 2. Green Spaces
            green_landuse = ['grass', 'forest', 'recreation_ground', 'village_green', 'allotments', 'meadow']
            green_natural = ['wood', 'scrub', 'heath', 'moor']
            green_leisure = ['park', 'garden', 'playground', 'nature_reserve', 'common']
            
            if 'landuse' in gdf.columns:
                gdf.loc[gdf['landuse'].isin(green_landuse), 'feature_group'] = 'green'
            if 'natural' in gdf.columns:
                gdf.loc[gdf['natural'].isin(green_natural), 'feature_group'] = 'green'
            if 'leisure' in gdf.columns:
                gdf.loc[gdf['leisure'].isin(green_leisure), 'feature_group'] = 'green'

            # 3. Water
            water_natural = ['water', 'wetland']
            water_landuse = ['reservoir', 'basin'] 
            
            if 'natural' in gdf.columns:
                gdf.loc[gdf['natural'].isin(water_natural), 'feature_group'] = 'water'
            if 'landuse' in gdf.columns:
                gdf.loc[gdf['landuse'].isin(water_landuse), 'feature_group'] = 'water'
            if 'waterway' in gdf.columns:
                # Anything with a waterway tag is water
                gdf.loc[gdf['waterway'].notna(), 'feature_group'] = 'water'

            # Cleanup
            # Drop geometry nulls
            gdf = gdf[gdf.geometry.notna()]
            
            self.log(f"  > Total extracted features: {len(gdf)}")
            return gdf

        except Exception as e:
            self.log(f"  [Error] Feature extraction failed: {e}")
            return pd.DataFrame()

    def extract_green_areas(self) -> 'gpd.GeoDataFrame':
        """
        Extract green space polygons for visibility analysis.
        
        Tags extracted:
        - landuse: grass, forest, meadow, recreation_ground, village_green, allotments
        - leisure: park, garden, playground, nature_reserve, common
        - natural: wood, scrub, heath, moor
        
        Returns:
            GeoDataFrame of green polygons projected to EPSG:32630 (metres).
        """
        import geopandas as gpd
        
        # Use the active PBF path if set (may be osmium-extracted), otherwise fall back to file_path
        pbf_path = self._active_pbf_path or self.file_path
        
        if not pbf_path or not os.path.exists(pbf_path):
            self.log("[OSMDataLoader] Cannot extract green areas - PBF not loaded.")
            return gpd.GeoDataFrame()
        
        self.log(f"[OSMDataLoader] Extracting green areas from: {os.path.basename(pbf_path)}")
        
        try:
            osm = OSM(pbf_path)
            
            custom_filter = {
                'landuse': ['grass', 'forest', 'meadow', 'recreation_ground', 
                           'village_green', 'allotments'],
                'leisure': ['park', 'garden', 'playground', 'nature_reserve', 'common'],
                'natural': ['wood', 'scrub', 'heath', 'moor']
            }
            
            gdf = osm.get_data_by_custom_criteria(custom_filter=custom_filter)
            
            if gdf is None or gdf.empty:
                self.log("  [Warn] No green areas found.")
                return gpd.GeoDataFrame()
            
            # Filter for polygons only (exclude points/lines)
            gdf = gdf[gdf.geometry.notna()]
            gdf = gdf[gdf.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])]
            
            # Project to metres (UTM zone 30N for Bristol/UK)
            if gdf.crs is None:
                gdf = gdf.set_crs('EPSG:4326')
            gdf = gdf.to_crs('EPSG:32630')
            
            self.log(f"  > Extracted {len(gdf)} green area polygons.")
            return gdf
            
        except Exception as e:
            self.log(f"  [Error] Green area extraction failed: {e}")
            return gpd.GeoDataFrame()

    def extract_buildings(self) -> 'gpd.GeoDataFrame':
        """
        Extract building polygons for visibility occlusion.
        
        Tags extracted:
        - building: any value (True matches all)
        - barrier: wall (solid barriers that block visibility)
        
        Returns:
            GeoDataFrame of building polygons projected to EPSG:32630 (metres).
        """
        import geopandas as gpd
        
        # Use the active PBF path if set (may be osmium-extracted), otherwise fall back to file_path
        pbf_path = self._active_pbf_path or self.file_path
        
        if not pbf_path or not os.path.exists(pbf_path):
            self.log("[OSMDataLoader] Cannot extract buildings - PBF not loaded.")
            return gpd.GeoDataFrame()
        
        self.log(f"[OSMDataLoader] Extracting buildings from: {os.path.basename(pbf_path)}")
        
        try:
            osm = OSM(pbf_path)
            
            # Get buildings - pyrosm has a dedicated method for this
            gdf = osm.get_buildings()
            
            if gdf is None or gdf.empty:
                self.log("  [Warn] No buildings found.")
                return gpd.GeoDataFrame()
            
            # Filter for polygons only
            gdf = gdf[gdf.geometry.notna()]
            gdf = gdf[gdf.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])]
            
            # Project to metres (UTM zone 30N for Bristol/UK)
            if gdf.crs is None:
                gdf = gdf.set_crs('EPSG:4326')
            gdf = gdf.to_crs('EPSG:32630')
            
            self.log(f"  > Extracted {len(gdf)} building polygons.")
            return gdf
            
        except Exception as e:
            self.log(f"  [Error] Building extraction failed: {e}")
            return gpd.GeoDataFrame()

    def extract_water(self) -> 'gpd.GeoDataFrame':
        """
        Extract water feature polygons for scenic scoring.
        
        Tags extracted:
        - natural: water, wetland
        - landuse: reservoir, basin
        - waterway: river, canal, riverbank, stream
        
        LineString geometries (rivers, canals) are buffered to create proximity
        areas, as OSM maps rivers as lines rather than polygons.
        
        Returns:
            GeoDataFrame of water polygons projected to EPSG:32630 (metres).
        """
        import geopandas as gpd
        
        # Buffer width for river/canal LineStrings (in metres after projection)
        RIVER_BUFFER_METRES = 10
        
        # Use the active PBF path if set (may be osmium-extracted), otherwise fall back to file_path
        pbf_path = self._active_pbf_path or self.file_path
        
        if not pbf_path or not os.path.exists(pbf_path):
            self.log("[OSMDataLoader] Cannot extract water - PBF not loaded.")
            return gpd.GeoDataFrame()
        
        self.log(f"[OSMDataLoader] Extracting water features from: {os.path.basename(pbf_path)}")
        
        try:
            osm = OSM(pbf_path)
            
            custom_filter = {
                'natural': ['water', 'wetland'],
                'landuse': ['reservoir', 'basin'],
                'waterway': ['river', 'canal', 'riverbank', 'stream']
            }
            
            gdf = osm.get_data_by_custom_criteria(custom_filter=custom_filter)
            
            if gdf is None or gdf.empty:
                self.log("  [Warn] No water features found.")
                return gpd.GeoDataFrame()
            
            # Keep all geometries (not just polygons)
            gdf = gdf[gdf.geometry.notna()]
            
            # Project to metres before buffering
            if gdf.crs is None:
                gdf = gdf.set_crs('EPSG:4326')
            gdf = gdf.to_crs('EPSG:32630')
            
            # Buffer LineString geometries to create proximity areas
            # Rivers in OSM are mapped as lines, not polygons, so we need to
            # convert them to buffered polygons for spatial intersection
            line_types = ['LineString', 'MultiLineString']
            line_mask = gdf.geometry.geom_type.isin(line_types)
            line_count = line_mask.sum()
            
            if line_count > 0:
                gdf.loc[line_mask, 'geometry'] = gdf.loc[line_mask, 'geometry'].buffer(RIVER_BUFFER_METRES)
                self.log(f"  > Buffered {line_count} river/canal lines by {RIVER_BUFFER_METRES}m")
            
            # Count polygon features
            polygon_count = len(gdf) - line_count
            self.log(f"  > Extracted {len(gdf)} water features ({polygon_count} polygons, {line_count} buffered lines).")
            return gdf
            
        except Exception as e:
            self.log(f"  [Error] Water extraction failed: {e}")
            return gpd.GeoDataFrame()

    def extract_pois(self) -> 'gpd.GeoDataFrame':
        """
        Extract tourist and social POI features for social scoring.
        
        Tags extracted:
        - tourism: attraction, viewpoint, museum, artwork, gallery, information
        - historic: castle, monument, memorial, ruins, archaeological_site
        - amenity: cafe, restaurant, pub, theatre, cinema
        
        Returns:
            GeoDataFrame of POI points/polygons projected to EPSG:32630 (metres).
        """
        import geopandas as gpd
        
        # Use the active PBF path if set (may be osmium-extracted), otherwise fall back to file_path
        pbf_path = self._active_pbf_path or self.file_path
        
        if not pbf_path or not os.path.exists(pbf_path):
            self.log("[OSMDataLoader] Cannot extract POIs - PBF not loaded.")
            return gpd.GeoDataFrame()
        
        self.log(f"[OSMDataLoader] Extracting POIs from: {os.path.basename(pbf_path)}")
        
        try:
            osm = OSM(pbf_path)
            
            custom_filter = {
                'tourism': ['attraction', 'viewpoint', 'museum', 'artwork', 
                           'gallery', 'information', 'picnic_site', 'zoo', 'theme_park'],
                'historic': ['castle', 'monument', 'memorial', 'ruins', 
                            'archaeological_site', 'church', 'manor', 'fort'],
                'amenity': ['cafe', 'restaurant', 'pub', 'bar', 'theatre', 
                           'cinema', 'arts_centre', 'library']
            }
            
            gdf = osm.get_data_by_custom_criteria(custom_filter=custom_filter)
            
            if gdf is None or gdf.empty:
                self.log("  [Warn] No POIs found.")
                return gpd.GeoDataFrame()
            
            # Keep all geometry types (points, polygons) for POIs
            gdf = gdf[gdf.geometry.notna()]
            
            # Project to metres
            if gdf.crs is None:
                gdf = gdf.set_crs('EPSG:4326')
            gdf = gdf.to_crs('EPSG:32630')
            
            self.log(f"  > Extracted {len(gdf)} POI features.")
            return gdf
            
        except Exception as e:
            self.log(f"  [Error] POI extraction failed: {e}")
            return gpd.GeoDataFrame()

    def _load_geofabrik_index(self):
        """Load and cache the Geofabrik index data."""
        index_path = os.path.join(self.data_dir, self.INDEX_FILE)
        
        if not os.path.exists(index_path):
            self.log("[OSMDataLoader] Downloading Geofabrik Index...")
            self._download_file(self.INDEX_URL, index_path)
            
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[OSMDataLoader] Error reading index {e}, re-downloading...")
            if os.path.exists(index_path):
                os.remove(index_path)
            self._download_file(self.INDEX_URL, index_path)
            with open(index_path, 'r', encoding='utf-8') as f:
                return json.load(f)

    def _find_pbf_url_for_location(self, lat, lon):
        """
        Downloads/Loads Geofabrik Index and finds the smallest polygon containing the point.
        """
        data = self._load_geofabrik_index()
        
        point = Point(lon, lat)
        best_match = None
        best_area = float('inf')
        
        # Iterate features
        for feature in data['features']:
            props = feature['properties']
            if 'pbf' not in props.get('urls', {}):
                continue
                
            try:
                geom = shape(feature['geometry'])
                if geom.contains(point):
                    # Found a match. Is it smaller?
                    # Area calculation on lat/lon is approximate but sufficient for hierarchy
                    area = geom.area 
                    if area < best_area:
                        best_area = area
                        best_match = feature
            except Exception:
                continue

        if best_match:
            url = best_match['properties']['urls']['pbf']
            # Clean name for filename usage
            raw_id = best_match['properties']['id']
            name = raw_id.replace('/', '_').replace('-', '_') # e.g. europe/great-britain/england -> europe_great_britain_england
            # Use just the basename for cleaner files if unique enough? 
            # ideally keep hierarchy to avoid conflicts, but full path is safe.
            self.log(f"[OSMDataLoader] Identified best extract: {best_match['properties']['name']} ({name})")
            return url, name
            
        return None, None

    def _find_pbf_url_for_bbox(self, bbox):
        """
        Find the smallest Geofabrik extract whose polygon fully contains the
        entire bounding box (all 4 corners), not just the centre point.
        
        This prevents the bug where a large tile's centre falls in one region
        (e.g. Somerset) while the actual route points are in another (e.g. Bristol).
        
        Falls back to _find_pbf_url_for_location (centre-point) if no single
        extract covers the full bbox.
        
        Args:
            bbox: (min_lat, min_lon, max_lat, max_lon)
        
        Returns:
            Tuple of (pbf_url, region_name) or (None, None).
        """
        from shapely.geometry import box as shapely_box
        
        data = self._load_geofabrik_index()
        
        # Build a Shapely box from the bbox (note: shapely_box takes minx,miny,maxx,maxy = lon,lat order)
        query_box = shapely_box(bbox[1], bbox[0], bbox[3], bbox[2])
        
        best_match = None
        best_area = float('inf')
        
        for feature in data['features']:
            props = feature['properties']
            if 'pbf' not in props.get('urls', {}):
                continue
            try:
                geom = shape(feature['geometry'])
                if geom.contains(query_box):
                    area = geom.area
                    if area < best_area:
                        best_area = area
                        best_match = feature
            except Exception:
                continue
        
        if best_match:
            url = best_match['properties']['urls']['pbf']
            raw_id = best_match['properties']['id']
            name = raw_id.replace('/', '_').replace('-', '_')
            self.log(f"[OSMDataLoader] Identified best extract (bbox-cover): {best_match['properties']['name']} ({name})")
            return url, name
        
        # Fallback: no single extract covers the full bbox → use centre point
        lat = (bbox[0] + bbox[2]) / 2
        lon = (bbox[1] + bbox[3]) / 2
        self.log(f"[OSMDataLoader] No extract covers full bbox, falling back to centre-point lookup")
        return self._find_pbf_url_for_location(lat, lon)
        
    def _download_file(self, url: str, dest_path: str):
        """
        Streams a download with a progress bar. 
        Polite: Uses PathFinderProject/1.0 User-Agent.
        """
        self.log(f"[OSMDataLoader] Downloading from {url}...")
        try:
            # Polite & Honest User-Agent
            headers = {
                'User-Agent': 'PathFinderProject/1.0 (contact@example.com)' 
            }
            response = requests.get(url, stream=True, timeout=60, headers=headers)
            
            if response.status_code == 403 or response.status_code == 404:
                error_msg = (
                    f"\n[OSMDataLoader] ERROR: Automated download failed (Status {response.status_code}).\n"
                    f"Geofabrik might have blocked this request or file is missing.\n"
                    f"PLEASE MANUALLY DOWNLOAD: {url}\n"
                    f"AND SAVE TO: {dest_path}\n"
                )
                print(error_msg)
                raise PermissionError(error_msg)
                
            response.raise_for_status()
            
            total_size_in_bytes = int(response.headers.get('content-length', 0))
            block_size = 1024 
            
            with open(dest_path, 'wb') as file, tqdm(
                desc=os.path.basename(dest_path),
                total=total_size_in_bytes,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
            ) as bar:
                for data in response.iter_content(block_size):
                    size = file.write(data)
                    bar.update(size)
            
            print(f"[OSMDataLoader] Download complete: {dest_path}")
        except Exception as e:
            print(f"[OSMDataLoader] Error downloading file: {e}")
            if os.path.exists(dest_path):
                os.remove(dest_path) 
            raise
