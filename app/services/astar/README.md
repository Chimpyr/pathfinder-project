# Custom A* Service Documentation

## Overview
This service provides a custom A* pathfinding implementation integrated with OpenStreetMap (OSM) data via NetworkX. It replaces the standard `networkx.shortest_path` function to demonstrate a custom algorithm implementation.

## Integration
The integration is achieved through an adapter class `OSMNetworkXAStar` located in `app/services/astar/astar.py`. This class inherits from the generic `AStar` class provided by the `python-astar` library (located in `app/services/astar/astar_lib`).

### Adapter Structure
The `OSMNetworkXAStar` adapter bridges the gap between the generic A* library and the NetworkX graph structure used by OSMnx:

- **Inheritance**: `class OSMNetworkXAStar(AStar)`
- **Initialisation**: Accepts a `networkx.MultiDiGraph` instance.
- **Neighbors**: Maps `self.graph.neighbors(node)` to the A* `neighbors` method.
- **Distance**: Extracts the `length` attribute from graph edges to determine the cost between nodes.
- **Heuristic**: Implements the Haversine formula to calculate the great-circle distance between nodes using their latitude (`y`) and longitude (`x`) coordinates.

## Mechanism
### A* Algorithm    
The A* algorithm finds the shortest path by maintaining a priority queue of paths to explore. It uses:
- **g(n)**: The cost from the start node to node *n*.
- **h(n)**: The estimated cost from node *n* to the goal (heuristic).
- **f(n) = g(n) + h(n)**: The total estimated cost of the path through node *n*.

The algorithm prioritises nodes with the lowest *f(n)*.

### Heuristic Function
We use the **Haversine distance** as the heuristic. This calculates the "as-the-crow-flies" distance between two points on a sphere (Earth). This is an *admissible* heuristic because the straight-line distance is never greater than the actual road distance, ensuring the algorithm finds the optimal path.

## Usage
To use the service in the application:

```python
from app.services.astar.astar import OSMNetworkXAStar

# Initialise with a graph
astar_solver = OSMNetworkXAStar(graph)

# Find path between two node IDs
# Returns a generator of node IDs
route_generator = astar_solver.astar(start_node, end_node)

if route_generator:
    route = list(route_generator)
else:
    print("No route found")
```

## Maintenance
### Updating the Library
The core A* logic is contained in `app/services/astar/astar_lib`. If you need to update the generic algorithm:
1. Modify the files in `app/services/astar/astar_lib`.
2. Ensure the `AStar` class interface remains compatible with the adapter.

### Modifying the Adapter
If the graph structure changes (e.g., different edge attributes):
1. Update `OSMNetworkXAStar.distance_between` in `app/services/astar/astar.py` to access the correct weight attribute.
2. Update `OSMNetworkXAStar.heuristic_cost_estimate` if node coordinate attributes change.

