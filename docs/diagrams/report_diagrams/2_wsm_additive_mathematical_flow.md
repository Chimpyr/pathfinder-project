# 2. WSM Additive (with Group Nature) Mathematical Flow

**Section:** Cost Function / Algorithmic Implementation  
**Purpose:** Details how `cost_calculator.py` processes raw scenic factors into a final admissible WSM A\* edge cost. The system evaluates **six criteria**: distance, greenness, water, quietness, social, and slope. With the optional "Group Nature" toggle, greenness and water use a disjunctive `min()` operator to prevent multi-criteria collapse (an edge near water OR greenery is equally rewarded). The slope criterion has **signed semantics**: a positive weight penalises steepness while a negative weight penalises flatness (preferring hilly routes). Adheres to the Okabe-Ito colour palette; distinct shapes (stadium for data, trapezoid for weights, rectangles for functions, hexagons for logic operators) guarantee visual accessibility.

**Source:** [`cost_calculator.py` — `validate_weights()`](../../app/services/routing/cost_calculator.py#L48) enforces six required keys: `distance`, `greenness`, `water`, `quietness`, `social`, `slope`. [`cost_wsm_additive()`](../../app/services/routing/cost_calculator.py#L113) is the implementation.

```mermaid
flowchart TD
    %% ── Okabe-Ito Accessible Colour Palette ──────────────────────
    classDef input    fill:#E69F00,stroke:#000000,stroke-width:2px,color:#000000
    classDef operator fill:#009E73,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef process  fill:#0072B2,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef output   fill:#D55E00,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef decision fill:#CC79A7,stroke:#000000,stroke-width:2px,color:#000000

    %% ── Entry: six normalised scores ────────────────────────────
    Inputs(["Six normalised edge scores: N(dist), N(Cg), N(Cw), N(Cq), N(Cs), N(Ce) — each in [0 = good, 1 = bad]"]):::input

    %% ── Additive cost terms (criteria 1–4) ───────────────────────
    subgraph Additive ["Additive Cost Terms  (criteria 1–4)"]
        direction TB
        DistCost["1  Distance:   w_d × N(dist)"]:::process
        NatureCost["2  Nature:     w_n × min(N(Cg), N(Cw))  —  rewards water OR green edge"]:::process
        QuietCost["3  Quietness:  w_q × N(Cq)"]:::process
        SocialCost["4  Social:     w_s × N(Cs)"]:::process
    end

    %% ── Slope: signed-weight branch (criterion 5) ────────────────
    %% cost_wsm_additive() cost_calculator.py line 113:
    %%   if slope_weight >= 0: cost += w_e * norm_slope
    %%   else:                 cost += abs(w_e) * (1 - norm_slope)
    subgraph SlopeGroup ["Slope Cost  (criterion 5 — signed weight)"]
        direction TB
        SlopeDecision{"w_e >= 0 ?"}:::decision
        SlopeAvoid["Avoid steepness:   w_e x N(Ce)"]:::process
        SlopePrefer["Prefer steepness:  |w_e| x (1 - N(Ce))"]:::process
        SlopeDecision -->|"Yes — penalise steep"| SlopeAvoid
        SlopeDecision -->|"No — penalise flat"| SlopePrefer
    end

    %% ── Final sum ────────────────────────────────────────────────
    Add{{"Sum all five cost terms"}}:::operator
    EdgeCost(["Final WSM A* Edge Cost"]):::output

    %% ── Connections ──────────────────────────────────────────────
    Inputs --> Additive
    Inputs --> SlopeGroup
    Additive --> Add
    SlopeGroup --> Add
    Add --> EdgeCost
```
