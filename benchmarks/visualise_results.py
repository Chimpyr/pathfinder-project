"""
Benchmark Results Visualiser

Generates academic, publication-ready data visualisations from the JSON
results of the benchmark suite. These visualisations map directly to the
arguments and test cases in the REPORT.md (T-PERF-01 through T-PERF-05).

Usage:
    python -m benchmarks.visualise_results
"""

import os
import json

# Use non-interactive backend for headless Docker environments
import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

# Configuration
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
VIS_DIR = os.path.join(os.path.dirname(__file__), "visualisations")

# Set global seaborn styling for academic charts (colour-blind friendly)
sns.set_theme(style="whitegrid", context="paper", palette="colorblind")
plt.rcParams.update({
    "font.size": 12,
    "figure.titlesize": 16,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight"
})

def safe_load_json(filename):
    path = os.path.join(RESULTS_DIR, filename)
    if not os.path.exists(path):
        print(f"[WARN] Result file {filename} not found. Skipping plot.")
        return None
    with open(path, "r") as f:
        return json.load(f)

def ensure_vis_dir():
    os.makedirs(VIS_DIR, exist_ok=True)

def plot_route_latency(data):
    """T-PERF-01: Route Latency Distribution (Histogram/KDE)"""
    if "raw_latencies_ms" not in data:
        return
        
    latencies = data["raw_latencies_ms"]
    mean_ms = data.get("mean_ms", np.mean(latencies))
    p95_ms = data.get("p95_ms", np.percentile(latencies, 95))
    
    plt.figure(figsize=(8, 5))
    ax = sns.histplot(latencies, kde=True, bins=15, color="steelblue")
    
    # Add vertical lines for thresholds
    plt.axvline(x=mean_ms, color="darkred", linestyle="--", linewidth=2, label=f"Mean: {mean_ms:.0f}ms")
    plt.axvline(x=p95_ms, color="darkorange", linestyle=":", linewidth=2, label=f"95th Pct: {p95_ms:.0f}ms")
    
    plt.title("Routing Computation Latency on Warm Cache (T-PERF-01)")
    plt.xlabel("Latency (Milliseconds)")
    plt.ylabel("Frequency")
    plt.legend()
    
    out_path = os.path.join(VIS_DIR, "t_perf_01_route_latency.png")
    plt.savefig(out_path)
    plt.close()
    print(f"Generated: {out_path}")

def plot_graph_build_stages(data):
    """T-PERF-02: Graph Build Phases (Horizontal Stacked Bar)"""
    if "timings" not in data:
        return
        
    timings = {k: v for k, v in data["timings"].items() if k != "TOTAL" and "Total" not in k}
    
    labels = list(timings.keys())
    values = list(timings.values())
    
    df = pd.DataFrame({"Stage": labels, "Duration (s)": values})
    df = df.sort_values(by="Duration (s)")
    
    fig, ax = plt.subplots(figsize=(10, max(3, len(df) * 0.8)))
    sns.barplot(x="Duration (s)", y="Stage", data=df, hue="Stage", dodge=False, palette="viridis", legend=False, ax=ax)
    
    # Add duration text on the bars (iterate sorted df by position)
    max_dur = df["Duration (s)"].max()
    for idx in range(len(df)):
        v = df.iloc[idx]["Duration (s)"]
        ax.text(v + (max_dur * 0.02), idx, f"{v:.1f}s", color="black", va="center")
        
    ax.set_title("Graph Build Phase Bottlenecks (T-PERF-02)")
    ax.set_xlabel("Execution Time (Seconds)")
    ax.set_ylabel("")
    
    out_path = os.path.join(VIS_DIR, "t_perf_02_graph_build.png")
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

def plot_memory_usage(data):
    """T-PERF-03: Memory Peak RSS (Grouped Bar Chart)"""
    clipped = data.get("clipped", {}).get("peak_rss_mb", 0)
    unclipped = data.get("unclipped", {}).get("peak_rss_mb", 0)
    
    # Handle OOM cases
    if unclipped == 0 and not data.get("unclipped", {}).get("success", True):
        unclipped = 8192 # Arbitrary OOM representation for chart if it crashed container
        oom_label = " (OOM Crash)"
    else:
        oom_label = ""
        
    if clipped == 0 and unclipped == 0:
        return
        
    categories = ["BBox Clipped (ADR-004)", f"Full Region{oom_label}"]
    values = [clipped, unclipped]
    
    plt.figure(figsize=(7, 6))
    ax = sns.barplot(x=categories, y=values, hue=categories, dodge=False, palette=["mediumseagreen", "indianred"])
    
    plt.axhline(5000, color="gray", linestyle="--", label="NFR-05 Target Threshold (5 GB)")
    
    for i, v in enumerate(values):
        ax.text(i, v + 100, f"{v:.0f} MB", color="black", ha="center")
        
    plt.title("Peak Memory Usage During Graph Build (T-PERF-03)")
    plt.ylabel("Peak RSS (Megabytes)")
    plt.legend()
    
    out_path = os.path.join(VIS_DIR, "t_perf_03_memory_usage.png")
    plt.savefig(out_path)
    plt.close()
    print(f"Generated: {out_path}")

def plot_extraction_comparison(data):
    """T-PERF-04: Extraction Methods (Side-by-Side Bar Charts)"""
    if "methods" not in data:
        return
        
    methods = [m["method"].split(" (")[0] for m in data["methods"]]
    times = [m["time_s"] for m in data["methods"]]
    edges_per_sec = [m["edges_per_second"] for m in data["methods"]]
    
    # Create figure with 2 subplots side-by-side
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    x = np.arange(len(methods))
    width = 0.6
    
    # Plot 1: Execution Time
    color1 = sns.color_palette("muted")[0]
    bars1 = ax1.bar(x, times, width, color=color1)
    ax1.set_title("Execution Time (Seconds)")
    ax1.set_ylabel("Seconds (Log Scale)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(methods, rotation=15, ha='right')
    ax1.set_yscale("log")
    
    # Add value labels on top of bars
    for bar in bars1:
        yval = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2, yval * 1.1, f'{yval:,.1f}s', ha='center', va='bottom', fontweight='bold')
    
    # Plot 2: Throughput (Edges/Second)
    color2 = sns.color_palette("muted")[1]
    bars2 = ax2.bar(x, edges_per_sec, width, color=color2)
    ax2.set_title("Processing Throughput (Edges / Second)")
    ax2.set_ylabel("Edges/s (Log Scale)")
    ax2.set_xticks(x)
    ax2.set_xticklabels(methods, rotation=15, ha='right')
    ax2.set_yscale("log")
    
    for bar in bars2:
        yval = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2, yval * 1.1, f'{int(yval):,}/s', ha='center', va='bottom', fontweight='bold')
    
    fig.suptitle("Spatial Extraction Methodology Comparison (T-PERF-04)", fontsize=16, fontweight='bold', y=1.05)
    
    out_path = os.path.join(VIS_DIR, "t_perf_04_extraction.png")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

def plot_loop_convergence(data):
    """T-PERF-05: Target vs Actual Loop Distances (Scatter)"""
    if "raw_results" not in data:
        return
        
    df = pd.DataFrame(data["raw_results"])
    df = df[df["success"] == True]
    
    if df.empty:
        return

    plt.figure(figsize=(8, 8))
    
    # Draw perfect 1:1 convergence line
    max_val = max(df["target_km"].max(), df["actual_km"].max()) + 1
    plt.plot([0, max_val], [0, max_val], 'k--', alpha=0.5, label="Ideal Target Distance (1:1)")
    
    sns.scatterplot(
        data=df, 
        x="target_km", 
        y="actual_km", 
        hue="bias", 
        style="bias",
        s=150,
        palette="colorblind"
    )
    
    plt.title("Loop Generator Geometric Convergence (T-PERF-05)")
    plt.xlabel("Requested Target Distance (km)")
    plt.ylabel("Actual Generated Route Distance (km)")
    plt.legend(title="Directional Bias")
    
    # Force aspects to be square so 1:1 line is perfectly diagonal
    plt.gca().set_aspect('equal', adjustable='box')
    plt.xlim(0, max_val)
    plt.ylim(0, max_val)
    
    out_path = os.path.join(VIS_DIR, "t_perf_05_loop_convergence.png")
    plt.savefig(out_path)
    plt.close()
    print(f"Generated: {out_path}")

def plot_stress_test(data):
    """T-PERF-06: API Stress Validation under Load"""
    if "results" not in data or not data["results"]:
        return

    users = [r["users"] for r in data["results"]]
    avg_lat = [r["avg_latency_ms"] / 1000.0 for r in data["results"]]
    max_lat = [r.get("max_latency_ms", 0) / 1000.0 for r in data["results"]]

    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(users))
    width = 0.35
    
    ax.bar(x - width/2, avg_lat, width, label='Average Latency', color=sns.color_palette("muted")[0])
    ax.bar(x + width/2, max_lat, width, label='Max Latency', color=sns.color_palette("muted")[3])
    
    ax.set_title("API Edge Routing Performance under Concurrent Load (T-PERF-06)")
    ax.set_xlabel("Number of Concurrent Request Connections")
    ax.set_ylabel("Latency (Seconds)")
    ax.set_xticks(x)
    ax.set_xticklabels(users)
    ax.legend()
    
    # Add labels
    for i in range(len(users)):
        ax.text(i - width/2, avg_lat[i] + 0.5, f"{avg_lat[i]:.1f}s", ha='center', va='bottom', fontsize=9)
        ax.text(i + width/2, max_lat[i] + 0.5, f"{max_lat[i]:.1f}s", ha='center', va='bottom', fontsize=9)
    
    out_path = os.path.join(VIS_DIR, "t_perf_06_stress.png")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

def plot_pruning(data):
    """T-ENG-03: Graph Pruning Validation (Grouped Bar Chart)"""
    if "raw_highway_distribution" not in data or "pruned_highway_distribution" not in data:
        print("[WARN] Pruning data missing raw/pruned keys. Fallback to old pie chart skipped.")
        return
        
    raw = data["raw_highway_distribution"]
    pruned = data["pruned_highway_distribution"]
    
    # We want to highlight the filtering of forbidden types + common types
    target_keys = ["motorway", "trunk", "primary", "secondary", "residential", "service", "footway", "path", "cycleway", "track", "unclassified"]
    
    # Also add any top keys from pruned that aren't in target_keys
    for k, v in sorted(pruned.items(), key=lambda x: x[1], reverse=True)[:5]:
        if k not in target_keys:
            target_keys.append(k)
            
    plot_data = []
    for k in target_keys:
        raw_val = raw.get(k, 0)
        pruned_val = pruned.get(k, 0)
        if raw_val > 0 or pruned_val > 0:
            plot_data.append({"Highway Type": k, "Count": raw_val, "State": "Before Filter (Raw OSM)"})
            plot_data.append({"Highway Type": k, "Count": pruned_val, "State": "After Filter (Walking-Optimised)"})
            
    df = pd.DataFrame(plot_data)
    
    if df.empty:
        return
        
    fig, ax = plt.subplots(figsize=(12, 6))
    sns.barplot(data=df, x="Highway Type", y="Count", hue="State", palette=["indianred", "mediumseagreen"], ax=ax)
    
    ax.set_title("Edge Highway Pruning Efficacy (T-ENG-03)\nDemonstrates the absolute removal of motorways/trunks and retention of walkable paths.")
    ax.set_yscale("log")
    ax.set_ylabel("Number of Edges (Log Scale)")
    plt.xticks(rotation=45, ha="right")
    
    # Add exact numeric labels on bars
    for container in ax.containers:
        ax.bar_label(container, fmt='%d', padding=3, rotation=90, size=8)
        
    out_path = os.path.join(VIS_DIR, "t_eng_03_pruning.png")
    fig.tight_layout()
    fig.savefig(out_path)
    plt.close(fig)
    print(f"Generated: {out_path}")

def plot_wsm_efficacy(data):
    """T-ENG-02 & T-ENG-04: Weighted Sum Model and Advanced Options (Horizontal Bars)"""
    if "details" not in data:
        return
        
    wsm_names = []
    wsm_lengths = []
    
    adv_names = []
    adv_lengths = []
    
    for d in data["details"]:
        name = d["name"]
        length = d.get("coords_length", d.get("coords_length_or", 0))
        
        # Split into WSM Sliders vs Advanced Toggles based on (5) suffix
        if "(5)" in name:
            wsm_names.append(name)
            wsm_lengths.append(length)
        else:
            adv_names.append(name)
            adv_lengths.append(length)
            
    # 1. Plot WSM Sub-chart (T-ENG-02)
    if wsm_names:
        fig1, ax1 = plt.subplots(figsize=(10, 5))
        y_pos = np.arange(len(wsm_names))
        colors1 = sns.color_palette("husl", len(wsm_names))
        bars1 = ax1.barh(y_pos, wsm_lengths, align='center', color=colors1)
        ax1.set_yticks(y_pos)
        ax1.set_yticklabels(wsm_names)
        ax1.invert_yaxis()
        ax1.set_xlabel('Geometric Route Length (Number of Coordinate Waypoints)')
        ax1.set_title('Impact of Environmental Weighting on Path Geometry (T-ENG-02)\n'
                     'Route: Bristol Temple Meads to Clifton Suspension Bridge (~3.2km)', fontsize=13)
        for bar in bars1:
            ax1.text(bar.get_width() + 5, bar.get_y() + bar.get_height()/2, f'{int(bar.get_width())} coords', ha='left', va='center', fontweight='bold')
        out_path1 = os.path.join(VIS_DIR, "t_eng_02_wsm.png")
        fig1.tight_layout()
        fig1.savefig(out_path1)
        plt.close(fig1)
        print(f"Generated: {out_path1}")
        
    # 2. Plot Advanced Options Sub-chart (T-ENG-04)
    if adv_names:
        fig2, ax2 = plt.subplots(figsize=(10, 4))
        y_pos2 = np.arange(len(adv_names))
        colors2 = sns.color_palette("Set2", len(adv_names))
        bars2 = ax2.barh(y_pos2, adv_lengths, align='center', color=colors2)
        ax2.set_yticks(y_pos2)
        ax2.set_yticklabels(adv_names)
        ax2.invert_yaxis()
        ax2.set_xlabel('Geometric Route Length (Number of Coordinate Waypoints)')
        ax2.set_title('Impact of Advanced Routing Options on Path Geometry (T-ENG-04)\n'
                     'Route: Bristol Temple Meads to Clifton Suspension Bridge (~3.2km)', fontsize=13)
        for bar in bars2:
            ax2.text(bar.get_width() + 5, bar.get_y() + bar.get_height()/2, f'{int(bar.get_width())} coords', ha='left', va='center', fontweight='bold')
        out_path2 = os.path.join(VIS_DIR, "t_eng_04_advanced_options.png")
        fig2.tight_layout()
        fig2.savefig(out_path2)
        plt.close(fig2)
        print(f"Generated: {out_path2}")

def run_visualisation():
    print("="*60)
    print("Generating Academic Visualisations from Benchmarks")
    print("="*60)
    
    ensure_vis_dir()
    
    # T-PERF-01
    latency_data = safe_load_json("route_latency.json")
    if latency_data:
        plot_route_latency(latency_data)
        
    # T-PERF-02
    build_data = safe_load_json("graph_build.json")
    if build_data:
        plot_graph_build_stages(build_data)
        
    # T-PERF-03
    mem_data = safe_load_json("memory_usage.json")
    if mem_data:
        plot_memory_usage(mem_data)
        
    # T-PERF-04
    ext_data = safe_load_json("extraction_comparison.json")
    if ext_data:
        plot_extraction_comparison(ext_data)
        
    # T-PERF-05
    loop_data = safe_load_json("loop_solver.json")
    if loop_data:
        plot_loop_convergence(loop_data)
        
    # T-PERF-06
    stress_data = safe_load_json("stress_test.json")
    if stress_data:
        plot_stress_test(stress_data)
        
    # T-ENG-03
    pruning_data = safe_load_json("pruning_verification.json")
    if pruning_data:
        plot_pruning(pruning_data)
        
    # T-ENG-02
    wsm_data = safe_load_json("wsm_efficacy.json")
    if wsm_data:
        plot_wsm_efficacy(wsm_data)
        
    print("="*60)
    print(f"All visualisations saved to: {VIS_DIR}")

if __name__ == "__main__":
    run_visualisation()
