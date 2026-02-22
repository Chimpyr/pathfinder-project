# User Interface & Frontend Features

This document provides a detailed overview of the ScenicPathFinder frontend architecture and features.

---

## 1. Navigation Rail (Nav Rail)

The Navigation Rail is the central hub for accessing different areas of the application. It acts as a collapsible, persistent sidebar on the left side of the screen.

### Sections
- **Toggle Button**: Located at the top, allowing the user to collapse or expand the rail to save screen space when focusing purely on the map.
- **Routes (Map View)**: The primary view where point-to-point and loop routing happens.
- **Admin**: An interface dedicated to system diagnostics, cache management, testing, and viewing debugging information.
- **Settings**: A control panel for global application configurations (e.g., Map Appearance).

---

## 2. Routes Panel (Split Mode)

The main routing panel is divided into two distinct modes via a tabbed interface, simplifying complex scenario generation without cluttering the screen.

### Standard Route (A to B)
- Calculates a route from a specified **Start** location to a **Destination**.
- Takes advantage of all scenic algorithms (Greenness, Water, Quietness, etc.).

### Round Trip (Loop)
- Generates a circular walking route returning to the originating **Start** point.
- **Distance Targeting**: The user selects a desired loop distance (e.g., 5km), and the pathfinding engine attempts to create a route of exactly that length.
- Utilizes the `loop_solvers` backend architecture to ensure route novelty and minimize backtracking.

---

## 3. Advanced Options

"Advanced Options" is a collapsible section available in both Standard and Round Trip routing modes. It exposes specific practical or safety-focused preferences that are independent of purely "scenic" (nature-based) routing.

- **Prefer paths/trails**: Increases the weight/bias towards off-road or dedicated pedestrian paths.
- **Prefer paved surfaces**: Penalizes unpaved (dirt, mud, grass) edges, useful for accessibility or specific footwear. Managed by the backend `SurfaceProcessor`.
- **Prefer lit streets**: Penalizes unlit streets, designed for nighttime walking safety. Managed by the backend `LightingProcessor`.
- **Avoid unsafe roads**: Strongly penalizes roads deemed hostile to pedestrians (e.g., fast roads lacking adequate pavements).

---

## 4. Map Overlays and Appearance

The frontend provides tools to manipulate the visual presentation of the map and analyse map data layer-by-layer.

### Map Appearance (Tile Layers)
Users can select their preferred map visual style directly from the Settings or via the Layers control. Options include:
- Standard OpenStreetMap
- CartoDB Light (clean, muted background ideal for overlays)
- CartoDB Dark (high contrast, night-mode aesthetic)
- Voyager (balanced detail and style)

### Data Overlays
- **Street Lights Overlay**: Toggles a visual heatmap or marker representation of mapped street lighting infrastructure across the active region. Useful for verifying the "Prefer lit streets" data logic or planning night walks manually.
