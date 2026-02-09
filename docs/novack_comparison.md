# Comparison: ScenicPathFinder vs. Novack et al. (2018)

This document compares the implementation of scenic routing in **ScenicPathFinder** with the methodology presented in _"A System for Generating Customized Pleasant Pedestrian Routes Based on OpenStreetMap Data"_ (Novack et al., 2018).

---

## 1. Core Differences at a Glance

| Feature           | Novack et al. (2018)                                                                                          | ScenicPathFinder (Your Project)                                                                                                               |
| :---------------- | :------------------------------------------------------------------------------------------------------------ | :-------------------------------------------------------------------------------------------------------------------------------------------- |
| **Cost Function** | **Pure Weighted Sum Model (WSM)**<br>Additive: $Cost = w_l \hat{l} + w_g \hat{g} + w_s \hat{s} + w_q \hat{q}$ | **Hybrid Additive-Disjunctive** (Default)<br>Weighted-MIN: $\text{min}(\frac{\text{score}}{1+w})$<br>_(Also supports pure WSM configuration)_ |
| **Greenness**     | **Isovist / Viewshed Analysis**<br>Simulates visual perception (what can _actually_ be seen).                 | **Dual Mode**: <br>1. `NOVACK` mode (Implements exact isovist logic)<br>2. `EDGE_SAMPLING` / `FAST` (Simpler, faster proxies)                 |
| **Sociability**   | **Density of "Third Places"**<br>Count of specific amenities in 50m buffer.                                   | **Proximity / Access Score**<br>Inverse distance to nearest POIs with diminishing returns.                                                    |
| **Quietness**     | **Binary/Ternary Classification**<br>Road type $\rightarrow$ Noise Factor (1.0 vs 2.0).                       | **Similar Classification**<br>Extends logic with `noise_factor` based on highway tags.                                                        |
| **Water**         | **Implicit** (likely via "Natural" tags)                                                                      | **Explicit Factor**<br>Dedicated `WaterProcessor` calculating proximity.                                                                      |
| **Graph Prep**    | **High Computational Cost**<br>(Due to complex isovist geometry).                                             | **Configurable Cost**<br>Fast modes for rapid iteration vs. slow/accurate modes.                                                              |

---

## 2. Methodology Deep Dive

### A. Cost Function & Multi-Criteria Decision Analysis (MCDA)

**Novack's Approach (Pure WSM):**
Novack uses a classic **Weighted Sum Model**. All factors (distance, greenness, sociability, quietness) are normalized and summed.

- **Formula:** $W_i = w_l \hat{l}_i + w_s \hat{s}_i + w_g \hat{g}_i + w_q \hat{q}_i$
- **Implication:** A street must be "good enough" at _everything_ to be selected. If a street is very green but slightly noisy, the noise penalty might outweigh the green benefit, leading to "average" routes rather than "specialized" ones.
- **Your Code:** You support this via `CostFunction.WSM_ADDITIVE` in `cost_calculator.py`.

**Your Approach (Hybrid Disjunctive):**
Your default `CostFunction.HYBRID_DISJUNCTIVE` uses a **Weighted-MIN** approach for scenic features.

- **Formula:** $Cost = \text{Distance} + \text{Weight} \times \min(\text{Adjusted Scores})$
- **Implication:** This is a significant deviation. It follows a "logical OR" philosophy: a street is good if it is _either_ green _or_ quiet _or_ social. This prevents the "multi-criteria collapse" where great features are hidden by mediocre scores in other categories.
- **Verdict:** Your approach is likely **better for discovery**, allowing users to find "hidden gems" that excel in one specific aspect, whereas Novack's approach yields "well-rounded" but potentially boring routes.

### B. Feature Extraction: Greenness

**Novack's Approach (Isovist):**

- **Method:** Discretize street into points $\rightarrow$ Cast 360° rays $\rightarrow$ Clip by buildings $\rightarrow$ Calculate visible green area.
- **Psychological Validity:** High. It models what a pedestrian _actually sees_, accounting for occlusion (e.g., a park behind a wall is not "green").
- **Efficiency:** Very Low. Ray-casting and polygon intersection are expensive ($O(N \times M)$ where $N$ is sample points and $M$ is building count).

**Your Approach:**

- **Implementation:** You have correctly implemented this in `NovackIsovistProcessor`.
- **Observation:** Your code notes `Typical processing time: ~10+ minutes for 325,000 edges`. This matches the expected computational intensity of the method.
- **Default:** You seem to default to `EDGE_SAMPLING` or similar, which likely uses simpler distance/buffer checks. This trades accuracy for speed.

### C. Feature Extraction: Sociability

**Novack's Approach (Third Places):**

- **Definition:** Specific list of tags (Cafe, Bar, Pub, etc. - see Table 1 in paper).
- **Metric:** $\text{Sociability} = \frac{\text{Length}}{\text{Count of Third Places}}$.
- **Focus:** Density/Vibrancy. A street with 10 bars is 10x more "social" than a street with 1.

**Your Approach (Proximity):**

- **Metric:** Inverse distance to nearest POI.
- **Focus:** Access/Convenience. A street _near_ a bar is "social".
- **Difference:** Novack's method better captures "lively streets" (walking _through_ a social area). Your method better captures "destinations" (walking _to_ a social area).

---

## 3. Efficiency Analysis

| Aspect            | Novack (2018)                                                                            | ScenicPathFinder                                        | Verdict                                         |
| :---------------- | :--------------------------------------------------------------------------------------- | :------------------------------------------------------ | :---------------------------------------------- |
| **Preprocessing** | **Slow**. Isovist calculation is computationally heavy. Requires full building geometry. | **Flexible**. Can be fast (buffers) or slow (isovists). | **Your approach succeeds by offering options.** |
| **Routing**       | **Fast**. Standard Dijkstra/A\* on a static graph.                                       | **Fast**. Standard A\* on a static graph.               | **Tie.** Both pre-calculate costs.              |
| **Storage**       | **Standard**. Edge weights are stored.                                                   | **Standard**. Edge weights are stored.                  | **Tie.**                                        |

**Is Novack's approach more efficient?**
**No.** Their preprocessing is significantly heavier due to the isovist analysis. However, for a production system covering a fixed area (like Heidelberg or Bristol), this effectively "one-time" cost is acceptable.

---

## 4. What can you learn from Novack?

1.  **Rigorous "Third Place" Definition:**
    - Novack provides a validated list of OSM tags (Table 1) that define a "Third Place".
    - _Action:_ Review your `POI_TOURISM_TAGS`, `POI_HISTORIC_TAGS`, and `POI_AMENITY_TAGS` in `social.py` against Novack's Table 1 to ensure you aren't missing key categories (e.g., specific retail types that encourage foot traffic).

2.  **Visual Perception vs. Proximity:**
    - Novack's key insight is that _seeing_ green is more important than _being near_ green squared-off on a map.
    - _Action:_ If `NOVACK` mode is too slow, consider an approximation: **"Visible Buffer"**. Intead of full ray-casting, check if a green polygon intersects a buffer _and_ if a building polygon intersects the line-of-sight to its centroid.

3.  **Noise Factors:**
    - Novack uses a simple binary/ternary factor (1.0 vs 2.0).
    - _Action:_ Your `quietness.py` implementation is already very close to this. You could refine it by adding a middle tier for "Secondary" roads (noisy but not highway) if you haven't already.

---

## 5. Summary & Answers

- **Will their methods get better results?**
  - For **Greenness**: **Yes**. The isovist method is superior for "scenic" quality because it filters out "fake green" (e.g., a park hidden behind a warehouse).
  - For **Sociability**: **Maybe**. Their density count might better identify "high streets" compared to your proximity score.

- **Is their approach different?**
  - Fundamentally, yes, in the **Cost Function**. They use a pure Weighted Sum; you use a Hybrid Weighted-MIN. Your approach helps distinct features shine without being diluted.

- **Recommendation:**
  - Keep your **Hybrid Cost Function** (it's a smart innovation).
  - Keep the **Novack Processor** available as a "High Quality" build option.
  - Adopt their **"Third Place" tag list** to refine your social scoring.
