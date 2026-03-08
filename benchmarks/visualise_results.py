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
        
    timings = {k: v for k, v in data["timings"].items() if k != "TOTAL"}
    
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
    
    plt.axhline(1500, color="gray", linestyle="--", label="Target Threshold (1.5GB)")
    
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
    """T-PERF-04: Extraction Methods (Dual Axis)"""
    if "methods" not in data:
        return
        
    methods = [m["method"] for m in data["methods"]]
    times = [m["time_s"] for m in data["methods"]]
    edges_per_sec = [m["edges_per_second"] for m in data["methods"]]
    
    # Create figure and axis
    fig, ax1 = plt.subplots(figsize=(10, 6))
    
    # Bar width and positioning
    x = np.arange(len(methods))
    width = 0.35
    
    color1 = 'tab:blue'
    rects1 = ax1.bar(x - width/2, times, width, label='Time (Seconds)', color=color1)
    ax1.set_ylabel('Execution Time (s)', color=color1)
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.set_xticks(x)
    ax1.set_xticklabels(methods, rotation=15, ha='right')
    
    # Secondary axis
    ax2 = ax1.twinx()
    color2 = 'tab:green'
    rects2 = ax2.bar(x + width/2, edges_per_sec, width, label='Edges/Second', color=color2)
    ax2.set_ylabel('Throughput (Edges/s)', color=color2)
    ax2.tick_params(axis='y', labelcolor=color2)
    
    # Set log scale for Y1 and Y2 since Isovist is massively different from buffer
    ax1.set_yscale('log')
    ax2.set_yscale('log')
    
    fig.suptitle("Spatial Extraction Methodology Comparison (T-PERF-04)\n(Logarithmic Scale)")
    
    # Legends
    lines, labels = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines + lines2, labels + labels2, loc='upper left')
    
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
        
    print("="*60)
    print(f"All visualisations saved to: {VIS_DIR}")

if __name__ == "__main__":
    run_visualisation()
