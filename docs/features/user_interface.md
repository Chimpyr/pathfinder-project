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
- Supports both single-route and multi-route responses, depending on backend mode and selected preferences.

### Round Trip (Loop)

- Generates a circular walking route returning to the originating **Start** point.
- **Distance Targeting**: The user selects a desired loop distance (e.g., 5km), and the pathfinding engine attempts to create a route of exactly that length.
- Utilizes the `loop_solvers` backend architecture to ensure route novelty and minimize backtracking.

---

## 3. Advanced Options

"Advanced Options" is a collapsible section available in both Standard and Round Trip routing modes. It exposes specific practical or safety-focused preferences that are independent of purely "scenic" (nature-based) routing.

- **Prefer paths/trails**: Increases the weight/bias towards off-road or dedicated pedestrian paths.
- **Prefer paved surfaces**: Penalizes unpaved (dirt, mud, grass) edges, useful for accessibility or specific footwear. Managed dynamically via original OSM attributes.
- **Prefer lit streets**: Penalizes unlit streets, designed for nighttime walking safety. Managed from in-memory graph edge lighting (`lit`), including council-promoted edges when council streetlight data is available.
- **Heavily avoid unlit streets**: Strong safety-first mode that heavily penalizes unlit or unknown-lighting segments.
- **Avoid unsafe roads**: Strongly penalizes roads deemed hostile to pedestrians (e.g., fast roads lacking adequate pavements).

### How Advanced Options Are Applied

- Advanced options are now independent from Scenic Preferences.
- If Scenic Preferences are **enabled**, advanced options are applied on top of the user's scenic weights.
- If Scenic Preferences are **disabled** but any advanced option is enabled, the frontend requests an **advanced compare** response with:
  - **Baseline** route: shortest path with all advanced modifiers off.
  - **Advanced** route: distance-dominant WSM route with enabled advanced modifiers.
- This ensures advanced toggles are never silently ignored.

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

---

## 5. Route Explainability

The results panel route cards now include backend-provided context metadata:

- **Subtitle** (for example: `Shortest route`, `Custom mix`, `Advanced options`).
- **Modifier list** showing which advanced toggles were active for that route.

This makes it explicit why one route differs from another, especially in compare mode.
