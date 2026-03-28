import os

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'you-will-never-guess'
    DEFAULT_CITY = "Bristol, UK"
    DEBUG = True
    VERBOSE_LOGGING = True
    DEFAULT_DISTANCE_UNIT = 'km'
    DEFAULT_WALKING_SPEED_KMH = 5.0
    DEFAULT_RUNNING_EASY_SPEED_KMH = 9.5
    DEFAULT_RUNNING_RACE_SPEED_KMH = 12.5

    # Backward-compatible walking speed alias used by legacy code paths.
    WALKING_SPEED_KMH = DEFAULT_WALKING_SPEED_KMH

    ACTIVITY_PARAMS = {
        'walking': {
            'max_speed': 6.0,
            'flat_speed': 5.0,
            'decay_rate': 3.5,
            'optimal_grade': -0.05
        },
        'running': {
            'max_speed': 15.0,
            'flat_speed': 12.0,
            'decay_rate': 2.5,
            'optimal_grade': -0.10
        }
    }
    
    # =========================================================================
    # User Database Configuration (PostgreSQL)
    # =========================================================================
    _PG_USER = os.environ.get('POSTGRES_USER', 'scenic')
    _PG_PASS = os.environ.get('POSTGRES_PASSWORD', 'scenicpassword')
    _PG_HOST = os.environ.get('POSTGRES_DB_HOST', 'localhost')
    _PG_PORT = os.environ.get('POSTGRES_DB_PORT', '5432')
    _USER_DB = os.environ.get('USER_DB_NAME', 'user_db')

    SQLALCHEMY_DATABASE_URI = (
        f"postgresql://{_PG_USER}:{_PG_PASS}@{_PG_HOST}:{_PG_PORT}/{_USER_DB}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Connection pool tuning — conservative to stay below PostgreSQL max_connections
    # API (1 worker) + Celery (4 workers) = 5 processes × pool_size 3 = 15 conns max
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 3,
        'max_overflow': 2,
        'pool_pre_ping': True,  # Detect stale connections
    }
    
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
    COST_FUNCTION = 'WSM_ADDITIVE'
    
    # Graph caching configuration
    # Maximum number of region graphs to keep in memory (LRU eviction)
    # Higher = more memory usage, fewer reloads for multi-region routing
    MAX_CACHED_REGIONS = 3
    
    # Maximum number of tile graphs to keep in memory (LRU eviction)
    # 16 x 7.5km tiles ≈ 4 x 15km tiles in memory usage (~1.5GB)
    MAX_CACHED_TILES = 16
    
    # =========================================================================
    # Tile-Based Graph Caching (ADR-007)
    # =========================================================================
    # Routes are cached using a snap-to-grid tile system. This improves cache
    # reuse by ensuring nearby routes share the same tiles instead of creating
    # unique cache entries for each route's bounding box.
    
    # Size of each tile in kilometres
    # 30km covers most of greater Bristol area in 1-2 tiles for typical routes
    # Larger tiles = better cache reuse, fewer cross-boundary routes
    # Trade-off: longer initial build time (~3-4 min per tile)
    TILE_SIZE_KM = 15
    
    # Overlap between adjacent tiles in kilometres
    # Ensures boundary edges connect properly when merging tiles
    TILE_OVERLAP_KM = 2
    
    # List of tile IDs to pre-build on application startup (optional)
    # Format: ["lat_lon", ...] e.g., ["51.45_-2.55", "51.45_-2.70"]
    # Leave empty to disable pre-warming
    PREWARM_TILES = []
    
    # WSM (Weighted Sum Model) default feature weights
    # Used when API request does not include custom weights
    # Higher value = stronger preference for that scenic feature
    # Distance weight controls balance between shortest path and scenic features
    WSM_DEFAULT_WEIGHTS = {
        'distance': 1,    # Physical distance component
        'greenness': 0.0,  # Prefer greener routes
        'water': 0.,       # Prefer routes near water features
        'quietness': 0.,   # Prefer quieter routes (low traffic noise)
        'social': 0.,      # Prefer routes near tourist/social POIs
        'slope': 0.0,      # Prefer gentler gradients
    }
    
    # =========================================================================
    # Loop Routing Configuration
    # =========================================================================
    
    # Loop solver algorithm selection (plug-and-play)
    # Options: 'BUDGET_ASTAR', 'GEOMETRIC', 'TREE_SEARCH', 'RANDOM_WALK'
    # - BUDGET_ASTAR: State-augmented A* with budget heuristic
    # - GEOMETRIC: Triangle-plateau skeleton + WSM A* legs (recommended)
    # - TREE_SEARCH: Full-path tree search (single run, many routes)
    # - RANDOM_WALK: Legacy two-phase random walk + A* return (deprecated)
    LOOP_SOLVER_ALGORITHM = 'GEOMETRIC'
    
    # Number of loop candidates to return (like multi-route mode)
    # Geometric solver can efficiently generate 5-10 diverse routes
    # Higher values provide more variety but increase computation time
    LOOP_NUM_CANDIDATES = 7
    
    # Loop distance tolerance (±%)
    # Routes within this tolerance are considered successful
    LOOP_DISTANCE_TOLERANCE = 0.3  # ±30%
    
    # Minimum viable loop distance in metres (reject tiny loops)
    LOOP_MIN_DISTANCE = 1000  # 1km minimum
    
    # Loop candidate selection strategy
    # Options: 'DIVERSE' (maximise route difference), 'TOP_K' (best K by score)
    LOOP_CANDIDATE_STRATEGY = 'DIVERSE'
    
    # Multi-route mode (Distinct Paths strategy)
    # When True: Returns 3 routes per request (Baseline, Extremist, Balanced)
    #   - Baseline: Pure shortest distance (distance=1.0, others=0)
    #   - Extremist: Maximises user's strongest scenic preference
    #   - Balanced: Uses user's actual weight configuration
    # When False: Returns single route using user weights (legacy behaviour)
    # Approximates Pareto frontier without NP-hard evolutionary algorithms.
    MULTI_ROUTE_MODE = True
    
    # =========================================================================
    # Async Pipeline Configuration (Celery + Redis)
# =========================================================================
    
    # Enable async graph building
    # When True: Cache misses enqueue a Celery task and return task_id
    # When False: Cache misses block until graph is built (legacy behaviour)
    ASYNC_MODE = os.environ.get('ASYNC_MODE', 'false').lower() == 'true'
    
    # Redis connection URLs for Celery
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/1')
    
    # Task lock timeout (seconds) - prevents duplicate tasks for same region
    TASK_LOCK_TIMEOUT = int(os.environ.get('TASK_LOCK_TIMEOUT', '900'))  # 15 minutes



