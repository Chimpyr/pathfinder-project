import os

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    DEFAULT_CITY = "Bristol, UK"
    DEBUG = True
    VERBOSE_LOGGING = True
    WALKING_SPEED_KMH = 5.0
    
    # Greenness visibility processing mode
    # Options: 'OFF', 'FAST', 'NOVACK'
    # - OFF: Skip greenness processing entirely (fastest startup)
    # - FAST: Simple buffer intersection (quick, ~30 seconds)
    # - NOVACK: Full isovist ray-casting (accurate but slow, ~10+ minutes)
    GREENNESS_MODE = 'FAST'
    
    # Elevation processing mode
    # Options: 'OFF', 'FAST'
    # - OFF: Skip elevation processing (no gradient data)
    # - FAST: Fetch from Open Topo Data API (~30-60s for large graphs)
    ELEVATION_MODE = 'OFF'
    
    # Water proximity processing mode
    # Options: 'OFF', 'FAST'
    # - OFF: Skip water processing (no water proximity data)
    # - FAST: Buffer intersection for water features
    WATER_MODE = 'FAST'
    
    # Social/POI proximity processing mode
    # Options: 'OFF', 'FAST'
    # - OFF: Skip social processing (no POI proximity data)
    # - FAST: Buffer intersection for tourist/social POIs
    SOCIAL_MODE = 'FAST'
    
    # Graph caching configuration
    # Maximum number of region graphs to keep in memory (LRU eviction)
    # Higher = more memory usage, fewer reloads for multi-region routing
    MAX_CACHED_REGIONS = 3

