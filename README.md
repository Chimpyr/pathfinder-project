# PathFinder MVP Setup Guide

## Prerequisites
-   **Python 3.9+** (Tested with Python 3.13)
-   **pip** (Python Package Installer)
-   **Internet Connection** (Required to download map data on first run)

## Installation

1.  **Clone or Download** this repository.
2.  **Open a Terminal** in the project folder.
3.  **Install Dependencies**:
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
*Note: The first time you run with a new city, it will take a moment to download the map data.*

### Customizing Colors
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
-   **"No module named..."**: Ensure you ran `pip install -r requirements.txt`.
-   **Graph loading takes too long**: This depends on your internet speed and the size of the city. Bristol takes ~10-30s. Larger cities like London will take longer.
