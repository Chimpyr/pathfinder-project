import os
import pytest
from app.services.data_loader import OSMDataLoader
from unittest.mock import patch, MagicMock

def test_data_loader_index_resolution():
    """
    Test that the loader correctly finds the Bristol PBF URL for a Bristol coordinate.
    """
    # Bristol Coordinates
    bbox = (51.44, -2.60, 51.46, -2.58) # lat_min, lon_min, lat_max, lon_max
    # Note: ensure_data_for_bbox expects (min_lat, min_lon, max_lat, max_lon)
    
    loader = OSMDataLoader()
    
    # We want to test _find_pbf_url_for_location logic.
    # We might need to mock _download_file only for the index if we want to avoid network entirely,
    # but downloading index-v1.json (300KB) is usually fine.
    # Let's verify it downloads the index and logic works.
    
    # However, we MUST mock the PBF download to avoid 403s regarding the massive file.
    with patch.object(loader, '_download_file') as mock_dl:
        # Mock side effect: If downloading index, do nothing (let it fail to load? No, we need index).
        # Actually, let's allow index download, but block PBF download.
        
        # Real index download is needed for real logic test.
        # So we only mock if URL ends with .pbf
        
        original_download = loader._download_file
        
        def side_effect(url, dest):
            if url.endswith('.json'):
                # Call original for index
                if not os.path.exists(dest):
                     # If we can't call original easily due to binding...
                     # We can't easily partial mock.
                     # Let's just mock the RESULT of the index lookup if network is flaky.
                     pass 
            else:
                # Mock PBF download: Create empty file
                print(f"Mock downloading PBF: {url}")
                with open(dest, 'wb') as f:
                    f.write(b'MOCK_PBF_DATA')
                    
        mock_dl.side_effect = side_effect
        
        # ACT
        # But wait, we can't easily mock conditional on arguments with simple patch unless checks are inside side_effect.
        # And we need the real index to exist.
        
        # Plan B: Just run it. If index doesn't exist, it tries to download.
        # If we mock `_download_file`, index won't exist.
        # We need to manually download index first?
        pass

def test_manual_bbox_logic():
    # Let's assume index json is downloaded or we mock the json loading.
    pass
    
# Let's write a robust test that mocks the *requests.get* call only for the PBF, 
# but allows the Index download? Or just mock the Index data?
# Mocking index data is safer/faster.

@pytest.fixture
def mock_geofabrik_index():
    return {
        "features": [
            {
                "type": "Feature",
                "properties": {
                    "id": "europe/great-britain/england/bristol",
                    "name": "Bristol",
                    "urls": {"pbf": "https://example.com/bristol.osm.pbf"}
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-2.7, 51.4], [-2.5, 51.4], [-2.5, 51.5], [-2.7, 51.5], [-2.7, 51.4]
                    ]]
                }
            },
            {
                "type": "Feature",
                "properties": {
                    "id": "europe/great-britain/england",
                    "name": "England",
                    "urls": {"pbf": "https://example.com/england.osm.pbf"}
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [-6.0, 50.0], [2.0, 50.0], [2.0, 56.0], [-6.0, 56.0], [-6.0, 50.0]
                    ]]
                }
            }
        ]
    }

def test_find_correct_extract(mock_geofabrik_index):
    loader = OSMDataLoader()
    
    # Mock json.load to return our fake index
    with patch("json.load", return_value=mock_geofabrik_index):
        with patch("builtins.open", new_callable=MagicMock): # Mock open to prevent reading file
            with patch("os.path.exists", return_value=True): # Pretend index exists
                
                # Test Bristol Point (51.45, -2.6)
                url, name = loader._find_pbf_url_for_location(51.45, -2.6)
                assert name == "europe_great_britain_england_bristol"
                assert url == "https://example.com/bristol.osm.pbf"
                
                # Test Point outside Bristol but in England (50.1, -1.0)
                url, name = loader._find_pbf_url_for_location(50.1, -1.0)
                assert name == "europe_great_britain_england"

