import os

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    DEFAULT_CITY = "Bristol, UK"
    DEBUG = True
    VERBOSE_LOGGING = True
    WALKING_SPEED_KMH = 5.0
    
    # Greenness visibility processing mode
    # Options: 'OFF', 'FAST', 'EDGE_SAMPLING', 'NOVACK'
    # - OFF: Skip greenness processing entirely (fastest startup)
    # - FAST: Point buffer at edge midpoint (quick, ~30 seconds)
    # - EDGE_SAMPLING: Multi-point sampling along edge (balanced, ~60 seconds)
    # - NOVACK: Full isovist ray-casting (accurate but slow, ~10+ minutes)
    GREENNESS_MODE = 'EDGE_SAMPLING'
    
    # Elevation processing mode
    # Options: 'OFF', 'API', 'LOCAL'
    # - OFF: Skip elevation processing (no gradient data)
    # - API: Fetch from Open Topo Data API (no download, slower ~30-60s)
    # - LOCAL: Download Copernicus GLO-30 tiles for fast local lookup (~1-3s)
    ELEVATION_MODE = 'LOCAL'
    
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
    
    # Normalisation mode for scenic cost attributes
    # Options: 'STATIC', 'DYNAMIC'
    # - STATIC: Uses raw values directly (0-1 attrs kept as-is, only slope normalised)
    # - DYNAMIC: Rescales all attributes per-map (best edge = 0, worst = 1)
    NORMALISATION_MODE = 'DYNAMIC'
    
    # Cost function algorithm for scenic routing
    # Options: 'WSM_ADDITIVE', 'HYBRID_DISJUNCTIVE'
    # - WSM_ADDITIVE: Pure Weighted Sum Model (AND semantics)
    #       All criteria are summed. Being bad at ANY criterion adds penalty.
    #       Simple but causes multi-criteria collapse (must be good at ALL).
    # - HYBRID_DISJUNCTIVE: Weighted-MIN (OR semantics)
    #       Only best scenic criterion contributes. Good at ANY = rewarded.
    #       Prevents multi-criteria collapse, respects weight priority.
    # See ADR-001, ADR-003 for detailed rationale.
    COST_FUNCTION = 'HYBRID_DISJUNCTIVE'
    
    # Graph caching configuration
    # Maximum number of region graphs to keep in memory (LRU eviction)
    # Higher = more memory usage, fewer reloads for multi-region routing
    MAX_CACHED_REGIONS = 3
    
    # WSM (Weighted Sum Model) default feature weights
    # Used when API request does not include custom weights
    # Higher value = stronger preference for that scenic feature
    # Distance weight controls balance between shortest path and scenic features
    WSM_DEFAULT_WEIGHTS = {
        'distance': 0.5,    # Physical distance component
        'greenness': 0.15,  # Prefer greener routes
        'water': 0.1,       # Prefer routes near water features
        'quietness': 0.1,   # Prefer quieter routes (low traffic noise)
        'social': 0.1,      # Prefer routes near tourist/social POIs
        'slope': 0.05,      # Prefer gentler gradients
    }
