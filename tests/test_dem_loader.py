"""
Test suite for the DEM Data Loader module.

Tests tile management, elevation lookup, and batch processing.
Uses mocked file I/O to avoid actual network requests in unit tests.
"""

import os
import math
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
import numpy as np


class TestGetTileName:
    """Tests for the _get_tile_name method."""
    
    def test_uk_positive_lat_negative_lon(self):
        """Bristol area: N51, W003."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        tile_name = loader._get_tile_name(51.45, -2.58)
        
        assert "N51" in tile_name
        assert "W003" in tile_name or "W002" in tile_name  # Depends on floor
    
    def test_equator_positive_coords(self):
        """Equatorial location with positive coordinates."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        tile_name = loader._get_tile_name(0.5, 10.5)
        
        assert "N00" in tile_name
        assert "E010" in tile_name
    
    def test_southern_hemisphere(self):
        """Southern hemisphere location."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        tile_name = loader._get_tile_name(-33.9, 18.4)
        
        assert "S34" in tile_name or "S33" in tile_name
        assert "E018" in tile_name
    
    def test_negative_both(self):
        """Both coordinates negative (South America)."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        tile_name = loader._get_tile_name(-12.5, -77.0)
        
        assert "S" in tile_name
        assert "W" in tile_name


class TestTileValidity:
    """Tests for the _is_tile_valid method."""
    
    def test_nonexistent_file_invalid(self):
        """Non-existent file should be invalid."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        result = loader._is_tile_valid("/nonexistent/path/tile.tif")
        
        assert result is False
    
    @patch('os.path.exists')
    @patch('os.path.getsize')
    def test_small_file_invalid(self, mock_size, mock_exists):
        """File smaller than minimum size should be invalid."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        mock_exists.return_value = True
        mock_size.return_value = 1000  # Less than MIN_TILE_SIZE
        
        result = loader._is_tile_valid("/some/path/tile.tif")
        
        assert result is False


class TestEnsureTilesForBbox:
    """Tests for the ensure_tiles_for_bbox method."""
    
    def test_single_tile_bbox(self):
        """Small bounding box should require single tile."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        # Mock the download to always succeed
        with patch.object(loader, '_download_tile', return_value=True) as mock_download:
            # Bristol city centre - fits in one tile
            bbox = (51.44, -2.60, 51.46, -2.58)
            tiles = loader.ensure_tiles_for_bbox(bbox)
            
            assert len(tiles) == 1
            assert mock_download.called
    
    def test_multi_tile_bbox(self):
        """Large bounding box spanning tile boundaries."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        with patch.object(loader, '_download_tile', return_value=True):
            # Spans two longitude degrees
            bbox = (51.0, -3.5, 51.5, -1.5)
            tiles = loader.ensure_tiles_for_bbox(bbox)
            
            # Should require multiple tiles
            assert len(tiles) >= 2


class TestBatchElevationLookup:
    """Tests for the get_elevations_batch method."""
    
    @patch('app.services.core.dem_loader.RASTERIO_AVAILABLE', False)
    def test_returns_none_without_rasterio(self):
        """Should return None values when rasterio unavailable."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        coords = [(51.45, -2.58), (51.46, -2.59)]
        results = loader.get_elevations_batch(coords)
        
        assert all(v is None for v in results.values())
    
    def test_empty_coords_list(self):
        """Empty coordinate list should return empty dict."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        results = loader.get_elevations_batch([])
        
        assert results == {}


class TestSingleElevationLookup:
    """Tests for the get_elevation method."""
    
    @patch('app.services.core.dem_loader.RASTERIO_AVAILABLE', False)
    def test_returns_none_without_rasterio(self):
        """Should return None when rasterio unavailable."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        result = loader.get_elevation(51.45, -2.58)
        
        assert result is None


class TestMemoryCache:
    """Tests for the memory cache functionality."""
    
    def test_clear_cache(self):
        """Cache should be empty after clearing."""
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        # Add dummy data to caches
        loader._tile_data_cache['test'] = ('data', 'transform')
        loader._tile_cache['test'] = MagicMock()
        
        loader.clear_memory_cache()
        
        assert len(loader._tile_data_cache) == 0
        assert len(loader._tile_cache) == 0


class TestDataDirectory:
    """Tests for data directory management."""
    
    @patch('os.path.exists')
    @patch('os.makedirs')
    def test_creates_directory_if_missing(self, mock_makedirs, mock_exists):
        """Should create data directory if it doesn't exist."""
        mock_exists.return_value = False
        
        from app.services.core.dem_loader import DEMDataLoader
        loader = DEMDataLoader()
        
        mock_makedirs.assert_called()
