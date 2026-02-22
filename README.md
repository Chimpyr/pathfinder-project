# PathFinder MVP Setup Guide

## Features
- **Multi-criteria A* Routing**: Optimise walks for Greenness, Water proximity, Quietness, and Social POIs.
- **Round Trip (Loop) Generation**: Create circular routes of target distances returning to your start point.
- **Advanced Navigation Options**: Toggle preferences for lit streets (ideal for night), paved surfaces, and paths/trails.
- **Nav Rail Interface**: Clean, collapsible vertical sidebar organising routing, settings, and an admin debug panel.
- **Map Overlays**: Visualise OSM data like street lighting on top of customizable map appearances (CartoDB Light/Dark, Voyager).

## Prerequisites

- **Python 3.9+** (Tested with Python 3.13)
- **pip** (Python Package Installer)
- **Internet Connection** (Required to download map data on first run)

## Installation

1.  **Clone or Download** this repository.
2.  **Open a Terminal** in the project folder.
3.  **Install Dependencies**:
    `bash
    pip install -r requirements.txt
    `
    **Mac/pyenv:**
4.  **pyenv set version:**

```bash
    pyenv local 3.13.7
```

2. **Install to local version:**

```bash
    pip install -r requirements.txt
```

## How to Run

### Windows (Recommended)

Double-click the **`start.bat`** file in the project folder.

### Manual Run

Run the following command in your terminal:

```bash
python run.py
```

Then open your browser to: [http://127.0.0.1:5000](http://127.0.0.1:5000)

## Configuration

### Changing the City

To change the default city (currently "Bristol, UK"), edit `config.py`:

```python
class Config:
    DEFAULT_CITY = "London, UK" # Example change
```

_Note: The first time you run with a new city, it will take a moment to download the map data._

### Customising Colours

You can easily change the color scheme by editing `app/static/css/style.css`. Look for the variables at the top:

```css
:root {
  --primary-color: #5e9910ff; /* Change this hex code */
  /* ... other variables ... */
}
```

### Debug Options

To enable verbose logging and see debug information in the UI:

1.  Open `config.py`.
2.  Set `VERBOSE_LOGGING = True`.
3.  Restart the application.
4.  A "Debug Info" section will appear in the sidebar after searching for a route.

### Walking Speed

To adjust the estimated walking time:

1.  Open `config.py`.
2.  Edit `WALKING_SPEED_KMH` (default is 5.0 km/h).
3.  Restart the application.

## Troubleshooting

- **"No module named..."**: Ensure you ran `pip install -r requirements.txt`.
- **Graph loading takes too long**: This depends on your internet speed and the size of the city. Bristol takes ~10-30s. Larger cities like London will take longer.

## How Caching Works

The application uses a **two-layer caching system** to improve performance:

1.  **Disk Cache (`cache/` folder)**:

    - Managed by the `osmnx` library.
    - Stores raw map data downloaded from OpenStreetMap.
    - **Benefit**: Prevents re-downloading data from the internet on subsequent runs.
    - **Lifespan**: Permanent (until you delete the folder).

2.  **In-Memory Cache (RAM)**:
    - Managed by the `GraphManager` class.
    - Stores the loaded graph object in your computer's memory.
    - **Benefit**: Provides instant access to the map during your current session.
    - **Lifespan**: Temporary (cleared when you close the application).

**Summary**: The first run downloads from the internet (Slow). Restarting the app loads from disk (Fast). Searching again within the same session uses RAM (Instant).
