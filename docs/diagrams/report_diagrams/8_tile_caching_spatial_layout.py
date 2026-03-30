#!/usr/bin/env python3
"""
8. Tile-Based Caching Spatial Layout — Publication-Ready Diagram

Illustrates the 15 km snap-to-grid tile system with 2 km overlap bands.
Shows why two adjacent tiles must both be loaded when a route crosses
a tile boundary.

Source constants (verified from code — do NOT change without checking):
    DEFAULT_TILE_SIZE_KM    = 15   (config.py → tile_utils.py line 14)
    DEFAULT_TILE_OVERLAP_KM = 2    (config.py → tile_utils.py line 15)
    Snap logic: get_tile_id() rounds to nearest 15 km grid centre

Output: docs/report_diagrams/8_tile_caching_spatial_layout.png
"""

import os
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import numpy as np

# ── Constants from code (config.py → tile_utils.py) ─────────────────────
TILE_SIZE_KM = 15
TILE_OVERLAP_KM = 2

# ── Okabe-Ito Colour Palette ────────────────────────────────────────────
OI_ORANGE = "#E69F00"
OI_SKY    = "#56B4E9"
OI_GREEN  = "#009E73"
OI_BLUE   = "#0072B2"
OI_RED    = "#D55E00"
OI_PINK   = "#CC79A7"
OI_YELLOW = "#F0E442"
OI_BLACK  = "#000000"

# Tile colours
COLOR_DEFAULT_FILL = "#F5F5F5"          # Light grey for non-active tiles
COLOR_ACTIVE_FILL  = OI_SKY + "40"      # Translucent sky-blue for active tiles
COLOR_OVERLAP      = OI_ORANGE + "55"   # Translucent orange for overlap bands
COLOR_ROUTE        = OI_RED             # Route polyline
COLOR_GRID         = "#888888"          # Grid edge colour
COLOR_ACTIVE_EDGE  = OI_BLUE            # Active tile edge colour
COLOR_CENTRE       = OI_BLACK           # Tile centre dot


def draw_tile_grid(ax, cols=3, rows=3):
    """Draw a cols×rows tile grid and return centre coordinates."""
    centres = {}
    for r in range(rows):
        for c in range(cols):
            x0 = c * TILE_SIZE_KM
            y0 = r * TILE_SIZE_KM

            # Default tile rectangle
            rect = mpatches.FancyBboxPatch(
                (x0, y0), TILE_SIZE_KM, TILE_SIZE_KM,
                boxstyle="round,pad=0",
                facecolor=COLOR_DEFAULT_FILL,
                edgecolor=COLOR_GRID,
                linewidth=1.0,
                zorder=1,
            )
            ax.add_patch(rect)

            # Tile centre
            cx = x0 + TILE_SIZE_KM / 2
            cy = y0 + TILE_SIZE_KM / 2
            centres[(c, r)] = (cx, cy)

            # Label: illustrative snapped coordinate
            lat_label = f"{51.00 + r * 0.135:.2f}"
            lon_label = f"{-2.70 + c * 0.135:.2f}"
            ax.text(
                cx, cy - 1.2,
                f"({lat_label}, {lon_label})",
                ha="center", va="center",
                fontsize=6.5, color="#555555", style="italic",
                zorder=10,
            )
            ax.plot(cx, cy, "o", color=COLOR_CENTRE, markersize=3, zorder=10)

    return centres


def highlight_active_tiles(ax, tiles, cols=3, rows=3):
    """Highlight specific tile (col, row) pairs as 'loaded for routing'."""
    for (c, r) in tiles:
        x0 = c * TILE_SIZE_KM
        y0 = r * TILE_SIZE_KM
        rect = mpatches.FancyBboxPatch(
            (x0, y0), TILE_SIZE_KM, TILE_SIZE_KM,
            boxstyle="round,pad=0",
            facecolor=COLOR_ACTIVE_FILL,
            edgecolor=COLOR_ACTIVE_EDGE,
            linewidth=2.5,
            zorder=2,
        )
        ax.add_patch(rect)


def draw_overlap_bands(ax, tiles):
    """Draw 2 km overlap shading on shared edges of active tiles."""
    for (c, r) in tiles:
        x0 = c * TILE_SIZE_KM
        y0 = r * TILE_SIZE_KM

        # Draw overlap on all four edges (the overlap extends inward)
        # Left edge
        left = mpatches.Rectangle(
            (x0, y0), TILE_OVERLAP_KM, TILE_SIZE_KM,
            facecolor=COLOR_OVERLAP, edgecolor="none", zorder=3,
        )
        ax.add_patch(left)
        # Right edge
        right = mpatches.Rectangle(
            (x0 + TILE_SIZE_KM - TILE_OVERLAP_KM, y0),
            TILE_OVERLAP_KM, TILE_SIZE_KM,
            facecolor=COLOR_OVERLAP, edgecolor="none", zorder=3,
        )
        ax.add_patch(right)
        # Bottom edge
        bottom = mpatches.Rectangle(
            (x0, y0), TILE_SIZE_KM, TILE_OVERLAP_KM,
            facecolor=COLOR_OVERLAP, edgecolor="none", zorder=3,
        )
        ax.add_patch(bottom)
        # Top edge
        top = mpatches.Rectangle(
            (x0, y0 + TILE_SIZE_KM - TILE_OVERLAP_KM),
            TILE_SIZE_KM, TILE_OVERLAP_KM,
            facecolor=COLOR_OVERLAP, edgecolor="none", zorder=3,
        )
        ax.add_patch(top)


def draw_route(ax):
    """Draw an example route that crosses a tile boundary."""
    # Route crosses from tile (0,1) into tile (1,1) — left-centre to right-centre
    route_x = [3, 6, 10, 14, 16, 20, 24, 27]
    route_y = [20, 22, 24, 23.5, 22, 21, 22.5, 24]

    ax.plot(
        route_x, route_y,
        color=COLOR_ROUTE, linewidth=3.0, linestyle="-",
        solid_capstyle="round", solid_joinstyle="round",
        zorder=8, label="Example route",
    )
    # Start and end markers
    ax.plot(route_x[0], route_y[0], "o", color=OI_GREEN, markersize=10, zorder=9)
    ax.plot(route_x[-1], route_y[-1], "s", color=OI_RED, markersize=10, zorder=9)
    ax.text(route_x[0] - 0.3, route_y[0] + 1.2, "Start", fontsize=8, color=OI_GREEN, fontweight="bold", zorder=10)
    ax.text(route_x[-1] - 0.5, route_y[-1] + 1.2, "End", fontsize=8, color=OI_RED, fontweight="bold", zorder=10)


def add_dimension_annotations(ax):
    """Add dimension arrows showing tile size and overlap."""
    # Tile size annotation (bottom of grid)
    ax.annotate(
        "", xy=(TILE_SIZE_KM, -2.5), xytext=(0, -2.5),
        arrowprops=dict(arrowstyle="<->", color=OI_BLACK, lw=1.5),
        zorder=10,
    )
    ax.text(
        TILE_SIZE_KM / 2, -3.8,
        f"TILE_SIZE_KM = {TILE_SIZE_KM}",
        ha="center", va="center", fontsize=9, fontweight="bold",
        color=OI_BLACK, zorder=10,
    )

    # Overlap annotation (right side between two active tiles)
    boundary_x = TILE_SIZE_KM  # x-coord of boundary between tile(0,1) and tile(1,1)
    overlap_top = 1 * TILE_SIZE_KM + TILE_SIZE_KM  # top of row 1
    ax.annotate(
        "", xy=(boundary_x + TILE_OVERLAP_KM, overlap_top + 1.5),
        xytext=(boundary_x - TILE_OVERLAP_KM, overlap_top + 1.5),
        arrowprops=dict(arrowstyle="<->", color=OI_ORANGE, lw=1.5),
        zorder=10,
    )
    ax.text(
        boundary_x, overlap_top + 2.8,
        f"Overlap = {TILE_OVERLAP_KM} km\n(each side)",
        ha="center", va="center", fontsize=8, fontweight="bold",
        color="#B07800", zorder=10,
    )

    # Boundary line (dashed) at the tile edge
    ax.axvline(
        x=boundary_x, ymin=0.05, ymax=0.95,
        color=COLOR_GRID, linewidth=1.0, linestyle="--", alpha=0.6, zorder=5,
    )


def main():
    fig, ax = plt.subplots(1, 1, figsize=(10, 8), dpi=150)

    # Draw full 3×3 grid
    centres = draw_tile_grid(ax, cols=3, rows=3)

    # Active tiles: the route crosses from (0,1) to (1,1)
    active = [(0, 1), (1, 1)]
    highlight_active_tiles(ax, active)
    draw_overlap_bands(ax, active)

    # Route crossing boundary
    draw_route(ax)

    # Dimensions
    add_dimension_annotations(ax)

    # ── Legend ─────────────────────────────────────────────────────
    legend_elements = [
        mpatches.Patch(facecolor=COLOR_ACTIVE_FILL, edgecolor=COLOR_ACTIVE_EDGE,
                       linewidth=2, label="Tile loaded for routing"),
        mpatches.Patch(facecolor=COLOR_OVERLAP, edgecolor="none",
                       label=f"{TILE_OVERLAP_KM} km overlap band"),
        plt.Line2D([0], [0], color=COLOR_ROUTE, linewidth=3,
                   label="Example route"),
        mpatches.Patch(facecolor=COLOR_DEFAULT_FILL, edgecolor=COLOR_GRID,
                       linewidth=1, label="Inactive tile"),
    ]
    ax.legend(
        handles=legend_elements, loc="lower right",
        fontsize=8, framealpha=0.9, edgecolor="#CCCCCC",
    )

    # ── Axis setup ────────────────────────────────────────────────
    ax.set_xlim(-1, 3 * TILE_SIZE_KM + 1)
    ax.set_ylim(-5, 3 * TILE_SIZE_KM + 4)
    ax.set_aspect("equal")
    ax.set_xlabel("Longitude (km, illustrative)", fontsize=10)
    ax.set_ylabel("Latitude (km, illustrative)", fontsize=10)
    ax.set_title(
        "Tile Grid with 2 km Boundary Overlap\n"
        f"(TILE_SIZE_KM = {TILE_SIZE_KM}, TILE_OVERLAP_KM = {TILE_OVERLAP_KM})",
        fontsize=13, fontweight="bold", pad=12,
    )

    # Remove spines for cleaner figure
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    plt.tight_layout()

    # ── Save output ───────────────────────────────────────────────
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "8_tile_caching_spatial_layout.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"[OK] Saved to {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
