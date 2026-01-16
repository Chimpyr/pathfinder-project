"""
Greenness Processor Base Class

Defines the abstract interface that all greenness processing strategies must implement.
This enables the Strategy Pattern for swapping algorithms at runtime via configuration.

Attributes added to graph edges by all processors:
    - raw_green_cost: float (0.0 = very green, 1.0 = no green)
"""

from abc import ABC, abstractmethod
from typing import Optional
import networkx as nx
import geopandas as gpd


class GreennessProcessor(ABC):
    """
    Abstract base class for greenness calculation strategies.
    
    All greenness processors must implement the `process` method which takes
    a graph and green area GeoDataFrame, then adds 'raw_green_cost' attribute
    to each edge (0.0 = very green, 1.0 = no green).
    
    Subclasses should also implement the `name` property for logging purposes.
    
    Example:
        >>> class MyProcessor(GreennessProcessor):
        ...     @property
        ...     def name(self) -> str:
        ...         return "My Custom Processor"
        ...     
        ...     def process(self, graph, green_gdf, **kwargs):
        ...         # Add raw_green_cost to edges
        ...         return graph
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Human-readable name of the processor for logging.
        
        Returns:
            str: Descriptive name (e.g., "Fast Buffer", "Edge Sampling").
        """
        pass
    
    @abstractmethod
    def process(
        self,
        graph: nx.MultiDiGraph,
        green_gdf: Optional[gpd.GeoDataFrame],
        **kwargs
    ) -> nx.MultiDiGraph:
        """
        Process the graph and add greenness scores to edges.
        
        This method must add the 'raw_green_cost' attribute to every edge
        in the graph. The value should be between 0.0 (very green) and
        1.0 (no green), suitable for use as a routing cost.
        
        Args:
            graph: NetworkX MultiDiGraph with node coordinates (x, y attributes).
            green_gdf: GeoDataFrame of green area polygons. May be None or empty.
            **kwargs: Strategy-specific arguments (e.g., buildings for NOVACK).
        
        Returns:
            The same graph with 'raw_green_cost' attribute added to edges.
        
        Raises:
            ValueError: If graph is None or invalid.
        """
        pass
    
    def validate_graph(self, graph: nx.MultiDiGraph) -> None:
        """
        Validate that the graph is suitable for processing.
        
        Args:
            graph: Graph to validate.
        
        Raises:
            ValueError: If graph is None or has no edges.
        """
        if graph is None:
            raise ValueError("Graph cannot be None")
        
        if len(graph.edges) == 0:
            raise ValueError("Graph has no edges to process")
    
    def log_distribution(self, graph: nx.MultiDiGraph) -> None:
        """
        Log the distribution of green costs for debugging.
        
        Prints min, max, mean, and percentage of edges with good green scores.
        
        Args:
            graph: Graph with 'raw_green_cost' attributes.
        """
        costs = [
            data.get('raw_green_cost', 1.0)
            for u, v, k, data in graph.edges(keys=True, data=True)
        ]
        
        if not costs:
            print(f"  > [{self.name}] No edges to analyse")
            return
        
        mean_cost = sum(costs) / len(costs)
        green_edges = sum(1 for c in costs if c < 0.5)
        
        print(f"  > [{self.name}] Distribution: "
              f"min={min(costs):.3f}, max={max(costs):.3f}, mean={mean_cost:.3f}")
        print(f"  > [{self.name}] Edges with green cost < 0.5: "
              f"{green_edges}/{len(costs)} ({100*green_edges/len(costs):.1f}%)")
