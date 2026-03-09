#!/usr/bin/env python3
"""
9. Edge Sampling vs Midpoint-Only — Publication-Ready Side-by-Side Diagram

Illustrates why EdgeSamplingProcessor (20 m sample intervals, 50 m buffer)
correctly captures greenness for long park-adjacent edges, where the
FastBufferProcessor (single midpoint buffer) fails.

Source constants (verified from code — do NOT change without checking):
    DEFAULT_BUFFER_RADIUS   = 50.0 m   (edge_sampling.py line 38)
    DEFAULT_SAMPLE_INTERVAL = 20.0 m   (edge_sampling.py line 39)
    FastBufferProcessor uses a single buffer at the edge midpoint
        (fast_buffer.py — DEFAULT_BUFFER_RADIUS = 50.0 m)

Output: docs/report_diagrams/9_edge_sampling_spatial.png
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Circle, Polygon
from matplotlib.collections import PatchCollection

# ── Constants from code (edge_sampling.py, fast_buffer.py) ──────────────
BUFFER_RADIUS = 50.0       # metres
SAMPLE_INTERVAL = 20.0     # metres

# ── Okabe-Ito Colour Palette ────────────────────────────────────────────
OI_ORANGE = "#E69F00"
OI_SKY    = "#56B4E9"
OI_GREEN  = "#009E73"
OI_BLUE   = "#0072B2"
OI_RED    = "#D55E00"
OI_PINK   = "#CC79A7"
OI_BLACK  = "#000000"

# Diagram-specific colours
COLOR_ROAD        = OI_BLACK
COLOR_PARK_FILL   = "#009E7340"     # Translucent green
COLOR_PARK_EDGE   = OI_GREEN
COLOR_BUFFER      = OI_SKY + "30"   # Very translucent blue
COLOR_BUFFER_EDGE = OI_BLUE
COLOR_HIT         = OI_ORANGE + "60" # Translucent orange for intersection
COLOR_MISS_BUFFER = "#BBBBBB50"     # Grey translucent for miss
COLOR_MISS_EDGE   = "#999999"
COLOR_SAMPLE_PT   = OI_RED          # Sample point dots
COLOR_MIDPOINT    = OI_PINK         # Midpoint marker


# ── Geometry setup ──────────────────────────────────────────────────────
# Road: 280 m long, running roughly left-to-right with a gentle curve
# The road's midpoint is ~140 m along — far from the park
# The road's right end (≥200 m) runs alongside the park

ROAD_X = np.array([0, 40, 80, 120, 160, 200, 240, 280])
ROAD_Y = np.array([100, 105, 108, 106, 100, 92, 85, 80])

# Park polygon: positioned alongside the RIGHT portion of the road
# The park is far from the midpoint but hugs the road from ~180 m onwards
PARK_VERTS = np.array([
    [170, 50],
    [300, 50],
    [300, 110],
    [260, 100],
    [230, 75],
    [200, 65],
    [175, 60],
])


def interpolate_road_points(x_nodes, y_nodes, interval):
    """Interpolate sample points along a polyline at a fixed interval."""
    # Compute cumulative distances
    dx = np.diff(x_nodes)
    dy = np.diff(y_nodes)
    seg_lengths = np.sqrt(dx**2 + dy**2)
    cum_dist = np.concatenate([[0], np.cumsum(seg_lengths)])
    total_length = cum_dist[-1]

    # Sample at regular intervals
    sample_dists = np.arange(0, total_length + interval / 2, interval)
    pts_x = np.interp(sample_dists, cum_dist, x_nodes)
    pts_y = np.interp(sample_dists, cum_dist, y_nodes)

    return pts_x, pts_y, total_length


def point_in_polygon(px, py, poly_verts):
    """Simple ray-casting point-in-polygon test."""
    n = len(poly_verts)
    inside = False
    x1, y1 = poly_verts[0]
    for i in range(1, n + 1):
        x2, y2 = poly_verts[i % n]
        if min(y1, y2) < py <= max(y1, y2):
            xinters = (py - y1) * (x2 - x1) / (y2 - y1) + x1
            if px <= xinters:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def circle_intersects_polygon(cx, cy, radius, poly_verts, num_test=36):
    """Approximate: does a circle overlap a polygon? Test boundary points."""
    # Check if centre is inside
    if point_in_polygon(cx, cy, poly_verts):
        return True
    # Check points around the circle perimeter
    angles = np.linspace(0, 2 * np.pi, num_test, endpoint=False)
    for a in angles:
        px = cx + radius * np.cos(a)
        py = cy + radius * np.sin(a)
        if point_in_polygon(px, py, poly_verts):
            return True
    # Check if any polygon vertex is inside the circle
    for vx, vy in poly_verts:
        if (vx - cx)**2 + (vy - cy)**2 <= radius**2:
            return True
    return False


def draw_panel_a(ax):
    """Panel A: FastBuffer — midpoint only."""
    # Draw park
    park = Polygon(PARK_VERTS, closed=True,
                   facecolor=COLOR_PARK_FILL, edgecolor=COLOR_PARK_EDGE,
                   linewidth=2, zorder=1, label="Park polygon")
    ax.add_patch(park)
    ax.text(250, 60, "Park", fontsize=11, fontweight="bold",
            color=OI_GREEN, ha="center", zorder=10)

    # Draw road
    ax.plot(ROAD_X, ROAD_Y, color=COLOR_ROAD, linewidth=3, solid_capstyle="round",
            zorder=5, label="Road edge")

    # Midpoint
    mid_idx = len(ROAD_X) // 2
    # Exact midpoint via interpolation
    pts_x, pts_y, total = interpolate_road_points(ROAD_X, ROAD_Y, 1.0)
    mid_x = pts_x[len(pts_x) // 2]
    mid_y = pts_y[len(pts_y) // 2]

    ax.plot(mid_x, mid_y, "D", color=COLOR_MIDPOINT, markersize=10, zorder=7)
    ax.text(mid_x, mid_y + 12, "Midpoint", fontsize=8, fontweight="bold",
            color=COLOR_MIDPOINT, ha="center", zorder=10)

    # Buffer circle at midpoint
    hits = circle_intersects_polygon(mid_x, mid_y, BUFFER_RADIUS, PARK_VERTS)
    buf_color = COLOR_BUFFER if hits else COLOR_MISS_BUFFER
    buf_edge = COLOR_BUFFER_EDGE if hits else COLOR_MISS_EDGE

    circle = Circle((mid_x, mid_y), BUFFER_RADIUS,
                     facecolor=buf_color, edgecolor=buf_edge,
                     linewidth=1.5, linestyle="--", zorder=3)
    ax.add_patch(circle)

    # Annotate radius
    ax.annotate(
        f"r = {int(BUFFER_RADIUS)} m", xy=(mid_x + BUFFER_RADIUS * 0.7, mid_y - BUFFER_RADIUS * 0.7),
        fontsize=8, color=OI_BLUE, fontweight="bold", zorder=10,
    )

    # Failure annotation
    ax.annotate(
        "Single buffer\nmisses park segment",
        xy=(mid_x, mid_y - BUFFER_RADIUS - 5),
        xytext=(mid_x - 40, mid_y - BUFFER_RADIUS - 35),
        fontsize=9, color=OI_RED, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=OI_RED, lw=1.5),
        ha="center", zorder=10,
    )

    # Score annotation
    ax.text(
        140, 140, "Greenness = 0.0\n(miss — no intersection)",
        fontsize=9, color=OI_RED, ha="center",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#FFEEEE", edgecolor=OI_RED, alpha=0.9),
        zorder=10,
    )

    ax.set_title("(A) FastBuffer: midpoint only", fontsize=12, fontweight="bold", pad=10)


def draw_panel_b(ax):
    """Panel B: EdgeSampling — 20 m intervals."""
    # Draw park
    park = Polygon(PARK_VERTS, closed=True,
                   facecolor=COLOR_PARK_FILL, edgecolor=COLOR_PARK_EDGE,
                   linewidth=2, zorder=1, label="Park polygon")
    ax.add_patch(park)
    ax.text(250, 60, "Park", fontsize=11, fontweight="bold",
            color=OI_GREEN, ha="center", zorder=10)

    # Draw road
    ax.plot(ROAD_X, ROAD_Y, color=COLOR_ROAD, linewidth=3, solid_capstyle="round",
            zorder=5, label="Road edge")

    # Sample points along the road
    pts_x, pts_y, total = interpolate_road_points(ROAD_X, ROAD_Y, SAMPLE_INTERVAL)

    hit_count = 0
    for i, (sx, sy) in enumerate(zip(pts_x, pts_y)):
        hits = circle_intersects_polygon(sx, sy, BUFFER_RADIUS, PARK_VERTS)
        if hits:
            hit_count += 1

        buf_color = COLOR_HIT if hits else COLOR_BUFFER
        buf_edge = OI_ORANGE if hits else COLOR_BUFFER_EDGE
        lw = 1.8 if hits else 1.0

        circle = Circle((sx, sy), BUFFER_RADIUS,
                         facecolor=buf_color, edgecolor=buf_edge,
                         linewidth=lw, linestyle="--" if not hits else "-",
                         zorder=3 if not hits else 4)
        ax.add_patch(circle)

    # Sample point dots
    ax.plot(pts_x, pts_y, "o", color=COLOR_SAMPLE_PT, markersize=4, zorder=6,
            label=f"Sample points (Δs = {int(SAMPLE_INTERVAL)} m)")

    # Annotations
    # Delta-s label
    if len(pts_x) >= 3:
        ax.annotate(
            f"Δs = {int(SAMPLE_INTERVAL)} m",
            xy=((pts_x[1] + pts_x[2]) / 2, (pts_y[1] + pts_y[2]) / 2 + 8),
            fontsize=8, color=OI_RED, fontweight="bold", ha="center", zorder=10,
        )

    # Buffer radius label (on a hit buffer near the park)
    park_hit_idx = len(pts_x) * 3 // 4  # Pick a point near park
    ax.annotate(
        f"r = {int(BUFFER_RADIUS)} m",
        xy=(pts_x[park_hit_idx] + BUFFER_RADIUS * 0.6,
            pts_y[park_hit_idx] - BUFFER_RADIUS * 0.6),
        fontsize=8, color=OI_BLUE, fontweight="bold", zorder=10,
    )

    # Success annotation
    ax.annotate(
        "Distributed samples\ndetect park adjacency",
        xy=(pts_x[-3], pts_y[-3] + BUFFER_RADIUS * 0.3),
        xytext=(pts_x[-3] - 80, pts_y[-3] + BUFFER_RADIUS + 30),
        fontsize=9, color=OI_GREEN, fontweight="bold",
        arrowprops=dict(arrowstyle="->", color=OI_GREEN, lw=1.5),
        ha="center", zorder=10,
    )

    # Score annotation
    score = hit_count / len(pts_x) if len(pts_x) > 0 else 0
    ax.text(
        140, 140,
        f"Greenness = {score:.2f}\n({hit_count}/{len(pts_x)} samples hit park)",
        fontsize=9, color=OI_GREEN, ha="center",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#EEFFEE", edgecolor=OI_GREEN, alpha=0.9),
        zorder=10,
    )

    ax.set_title("(B) EdgeSampling: 20 m intervals", fontsize=12, fontweight="bold", pad=10)


def main():
    fig, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(16, 7), dpi=150)

    for ax in (ax_a, ax_b):
        ax.set_xlim(-70, 330)
        ax.set_ylim(-10, 165)
        ax.set_aspect("equal")
        ax.set_xlabel("Distance along road (m)", fontsize=9)
        ax.set_ylabel("Perpendicular offset (m)", fontsize=9)
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(left=False, bottom=False, labelleft=False, labelbottom=False)

    draw_panel_a(ax_a)
    draw_panel_b(ax_b)

    fig.suptitle(
        "Edge Sampling Correctly Captures Park-Adjacent Greenness",
        fontsize=15, fontweight="bold", y=0.98,
    )

    # Shared legend below
    legend_elements = [
        plt.Line2D([0], [0], color=COLOR_ROAD, linewidth=3, label="Road edge (LineString)"),
        mpatches.Patch(facecolor=COLOR_PARK_FILL, edgecolor=COLOR_PARK_EDGE,
                       linewidth=2, label="Park polygon (vegetation)"),
        mpatches.Patch(facecolor=COLOR_BUFFER, edgecolor=COLOR_BUFFER_EDGE,
                       linewidth=1, label=f"Buffer circle (r = {int(BUFFER_RADIUS)} m) — no hit"),
        mpatches.Patch(facecolor=COLOR_HIT, edgecolor=OI_ORANGE,
                       linewidth=1.5, label=f"Buffer circle (r = {int(BUFFER_RADIUS)} m) — park intersection"),
        plt.Line2D([0], [0], marker="o", color="w", markerfacecolor=COLOR_SAMPLE_PT,
                   markersize=6, label=f"Sample point (Δs = {int(SAMPLE_INTERVAL)} m)"),
        plt.Line2D([0], [0], marker="D", color="w", markerfacecolor=COLOR_MIDPOINT,
                   markersize=8, label="Edge midpoint"),
    ]
    fig.legend(
        handles=legend_elements, loc="lower center", ncol=3,
        fontsize=8, framealpha=0.9, edgecolor="#CCCCCC",
        bbox_to_anchor=(0.5, -0.02),
    )

    plt.tight_layout(rect=[0, 0.06, 1, 0.95])

    # ── Save output ───────────────────────────────────────────────
    out_dir = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(out_dir, "9_edge_sampling_spatial.png")
    fig.savefig(out_path, dpi=150, bbox_inches="tight", facecolor="white")
    print(f"[OK] Saved to {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
