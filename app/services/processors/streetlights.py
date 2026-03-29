"""
Streetlight Processor Module

Augments graph edge lighting using council streetlight point datasets.

Edge attributes updated:
- lit: set to 'yes' when a nearby council streetlight is matched
- lit_source: set to 'council' for matched edges
- lit_source_detail: source dataset name where available
"""

from typing import List, Optional, Tuple

import networkx as nx
import geopandas as gpd
from pyproj import Transformer
from shapely.geometry import LineString, box
from shapely.strtree import STRtree


# Default point-to-edge snapping radius in metres
SNAP_DISTANCE_METRES: float = 15.0

# Coordinate transformer: WGS84 (lat/lon) to UTM zone 30N (metres)
_transformer: Optional[Transformer] = None


def _get_transformer() -> Transformer:
    """Get or create the coordinate transformer (WGS84 -> EPSG:32630)."""
    global _transformer
    if _transformer is None:
        _transformer = Transformer.from_crs("EPSG:4326", "EPSG:32630", always_xy=True)
    return _transformer


def _transform_coords(lon: float, lat: float) -> Tuple[float, float]:
    """Transform WGS84 coordinates to projected metres."""
    transformer = _get_transformer()
    x, y = transformer.transform(lon, lat)
    return x, y


def _normalise_lit_value(value) -> str:
    """Normalise lit tag values for comparison."""
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return ""
    return str(value).strip().lower()


def _prepare_streetlight_points(
    streetlight_gdf: Optional[gpd.GeoDataFrame],
) -> gpd.GeoDataFrame:
    """Ensure point data is valid and projected in metres (EPSG:32630)."""
    if streetlight_gdf is None or streetlight_gdf.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:32630")

    gdf = streetlight_gdf.copy()

    if gdf.geometry.name != "geometry":
        gdf = gdf.rename_geometry("geometry")

    gdf = gdf[gdf.geometry.notna()].copy()

    multipoint_mask = gdf.geometry.geom_type == "MultiPoint"
    if multipoint_mask.any():
        gdf = gdf.explode(index_parts=False).reset_index(drop=True)

    gdf = gdf[gdf.geometry.geom_type == "Point"].copy()

    if gdf.empty:
        return gpd.GeoDataFrame(geometry=[], crs="EPSG:32630")

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    if str(gdf.crs).upper() != "EPSG:32630":
        gdf = gdf.to_crs("EPSG:32630")

    return gdf


def _build_edge_spatial_index(
    graph: nx.MultiDiGraph,
) -> Tuple[Optional[STRtree], List[LineString], List[Tuple[int, int, int]], Optional[Tuple[float, float, float, float]]]:
    """
    Build a spatial index of graph edges using node coordinates.

    Returns:
        (spatial index, edge geometries, edge refs, bounds)
    """
    edge_geoms: List[LineString] = []
    edge_refs: List[Tuple[int, int, int]] = []

    minx = float("inf")
    miny = float("inf")
    maxx = float("-inf")
    maxy = float("-inf")

    for u, v, key in graph.edges(keys=True):
        try:
            start_lon = graph.nodes[u].get("x")
            start_lat = graph.nodes[u].get("y")
            end_lon = graph.nodes[v].get("x")
            end_lat = graph.nodes[v].get("y")

            if None in (start_lon, start_lat, end_lon, end_lat):
                continue

            start_x, start_y = _transform_coords(float(start_lon), float(start_lat))
            end_x, end_y = _transform_coords(float(end_lon), float(end_lat))

            if start_x == end_x and start_y == end_y:
                continue

            line = LineString([(start_x, start_y), (end_x, end_y)])
            edge_geoms.append(line)
            edge_refs.append((u, v, key))

            bx1, by1, bx2, by2 = line.bounds
            minx = min(minx, bx1)
            miny = min(miny, by1)
            maxx = max(maxx, bx2)
            maxy = max(maxy, by2)

        except Exception:
            continue

    if not edge_geoms:
        return None, [], [], None

    bounds = (minx, miny, maxx, maxy)
    return STRtree(edge_geoms), edge_geoms, edge_refs, bounds


def process_graph_streetlights(
    graph: nx.MultiDiGraph,
    streetlight_gdf: Optional[gpd.GeoDataFrame],
    snap_distance_m: float = SNAP_DISTANCE_METRES,
) -> nx.MultiDiGraph:
    """
    Snap council streetlight points to nearby graph edges.

    Args:
        graph: NetworkX MultiDiGraph with node coordinates in WGS84.
        streetlight_gdf: GeoDataFrame of streetlight points.
        snap_distance_m: Maximum point-to-edge distance for matching in metres.

    Returns:
        Graph with updated edge lighting attributes.
    """
    if graph is None:
        return graph

    points = _prepare_streetlight_points(streetlight_gdf)
    if points.empty:
        print("[StreetlightProcessor] No council streetlights provided, skipping.")
        return graph

    print("[StreetlightProcessor] Building edge spatial index...")
    edge_sindex, edge_geoms, edge_refs, bounds = _build_edge_spatial_index(graph)

    if edge_sindex is None or not edge_geoms:
        print("[StreetlightProcessor] Graph has no spatially indexable edges, skipping.")
        return graph

    if bounds is not None:
        minx, miny, maxx, maxy = bounds
        padded_bounds = box(
            minx - snap_distance_m,
            miny - snap_distance_m,
            maxx + snap_distance_m,
            maxy + snap_distance_m,
        )
        points = points[points.geometry.intersects(padded_bounds)].copy()

    if points.empty:
        print("[StreetlightProcessor] No streetlights intersect graph bounds, skipping.")
        return graph

    matched_points = 0
    promoted_to_lit = 0
    touched_edges = set()

    total_points = len(points)
    report_interval = max(1, total_points // 10)

    print(f"[StreetlightProcessor] Processing {total_points} streetlight points...")

    for idx, row in points.iterrows():
        point = row.geometry
        source = str(row.get("source", "unknown"))

        candidates = edge_sindex.query(point.buffer(snap_distance_m))
        if len(candidates) == 0:
            continue

        nearest_idx = None
        nearest_distance = snap_distance_m

        for edge_idx in candidates:
            distance = point.distance(edge_geoms[edge_idx])
            if distance <= nearest_distance:
                nearest_distance = distance
                nearest_idx = edge_idx

        if nearest_idx is None:
            continue

        u, v, key = edge_refs[int(nearest_idx)]
        edge_data = graph[u][v][key]

        if _normalise_lit_value(edge_data.get("lit")) != "yes":
            promoted_to_lit += 1

        edge_data["lit"] = "yes"
        edge_data["lit_source"] = "council"
        edge_data["lit_source_detail"] = source

        touched_edges.add((u, v, key))
        matched_points += 1

        if (idx + 1) % report_interval == 0:
            pct = ((idx + 1) / total_points) * 100
            print(f"  > Progress: {pct:.0f}% ({idx + 1}/{total_points})")

    print(
        "[StreetlightProcessor] Matched "
        f"{matched_points}/{total_points} points to {len(touched_edges)} edges; "
        f"promoted {promoted_to_lit} edges to lit='yes'."
    )

    return graph
