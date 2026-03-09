# 2. WSM Additive (with Group Nature) Mathematical Flow

**Section:** Cost Function / Algorithmic Implementation  
**Purpose:** Details how `cost_calculator.py` processes raw scenic factors into a final admissible WSM A\* edge cost. The system evaluates **six criteria**: distance, greenness, water, quietness, social, and slope. With the optional "Group Nature" toggle, greenness and water use a disjunctive `min()` operator to prevent multi-criteria collapse (an edge near water OR greenery is equally rewarded). The slope criterion has **signed semantics**: a positive weight penalises steepness while a negative weight penalises flatness (preferring hilly routes). Adheres to the Okabe-Ito colour palette; distinct shapes (stadium for data, trapezoid for weights, rectangles for functions, hexagons for logic operators) guarantee visual accessibility.

**Source:** [`cost_calculator.py` — `validate_weights()`](../../app/services/routing/cost_calculator.py#L48) enforces six required keys: `distance`, `greenness`, `water`, `quietness`, `social`, `slope`. [`cost_wsm_additive()`](../../app/services/routing/cost_calculator.py#L113) is the implementation.

```mermaid
flowchart TD
    %% ── Okabe-Ito Accessible Colour Palette ──────────────────────
    classDef input fill:#E69F00,stroke:#000000,stroke-width:2px,color:#000000
    classDef weight fill:#56B4E9,stroke:#000000,stroke-width:2px,color:#000000
    classDef operator fill:#009E73,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef process fill:#0072B2,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef output fill:#D55E00,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef decision fill:#CC79A7,stroke:#000000,stroke-width:2px,color:#000000

    %% ── Raw Inputs (6 normalised cost values 0=good 1=bad) ──────
    L(["Edge Length (dist)"]):::input
    G(["Green Cost (C_g)"]):::input
    W(["Water Cost (C_w)"]):::input
    Q(["Quiet Cost (C_q)"]):::input
    S(["Social Cost (C_s)"]):::input
    E(["Slope Cost (C_e)"]):::input

    %% ── User-Interface Weight Sliders ────────────────────────────
    uL[/"Distance Wgt (w_d)"\]:::weight
    uNature[/"Nature Wgt (w_n)"\]:::weight
    uQ[/"Quietness Wgt (w_q)"\]:::weight
    uS[/"Social Wgt (w_s)"\]:::weight
    uE[/"Slope Wgt (w_e)  — signed"\]:::weight

    %% ── Normalisation Functions ──────────────────────────────────
    NormL["Normalise Length\nN(dist)"]:::process
    NormG["Normalise Cost\nN(C_g)"]:::process
    NormW["Normalise Cost\nN(C_w)"]:::process
    NormQ["Normalise Cost\nN(C_q)"]:::process
    NormS["Normalise Cost\nN(C_s)"]:::process
    NormE["Normalise Cost\nN(C_e)"]:::process

    L --> NormL
    G --> NormG
    W --> NormW
    Q --> NormQ
    S --> NormS
    E --> NormE

    %% ── Group Nature Logic (Disjunctive OR Semantics) ────────────
    MinOp{{"Minimum Operator\n(Best of Nature)\nmin(N(C_g), N(C_w))"}}:::operator
    NormG --> MinOp
    NormW --> MinOp

    %% ── Linear Multiplications ───────────────────────────────────
    Mult1["Baseline Cost\nw_d × N(dist)"]:::process
    Mult2["Nature Cost\nw_n × min(C_g, C_w)"]:::process
    Mult3["Quietness Cost\nw_q × N(C_q)"]:::process
    Mult4["Social Cost\nw_s × N(C_s)"]:::process

    NormL --> Mult1
    uL -.-> Mult1

    MinOp --> Mult2
    uNature -.->|"Slider Value"| Mult2

    NormQ --> Mult3
    uQ -.->|"Slider Value"| Mult3

    NormS --> Mult4
    uS -.->|"Slider Value"| Mult4

    %% ── Slope: Signed-Weight Conditional Branch ──────────────────
    %% Source: cost_wsm_additive() in cost_calculator.py
    %% if slope_weight >= 0: cost += w_e × norm_slope   (penalise steepness)
    %% if slope_weight <  0: cost += |w_e| × (1 - norm_slope)  (penalise flatness)
    SlopeDecision{"w_e ≥ 0 ?"}:::decision
    uE -.-> SlopeDecision
    NormE --> SlopeDecision

    SlopeAvoid["Avoid Slope\n|w_e| × N(C_e)"]:::process
    SlopePrefer["Prefer Slope\n|w_e| × (1 − N(C_e))"]:::process

    SlopeDecision -->|"Yes — penalise steepness"| SlopeAvoid
    SlopeDecision -->|"No — penalise flatness"| SlopePrefer

    %% ── Final Additive Combination (AND Semantics) ───────────────
    Add{{"Total Edge Cost\n(+)"}}:::operator
    Mult1 -->|"Add"| Add
    Mult2 -->|"Add"| Add
    Mult3 -->|"Add"| Add
    Mult4 -->|"Add"| Add
    SlopeAvoid -->|"Add"| Add
    SlopePrefer -->|"Add"| Add

    EdgeCost(["Final Cost for\nWSM A* Node Traversal"]):::output
    Add --> EdgeCost
```
