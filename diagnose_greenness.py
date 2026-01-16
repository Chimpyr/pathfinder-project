"""
Diagnostic script to check greenness data quality in cached graph.
Run this to see the distribution of norm_green values.
"""
import pickle
import os
import glob
from collections import Counter

# Find the cached graph (auto-detect filename)
cache_dir = os.path.join(
    os.path.dirname(__file__),
    "app", "data", "cache"
)
pickle_files = glob.glob(os.path.join(cache_dir, "*.pickle"))

if not pickle_files:
    print(f"No cache files found in: {cache_dir}")
    exit(1)

cache_path = pickle_files[0]  # Use first one found

print(f"Loading cache from: {cache_path}")
with open(cache_path, 'rb') as f:
    graph = pickle.load(f)

print(f"Graph has {len(graph.nodes)} nodes and {len(graph.edges)} edges")

# Collect all norm_green values
norm_green_values = []
raw_green_costs = []
norm_quiet_values = []

for u, v, key, data in graph.edges(keys=True, data=True):
    ng = data.get('norm_green')
    rgc = data.get('raw_green_cost')
    nq = data.get('norm_quiet')
    
    if ng is not None:
        norm_green_values.append(ng)
    if rgc is not None:
        raw_green_costs.append(rgc)
    if nq is not None:
        norm_quiet_values.append(nq)

print("\n=== GREENNESS DATA ===")
print(f"Edges with norm_green: {len(norm_green_values)}")
print(f"Edges with raw_green_cost: {len(raw_green_costs)}")

if norm_green_values:
    print(f"\nnorm_green distribution:")
    print(f"  min: {min(norm_green_values):.4f}")
    print(f"  max: {max(norm_green_values):.4f}")
    print(f"  mean: {sum(norm_green_values)/len(norm_green_values):.4f}")
    
    # Count by ranges
    bins = {
        "0.0-0.2 (Very Green)": 0,
        "0.2-0.4 (Green)": 0,
        "0.4-0.6 (Moderate)": 0,
        "0.6-0.8 (Low Green)": 0,
        "0.8-1.0 (No Green)": 0,
    }
    for v in norm_green_values:
        if v < 0.2:
            bins["0.0-0.2 (Very Green)"] += 1
        elif v < 0.4:
            bins["0.2-0.4 (Green)"] += 1
        elif v < 0.6:
            bins["0.4-0.6 (Moderate)"] += 1
        elif v < 0.8:
            bins["0.6-0.8 (Low Green)"] += 1
        else:
            bins["0.8-1.0 (No Green)"] += 1
    
    print("\n  Distribution by range:")
    for label, count in bins.items():
        pct = 100 * count / len(norm_green_values)
        print(f"    {label}: {count} ({pct:.1f}%)")
else:
    print("  NO norm_green values found!")

print("\n=== QUIETNESS DATA (for comparison) ===")
print(f"Edges with norm_quiet: {len(norm_quiet_values)}")

if norm_quiet_values:
    print(f"\nnorm_quiet distribution:")
    print(f"  min: {min(norm_quiet_values):.4f}")
    print(f"  max: {max(norm_quiet_values):.4f}")
    print(f"  mean: {sum(norm_quiet_values)/len(norm_quiet_values):.4f}")
    
    # Count by ranges
    bins = {
        "0.0-0.2 (Very Quiet)": 0,
        "0.2-0.4 (Quiet)": 0,
        "0.4-0.6 (Moderate)": 0,
        "0.6-0.8 (Noisy)": 0,
        "0.8-1.0 (Very Noisy)": 0,
    }
    for v in norm_quiet_values:
        if v < 0.2:
            bins["0.0-0.2 (Very Quiet)"] += 1
        elif v < 0.4:
            bins["0.2-0.4 (Quiet)"] += 1
        elif v < 0.6:
            bins["0.4-0.6 (Moderate)"] += 1
        elif v < 0.8:
            bins["0.6-0.8 (Noisy)"] += 1
        else:
            bins["0.8-1.0 (Very Noisy)"] += 1
    
    print("\n  Distribution by range:")
    for label, count in bins.items():
        pct = 100 * count / len(norm_quiet_values)
        print(f"    {label}: {count} ({pct:.1f}%)")
