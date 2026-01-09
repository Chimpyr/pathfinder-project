import os

class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY')
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
