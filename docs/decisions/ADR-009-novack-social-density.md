# ADR-009: Adoption of Novack (2018) Social "Third Place" Metric

## Context

The ScenicPathFinder project aims to provide route suggestions that optimize for "scenic" qualities, including greenness, quietness, and sociability.

Previously, the **Sociability** factor was calculated using a **Proximity Score** ($1 - \frac{\text{distance}}{50m}$). An edge was considered "social" if it was strictly *close* to a Point of Interest (POI). This favored edges leading *to* a destination but did not necessarily identify "lively streets" where one walks *past* multiple social venues.

We reviewed the methodology from **Novack et al. (2018)** *"A System for Generating Customized Pleasant Pedestrian Routes Based on OpenStreetMap Data"*, which uses a density-based approach.

## Decision

We have decided to **replace** the proximity-based social scoring with the **Novack Density Metric**.

### 1. The Metric
The cost for an edge is calculated as:
$$ Cost_{social} = \frac{\text{Length of Edge}}{\text{Count of "Third Places" in 50m Buffer}} $$

*   **Lower Cost is Better**: A high count of social places reduces the cost close to 0.
*   **Zero Count Handling**: If count is 0, we divide by a small epsilon ($\epsilon \approx 0.1$), resulting in a high cost proportional to length.

### 2. "Third Place" Definition
We have updated the OSM tag filtering to strictly match Novack's validated list of "Third Places" (places of social interaction), rather than generic "tourism" tags.

**Included Categories:**
*   **Amenity**: `cafe`, `bar`, `pub`, `restaurant`, `ice_cream`, `fast_food`, `food_court`, `biergarten`
*   **Shop**: `bakery`, `convenience`, `supermarket`, `mall`, `department_store`, `clothes`, `fashion`, `shoes`, `gift`, `books`
*   **Leisure**: `fitness_centre`, `sports_centre`, `gym`, 'dance', `bowling_alley`

### 3. Normalisation Changes
Unlike the previous proximity score which was naturally bounded $[0, 1]$, the density metric is unbounded ($Cost \in (0, \infty)$).
*   **Action**: `raw_social_cost` has been added to the mandatory normalisation list in `normalisation.py`.
*   **Effect**: The routing engine will dynamically scale these costs to $[0, 1]$ based on the min/max values found in the current graph, ensuring compatibility with the Weighted Sum Model (WSM) and Weighted-MIN algorithms.

## Consequences

### Positive
*   **Alignment with Literature**: The system now uses a academically validated metric for "sociability".
*   **Better "Vibe" Detection**: The system successfully identifies streets lined with shops/cafes (high density) rather than just streets near a single museum.
*   **Clearer Definition**: References strictly defined "Third Places" rather than vague "tourism" tags.

### Negative
*   **Loss of Absolute Scale**: Costs are now relative to the current map view (dynamic normalisation). A "high social" street in a quiet village might have the same normalised score as a "high social" street in a city center, whereas the previous proximity score was absolute. This is considered an acceptable trade-off for better route differentiation.

## References
*   Novack, T., Wang, Z., & Zipf, A. (2018). *A System for Generating Customized Pleasant Pedestrian Routes Based on OpenStreetMap Data*. Seniors, 18(11), 3794.
