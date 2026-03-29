"""
Build canonical council streetlight dataset.

This script merges:
- Bristol Streetlights (Shapefile)
- South Gloucestershire Street Lighting (Excel)

into one canonical GeoPackage at:
  app/data/streetlight/combined_streetlights.gpkg

Canonical columns:
- source: source dataset identifier
- lit: lighting status (currently always 'yes')
- lit_tag_type: council metadata origin type
- lighting_regime: all_night | part_night | timed_window | solar | unknown
- lighting_regime_text: raw descriptive source text
- asset_type: source-specific asset category text
- geometry: point geometry in EPSG:4326
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Iterable, Optional

import geopandas as gpd
import pandas as pd


DEFAULT_STREETLIGHT_DIR = Path("app/data/streetlight")
DEFAULT_OUTPUT_PATH = DEFAULT_STREETLIGHT_DIR / "combined_streetlights.gpkg"
DEFAULT_LAYER_NAME = "combined_streetlights"


def _classify_lighting_regime(value: object) -> str:
    """Classify free-text schedule values into normalized lighting regimes."""
    if value is None:
        return "unknown"

    text = str(value).strip()
    if not text:
        return "unknown"

    norm = text.lower()
    if norm in {"n/a", "na", "none", "no current information"}:
        return "unknown"
    if "solar" in norm:
        return "solar"
    if "24 hour" in norm or "24 hours" in norm or "sunset to sunrise" in norm:
        return "all_night"
    if re.search(r"\b\d{3,4}\s*-\s*\d{3,4}\b", norm):
        return "timed_window"
    if "sunset" in norm and ("0500" in norm or "0600" in norm or "0000" in norm or "-" in norm):
        return "part_night"
    if "sunset" in norm:
        return "part_night"
    return "unknown"


def _normalise_name(value: str) -> str:
    """Normalise a column name for fuzzy matching."""
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def _find_column(columns: Iterable[str], candidates: Iterable[str]) -> Optional[str]:
    """Find the first matching column using normalised aliases."""
    normalised = {_normalise_name(col): col for col in columns}
    for candidate in candidates:
        key = _normalise_name(candidate)
        if key in normalised:
            return normalised[key]
    # Fall back to substring matching for verbose source headers
    # (for example root^item_(BNG)_Easting).
    for candidate in candidates:
        key = _normalise_name(candidate)
        for normalised_col, original_col in normalised.items():
            if key and key in normalised_col:
                return original_col
    return None


def _to_numeric(series: pd.Series) -> pd.Series:
    """Coerce a series to numeric values."""
    return pd.to_numeric(series, errors="coerce")


def _south_glos_from_excel(xlsx_path: Path) -> gpd.GeoDataFrame:
    """Load South Gloucestershire lights from Excel into canonical schema."""
    if not xlsx_path.exists():
        raise FileNotFoundError(f"South Gloucestershire file not found: {xlsx_path}")

    try:
        workbook = pd.ExcelFile(xlsx_path)
    except ImportError as exc:
        raise RuntimeError(
            "Reading .xlsx requires openpyxl. Install with: pip install openpyxl"
        ) from exc

    frames: list[gpd.GeoDataFrame] = []

    lat_candidates = ["lat", "latitude", "y", "y_wgs84"]
    lon_candidates = ["lon", "lng", "long", "longitude", "x", "x_wgs84"]
    east_candidates = ["easting", "eastings", "x_coordinate", "xcoord"]
    north_candidates = ["northing", "northings", "y_coordinate", "ycoord"]

    for sheet in workbook.sheet_names:
        df = pd.read_excel(xlsx_path, sheet_name=sheet)
        if df.empty:
            continue

        lat_col = _find_column(df.columns, lat_candidates)
        lon_col = _find_column(df.columns, lon_candidates)
        east_col = _find_column(df.columns, east_candidates)
        north_col = _find_column(df.columns, north_candidates)

        if lat_col and lon_col:
            lat = _to_numeric(df[lat_col])
            lon = _to_numeric(df[lon_col])
            mask = lat.notna() & lon.notna()
            if not mask.any():
                continue
            gdf = gpd.GeoDataFrame(
                df.loc[mask].copy(),
                geometry=gpd.points_from_xy(lon[mask], lat[mask]),
                crs="EPSG:4326",
            )
        elif east_col and north_col:
            east = _to_numeric(df[east_col])
            north = _to_numeric(df[north_col])
            mask = east.notna() & north.notna()
            if not mask.any():
                continue
            gdf = gpd.GeoDataFrame(
                df.loc[mask].copy(),
                geometry=gpd.points_from_xy(east[mask], north[mask]),
                crs="EPSG:27700",
            ).to_crs("EPSG:4326")
        else:
            continue

        time_col = _find_column(df.columns, ["Times", "Operating Times", "Hours"])
        unit_type_col = _find_column(
            df.columns,
            [
                "root_Unit Type_(Unit Types)_Description",
                "Unit Type",
                "Type",
            ],
        )

        canonical = gdf[["geometry"]].copy()
        canonical["source"] = "south_glos"
        canonical["lit"] = "yes"
        canonical["lit_tag_type"] = "council_times"
        if time_col:
            canonical["lighting_regime_text"] = gdf[time_col].astype(str).str.strip()
            canonical["lighting_regime"] = canonical["lighting_regime_text"].map(_classify_lighting_regime)
        else:
            canonical["lighting_regime_text"] = "unknown"
            canonical["lighting_regime"] = "unknown"

        if unit_type_col:
            canonical["asset_type"] = gdf[unit_type_col].astype(str).str.strip()
        else:
            canonical["asset_type"] = "unknown"
        frames.append(canonical)

    if not frames:
        raise ValueError(
            "Could not detect coordinate columns in South Gloucestershire workbook. "
            "Expected lat/lon or easting/northing columns."
        )

    merged = gpd.GeoDataFrame(
        pd.concat(frames, ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )
    return merged


def _bristol_from_shapefile(streetlight_dir: Path) -> gpd.GeoDataFrame:
    """Load Bristol shapefile points into canonical schema."""
    shapefiles = sorted((streetlight_dir / "Bristol Streetlights").glob("*.shp"))
    if not shapefiles:
        raise FileNotFoundError(
            "No Bristol shapefile found in app/data/streetlight/Bristol Streetlights"
        )

    gdf = gpd.read_file(shapefiles[0])
    if gdf.empty:
        raise ValueError(f"Bristol shapefile is empty: {shapefiles[0]}")

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    gdf = gdf.to_crs("EPSG:4326")
    gdf = gdf[gdf.geometry.notna()].copy()

    multipoint_mask = gdf.geometry.geom_type == "MultiPoint"
    if multipoint_mask.any():
        gdf = gdf.explode(index_parts=False).reset_index(drop=True)

    gdf = gdf[gdf.geometry.geom_type == "Point"].copy()

    unit_type_col = _find_column(gdf.columns, ["UNIT_TYPE_", "UNIT TYPE", "TYPE"])
    owner_col = _find_column(gdf.columns, ["OWNER_DESC", "OWNER", "OWNER DESCRIPTION"])

    canonical = gdf[["geometry"]].copy()
    canonical["source"] = "bristol"
    canonical["lit"] = "yes"
    canonical["lit_tag_type"] = "council_unit_type"
    canonical["lighting_regime"] = "unknown"
    if unit_type_col:
        canonical["lighting_regime_text"] = gdf[unit_type_col].astype(str).str.strip()
        canonical["asset_type"] = gdf[unit_type_col].astype(str).str.strip()
    elif owner_col:
        canonical["lighting_regime_text"] = gdf[owner_col].astype(str).str.strip()
        canonical["asset_type"] = gdf[owner_col].astype(str).str.strip()
    else:
        canonical["lighting_regime_text"] = "unknown"
        canonical["asset_type"] = "unknown"

    return canonical


def build_combined_streetlights(
    streetlight_dir: Path = DEFAULT_STREETLIGHT_DIR,
    output_path: Path = DEFAULT_OUTPUT_PATH,
    layer_name: str = DEFAULT_LAYER_NAME,
) -> Path:
    """Build and write the canonical combined streetlight GeoPackage."""
    bristol = _bristol_from_shapefile(streetlight_dir)
    south_glos = _south_glos_from_excel(
        streetlight_dir / "South Gloucestershire Street Lighting.xlsx"
    )

    combined = gpd.GeoDataFrame(
        pd.concat([bristol, south_glos], ignore_index=True),
        geometry="geometry",
        crs="EPSG:4326",
    )

    canonical_order = [
        "source",
        "lit",
        "lit_tag_type",
        "lighting_regime",
        "lighting_regime_text",
        "asset_type",
        "geometry",
    ]
    for col in canonical_order:
        if col not in combined.columns:
            combined[col] = "unknown"
    combined = combined[canonical_order]

    # Remove exact duplicates to keep the output deterministic.
    combined["_wkt"] = combined.geometry.to_wkt()
    combined = combined.drop_duplicates(
        subset=["source", "lit", "_wkt"]
    ).drop(columns=["_wkt"])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()

    combined.to_file(output_path, layer=layer_name, driver="GPKG")

    print(f"[StreetlightBuild] Wrote {len(combined)} points to {output_path}")
    print("[StreetlightBuild] Source counts:")
    for source, count in combined["source"].value_counts().items():
        print(f"  - {source}: {count}")

    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build canonical council streetlights GeoPackage.")
    parser.add_argument(
        "--streetlight-dir",
        type=Path,
        default=DEFAULT_STREETLIGHT_DIR,
        help="Directory containing raw council streetlight inputs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_PATH,
        help="Output GeoPackage path.",
    )
    parser.add_argument(
        "--layer",
        type=str,
        default=DEFAULT_LAYER_NAME,
        help="Output layer name inside GeoPackage.",
    )

    args = parser.parse_args()

    try:
        build_combined_streetlights(
            streetlight_dir=args.streetlight_dir,
            output_path=args.output,
            layer_name=args.layer,
        )
    except Exception as exc:
        print(f"[StreetlightBuild] Error: {exc}")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
