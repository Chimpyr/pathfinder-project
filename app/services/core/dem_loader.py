"""
DEM Data Loader Module

Manages downloading and caching of Copernicus GLO-30 Digital Elevation Model tiles.
Provides fast local elevation lookups using rasterio for GeoTIFF reading.

The Copernicus GLO-30 dataset offers ~4m vertical RMSE accuracy globally,
making it the most accurate freely available 30m DEM.

Data Source: AWS Open Data Registry (no API key required)
https://registry.opendata.aws/copernicus-dem/
"""

import os
import math
from typing import Dict, List, Optional, Tuple
import requests
from tqdm import tqdm

try:
    import rasterio
    from rasterio.io import MemoryFile
    RASTERIO_AVAILABLE = True
except ImportError:
    rasterio = None
    MemoryFile = None
    RASTERIO_AVAILABLE = False

try:
    from flask import current_app, has_app_context
except ImportError:
    current_app = None
    def has_app_context(): 
        return False


# AWS S3 configuration for Copernicus GLO-30 (no API key required)
# Bucket: s3://copernicus-dem-30m (publicly accessible)
AWS_S3_BUCKET_URL = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"

# Minimum valid tile size (bytes) - reject corrupt/empty downloads
MIN_TILE_SIZE = 1024 * 100  # 100KB minimum


class DEMDataLoader:
    """
    Manages Copernicus GLO-30 DEM tile downloading and elevation lookups.
    
    Follows the same caching pattern as OSMDataLoader: tiles are downloaded
    once and stored locally for fast subsequent lookups.
    
    Performance optimisation: Tiles are loaded into memory for batch lookups,
    reducing I/O overhead when processing thousands of graph nodes.
    """
    
    def __init__(self, data_dir: str = "app/data/dem"):
        """
        Initialise the DEM loader.
        
        Args:
            data_dir: Relative directory to store DEM tiles.
        """
        # Navigate from app/services/core/ up to project root
        base_dir = os.path.dirname(
            os.path.dirname(
                os.path.dirname(
                    os.path.dirname(os.path.abspath(__file__))
                )
            )
        )
        self.data_dir = os.path.join(base_dir, data_dir)
        
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)
        
        # In-memory tile cache for batch operations
        self._tile_cache: Dict[str, 'rasterio.DatasetReader'] = {}
        self._tile_data_cache: Dict[str, Tuple] = {}  # tile_name -> (data, transform)
    
    def _log(self, message: str) -> None:
        """Log message if verbose logging is enabled."""
        should_log = False
        if has_app_context():
            if current_app.config.get('VERBOSE_LOGGING') or current_app.config.get('DEBUG'):
                should_log = True
        else:
            should_log = True
        
        if should_log:
            print(message)
    
    def _get_tile_name(self, lat: float, lon: float) -> str:
        """
        Determine the tile filename for a given coordinate.
        
        Copernicus GLO-30 tiles are named using the south-west corner:
        - Latitude: N/S prefix + degrees (e.g., N51, S12)
        - Longitude: E/W prefix + degrees (e.g., W003, E010)
        
        Args:
            lat: Latitude in decimal degrees.
            lon: Longitude in decimal degrees.
            
        Returns:
            Tile filename without extension (e.g., "Copernicus_DSM_COG_10_N51_00_W003_00_DEM").
        """
        # Calculate tile bounds (south-west corner)
        lat_floor = int(math.floor(lat))
        lon_floor = int(math.floor(lon))
        
        # Format latitude component
        if lat_floor >= 0:
            lat_str = f"N{abs(lat_floor):02d}_00"
        else:
            lat_str = f"S{abs(lat_floor):02d}_00"
        
        # Format longitude component
        if lon_floor >= 0:
            lon_str = f"E{abs(lon_floor):03d}_00"
        else:
            lon_str = f"W{abs(lon_floor):03d}_00"
        
        return f"Copernicus_DSM_COG_10_{lat_str}_{lon_str}_DEM"
    
    def _get_tile_path(self, tile_name: str) -> str:
        """Get the full filesystem path for a tile."""
        return os.path.join(self.data_dir, f"{tile_name}.tif")
    
    def _is_tile_valid(self, tile_path: str) -> bool:
        """Check if a downloaded tile is valid (exists and not corrupt)."""
        if not os.path.exists(tile_path):
            return False
        
        # Check minimum size
        if os.path.getsize(tile_path) < MIN_TILE_SIZE:
            return False
        
        # Optionally verify rasterio can open it
        if RASTERIO_AVAILABLE:
            try:
                with rasterio.open(tile_path) as src:
                    # Quick sanity check
                    if src.width < 10 or src.height < 10:
                        return False
            except Exception:
                return False
        
        return True
    
    def _download_tile(self, tile_name: str) -> bool:
        """
        Download a DEM tile from AWS S3.
        
        Uses the AWS Open Data Registry which hosts Copernicus GLO-30 with
        no authentication required.
        
        Args:
            tile_name: The tile identifier.
            
        Returns:
            True if download successful, False otherwise.
        """
        tile_path = self._get_tile_path(tile_name)
        
        # Check if already valid
        if self._is_tile_valid(tile_path):
            self._log(f"[DEMLoader] Tile already exists: {tile_name}")
            return True
        
        # Remove corrupt file if present
        if os.path.exists(tile_path):
            self._log(f"[DEMLoader] Removing invalid tile: {tile_path}")
            os.remove(tile_path)
        
        # Build AWS S3 URL
        # AWS naming convention: Copernicus_DSM_COG_10_N51_00_W003_00_DEM/
        #                        Copernicus_DSM_COG_10_N51_00_W003_00_DEM.tif
        url = f"{AWS_S3_BUCKET_URL}/{tile_name}/{tile_name}.tif"
        
        self._log(f"[DEMLoader] Downloading tile from AWS S3: {tile_name}")
        self._log(f"[DEMLoader] URL: {url}")
        
        try:
            headers = {
                'User-Agent': 'ScenicPathFinder/1.0 (Academic Research Project)'
            }
            response = requests.get(url, stream=True, timeout=120, headers=headers)
            
            if response.status_code == 403:
                self._log(
                    f"[DEMLoader] ERROR: Access denied for tile {tile_name}.\n"
                    f"This tile may not be publicly available yet."
                )
                return False
            
            if response.status_code == 404:
                self._log(
                    f"[DEMLoader] ERROR: Tile not found: {tile_name}.\n"
                    f"This tile may not exist in the Copernicus dataset."
                )
                return False
            
            if response.status_code != 200:
                self._log(
                    f"[DEMLoader] ERROR: Download failed with status {response.status_code}\n"
                    f"Response: {response.text[:200]}"
                )
                return False
            
            # Stream download with progress bar
            total_size = int(response.headers.get('content-length', 0))
            
            with open(tile_path, 'wb') as f, tqdm(
                desc=f"Downloading {tile_name}",
                total=total_size,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
            ) as bar:
                for chunk in response.iter_content(chunk_size=8192):
                    size = f.write(chunk)
                    bar.update(size)
            
            # Verify download
            if not self._is_tile_valid(tile_path):
                self._log(f"[DEMLoader] ERROR: Downloaded tile is invalid: {tile_path}")
                if os.path.exists(tile_path):
                    os.remove(tile_path)
                return False
            
            self._log(f"[DEMLoader] Successfully downloaded: {tile_name}")
            return True
            
        except requests.exceptions.Timeout:
            self._log(f"[DEMLoader] ERROR: Download timed out for {tile_name}")
            return False
        except Exception as e:
            self._log(f"[DEMLoader] ERROR: Download failed: {e}")
            if os.path.exists(tile_path):
                os.remove(tile_path)
            return False
    
    def ensure_tiles_for_bbox(self, bbox: Tuple[float, float, float, float]) -> List[str]:
        """
        Ensure all required tiles for a bounding box are downloaded.
        
        Args:
            bbox: (min_lat, min_lon, max_lat, max_lon)
            
        Returns:
            List of available tile names.
        """
        min_lat, min_lon, max_lat, max_lon = bbox
        
        # Calculate required tiles
        required_tiles = set()
        
        lat = math.floor(min_lat)
        while lat <= max_lat:
            lon = math.floor(min_lon)
            while lon <= max_lon:
                tile_name = self._get_tile_name(lat + 0.5, lon + 0.5)
                required_tiles.add(tile_name)
                lon += 1
            lat += 1
        
        self._log(f"[DEMLoader] Bounding box requires {len(required_tiles)} tile(s)")
        
        available = []
        for tile_name in required_tiles:
            if self._download_tile(tile_name):
                available.append(tile_name)
            else:
                self._log(f"[DEMLoader] WARNING: Could not obtain tile {tile_name}")
        
        return available
    
    def _load_tile_to_memory(self, tile_name: str) -> bool:
        """
        Load a tile's data into memory for fast batch lookups.
        
        Args:
            tile_name: The tile identifier.
            
        Returns:
            True if loaded successfully.
        """
        if tile_name in self._tile_data_cache:
            return True
        
        tile_path = self._get_tile_path(tile_name)
        
        if not self._is_tile_valid(tile_path):
            return False
        
        try:
            with rasterio.open(tile_path) as src:
                # Read entire band into memory
                data = src.read(1)
                transform = src.transform
                self._tile_data_cache[tile_name] = (data, transform)
            return True
        except Exception as e:
            self._log(f"[DEMLoader] ERROR loading tile {tile_name}: {e}")
            return False
    
    def get_elevation(self, lat: float, lon: float) -> Optional[float]:
        """
        Get elevation for a single coordinate.
        
        Args:
            lat: Latitude in decimal degrees.
            lon: Longitude in decimal degrees.
            
        Returns:
            Elevation in metres, or None if unavailable.
        """
        if not RASTERIO_AVAILABLE:
            self._log("[DEMLoader] WARNING: rasterio not available")
            return None
        
        tile_name = self._get_tile_name(lat, lon)
        tile_path = self._get_tile_path(tile_name)
        
        # Ensure tile is downloaded
        if not self._is_tile_valid(tile_path):
            if not self._download_tile(tile_name):
                return None
        
        # Load to memory cache if not already
        if not self._load_tile_to_memory(tile_name):
            return None
        
        data, transform = self._tile_data_cache[tile_name]
        
        try:
            # Convert geographic coordinates to pixel indices
            row, col = rasterio.transform.rowcol(transform, lon, lat)
            
            # Check bounds
            if 0 <= row < data.shape[0] and 0 <= col < data.shape[1]:
                elevation = float(data[row, col])
                
                # Handle nodata values (typically -9999 or similar)
                if elevation < -1000:
                    return None
                
                return elevation
            else:
                return None
                
        except Exception as e:
            self._log(f"[DEMLoader] ERROR reading elevation: {e}")
            return None
    
    def get_elevations_batch(
        self, 
        coords: List[Tuple[float, float]]
    ) -> Dict[Tuple[float, float], Optional[float]]:
        """
        Get elevations for multiple coordinates efficiently.
        
        Loads required tiles into memory and performs batch lookups,
        significantly faster than individual coordinate queries.
        
        Args:
            coords: List of (lat, lon) tuples.
            
        Returns:
            Dictionary mapping (lat, lon) -> elevation (or None).
        """
        if not RASTERIO_AVAILABLE:
            self._log("[DEMLoader] WARNING: rasterio not available")
            return {coord: None for coord in coords}
        
        results = {}
        
        # Group coordinates by tile
        tiles_needed: Dict[str, List[Tuple[float, float]]] = {}
        
        for lat, lon in coords:
            tile_name = self._get_tile_name(lat, lon)
            if tile_name not in tiles_needed:
                tiles_needed[tile_name] = []
            tiles_needed[tile_name].append((lat, lon))
        
        self._log(f"[DEMLoader] Batch lookup: {len(coords)} coords across {len(tiles_needed)} tile(s)")
        
        # Process each tile
        for tile_name, tile_coords in tiles_needed.items():
            # Ensure tile is available and loaded
            tile_path = self._get_tile_path(tile_name)
            
            if not self._is_tile_valid(tile_path):
                if not self._download_tile(tile_name):
                    # Mark all coords in this tile as unavailable
                    for coord in tile_coords:
                        results[coord] = None
                    continue
            
            if not self._load_tile_to_memory(tile_name):
                for coord in tile_coords:
                    results[coord] = None
                continue
            
            data, transform = self._tile_data_cache[tile_name]
            
            # Batch process coordinates for this tile
            for lat, lon in tile_coords:
                try:
                    row, col = rasterio.transform.rowcol(transform, lon, lat)
                    
                    if 0 <= row < data.shape[0] and 0 <= col < data.shape[1]:
                        elevation = float(data[row, col])
                        
                        # Handle nodata
                        if elevation < -1000:
                            results[(lat, lon)] = None
                        else:
                            results[(lat, lon)] = elevation
                    else:
                        results[(lat, lon)] = None
                        
                except Exception:
                    results[(lat, lon)] = None
        
        successful = sum(1 for v in results.values() if v is not None)
        self._log(f"[DEMLoader] Retrieved {successful}/{len(coords)} elevations")
        
        return results
    
    def clear_memory_cache(self) -> None:
        """Clear the in-memory tile cache to free memory."""
        self._tile_data_cache.clear()
        self._tile_cache.clear()
