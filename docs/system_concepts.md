# System Concepts: How PathFinder Works

This document explains how the PathFinder application turns a user's request into a navigable map, focusing on the data flow and the graph structure.

## 1. The Journey of a Request

### Step 1: User Input
The user provides two strings:
*   **Start**: "Bristol Temple Meads"
*   **End**: "Cabot Circus"

### Step 2: Geocoding
We convert these names into coordinates (Latitude/Longitude) using a geocoder (OSMnx/Nominatim).
*   `Start`: `(51.449, -2.581)`
*   `End`: `(51.458, -2.584)`

### Step 3: Finding the Map (Auto-Discovery)
We need the street network for these points. We don't want to download the whole world.
1.  **Index Lookup**: We look at the `geofabrik_index.json`.
2.  **Polygon Match**: We check which box contains our coordinates.
    *   *Is it in London?* No.
    *   *Is it in Bristol?* **Yes.**
3.  **Download/Cache**: We download `bristol.osm.pbf` (a compressed binary file of all Bristol streets) if we don't have it yet.

### Step 4: Building the Graph
We read the PBF file and convert it into a **Graph**.
*   **Raw Data**: The PBF contains millions of "Nodes" (points) and "Ways" (lines).
*   **Conversion**: We filter for "walking" paths and keep specific tags like `lit`, `surface`, and `incline`.
*   **Result**: A `networkx.MultiDiGraph` object.

---

## 2. The Graph Object Explained

The graph (`G`) is a mathematical structure representing the street network.

### What is it?
It is a **MultiDiGraph**:
*   **Multi**: Two nodes can have multiple edges between them (e.g., a road and a parallel path).
*   **Di** (Directed): Streets have direction (A -> B might be different from B -> A, mostly relevant for one-way streets, though walking is usually bidirectional).

### Components

#### 1. Nodes (Junctions)
Points where streets meet or end.
*   **ID**: A unique number (e.g., `123456789`).
*   **Data**: Dictionary containing coordinates.
    ```python
    # Accessing node data
    node_data = G.nodes[123456789]
    # Result: {'y': 51.449, 'x': -2.581, 'street_count': 3}
    ```

#### 2. Edges (Streets)
Connections between two nodes.
*   **Key**: `(u, v, k)` where `u` is start node, `v` is end node, `k` is the edge key (usually 0).
*   **Data**: The rich attributes we extracted.
    ```python
    # Accessing edge data (from Node A to Node B)
    edge_data = G[123456789][987654321][0]
    
    # Resulting Dictionary:
    {
        'length': 45.2,          # Length in meters
        'highway': 'residential', # Road type
        'name': 'Victoria Street',
        'lit': 'yes',            # <---  custom tag
        'surface': 'asphalt',    # <---  custom tag
        'incline': 'up'          # <---  custom tag
    }
    ```

## 3. How I Use It (The Algorithm)

When the A* algorithm wants to walk from Node A to Node B, it looks at the **Edge Data**:

```python
def calculate_cost(edge_data):
    distance = edge_data['length']
    cost = distance
    
    # Example Logic, very wrong for now:
    if edge_data.get('lit') == 'yes':
        cost *= 0.9  # 10% cheaper (prefer lit roads)
    
    if edge_data.get('surface') == 'gravel':
        cost *= 1.2  # 20% more expensive (harder to walk)
        
    return cost
```

The graph provides the raw data locally so the `RouteFinder` can run this logic millions of times instantly.

---

## 4. Custom Features: Quietness Value

Beyond raw OSM tags, we compute **derived attributes** on edges during graph loading. The first of these is the **quietness value**, based on Wang et al. (2021) research validating road hierarchy as a proxy for traffic noise.

### How It Works

After loading the graph from the PBF file, `GraphManager` runs the `QuietnessProcessor` to classify each edge:

```python
# In graph_manager.py
cls._graph = process_graph_quietness(cls._graph)
```

### Edge Classification

Each edge receives a `noise_factor` attribute based on its `highway` tag:

| Highway Type | Examples | `noise_factor` | Description |
|--------------|----------|----------------|-------------|
| **Noisy** | motorway, primary, secondary | 1.0 | High traffic, loud |
| **Quiet** | residential, footway, path | 2.0 | Low traffic, peaceful |
| **Neutral** | tertiary, unclassified | 1.5 | Unknown/moderate |

### New Edge Attributes

```python
edge_data = G[123456789][987654321][0]

# After QuietnessProcessor:
{
    'length': 45.2,
    'highway': 'residential',
    'noise_factor': 2.0,           # <---  Quietness classification
    # ... other OSM tags
}
```

### Future Use (WSM A*)

A `raw_quiet_cost` attribute (formula: `length / noise_factor`) will be added when the **Weighted Sum Model (WSM)** A* algorithm is implemented. This will allow users to balance route preferences:

- Shortest distance
- Quietest route
- Best-lit route
- Smoothest surface
- etc.

