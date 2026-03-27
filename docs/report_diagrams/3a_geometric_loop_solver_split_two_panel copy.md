# 3A. Geometric Loop Solver — Split Two-Panel Continuation

**Goal:** Keep full detail while making the figure printable on a single A4 page by placing two connected panels side-by-side.

## Panel 1 (Left): Request → Distance Check

```mermaid
flowchart TD
    classDef entry fill:#E69F00,stroke:#000,stroke-width:2px,color:#000
    classDef process fill:#0072B2,stroke:#000,stroke-width:2px,color:#FFF
    classDef decision fill:#CC79A7,stroke:#000,stroke-width:2px,color:#000
    classDef success fill:#009E73,stroke:#000,stroke-width:2px,color:#FFF

    Start(["User requests loop route"]):::entry
    Solve["solve(target_distance, variety_level, directional_bias)"]:::process
    Start --> Solve

    BearingCheck{"directional_bias set?"}:::decision
    Solve --> BearingCheck

    SmartBearings["_analyze_scenic_sectors()\n12 sectors × 30°\nRank by scenic density"]:::process
    EquiBearings["Equidistant bearings\n(0°, 60°, 120°, …)"]:::process
    BearingCheck -->|"Yes"| SmartBearings
    BearingCheck -->|"No"| EquiBearings

    ConfigGate{"variety_level?"}:::decision
    SmartBearings --> ConfigGate
    EquiBearings --> ConfigGate

    V0["Triangle\nN=3 arc=90° irr=0.05"]:::process
    V1["Triangle + Quad\nN=4 arc=110° irr=0.15"]:::process
    V2["Tri + Quad + Pentagon\nN=5 arc=130° irr=0.25"]:::process
    ConfigGate -->|"0"| V0
    ConfigGate -->|"≥1"| V1
    ConfigGate -->|"≥2"| V2

    ForBearing["For each bearing + shape config"]:::process
    V0 --> ForBearing
    V1 --> ForBearing
    V2 --> ForBearing

    GenWP["generate_waypoints()\nProject vertices with τ=1.25"]:::process
    Snap["_smart_snap()\nKDTree SNAP_K=50\nanti-U-turn penalty"]:::process
    TryPoly["_try_polygon()\nStart→W1→...→Start"]:::process
    Prune["_prune_spurs()\nRemove A→B→A"]:::process
    DistCheck{"−5% ≤ deviation ≤ +15%?"}:::decision

    ForBearing --> GenWP --> Snap --> TryPoly --> Prune --> DistCheck

    ToP2Yes(["▶ Continue at A-Yes"]):::entry
    ToP2No(["▶ Continue at A-No"]):::entry
    DistCheck -->|"Yes"| ToP2Yes
    DistCheck -->|"No"| ToP2No
```

## Panel 2 (Right): Accept / Retry / Fallback / Return

```mermaid
flowchart TD
    classDef entry fill:#E69F00,stroke:#000,stroke-width:2px,color:#000
    classDef process fill:#0072B2,stroke:#000,stroke-width:2px,color:#FFF
    classDef decision fill:#CC79A7,stroke:#000,stroke-width:2px,color:#000
    classDef success fill:#009E73,stroke:#000,stroke-width:2px,color:#FFF
    classDef fail fill:#D55E00,stroke:#000,stroke-width:2px,color:#FFF
    classDef feedback fill:#56B4E9,stroke:#000,stroke-width:2px,color:#000

    FromP1Yes(["◀ A-Yes from Panel 1"]):::entry
    FromP1No(["◀ A-No from Panel 1"]):::entry

    Accept["Candidate accepted\nStore(route, distance, scenic_cost, metadata)"]:::success
    RetryCheck{"retry < 5?"}:::decision

    FromP1Yes --> Accept
    FromP1No --> RetryCheck

    TauUpdate["τ_new = τ × clamp(actual/target, 0.85, 1.15)"]:::feedback
    ToRetry(["◀ Return to Panel 1 at generate_waypoints()"]):::entry
    RetryCheck -->|"Yes"| TauUpdate -->|"Retry with adjusted τ"| ToRetry

    OABFallback["_try_out_and_back()\nStart→Far→Start"]:::process
    OABCheck{"Within distance tolerance?"}:::decision
    OABAccept["Out-and-back accepted"]:::success
    OABReject["Bearing abandoned"]:::fail

    RetryCheck -->|"No — retries exhausted"| OABFallback --> OABCheck
    OABCheck -->|"Yes"| OABAccept
    OABCheck -->|"No"| OABReject

    NextBearing{"More bearings to try?"}:::decision
    Accept --> NextBearing
    OABAccept --> NextBearing
    OABReject --> NextBearing

    ToLoop(["◀ Return to Panel 1 at For each bearing"]):::entry
    SelectDiv["select_diverse_candidates()\nPick top-K by quality + bearing diversity"]:::process
    Result(["Return K loop candidates to client"]):::entry

    NextBearing -->|"Yes"| ToLoop
    NextBearing -->|"No"| SelectDiv --> Result
```

## Placement Notes (for A4)

- Put Panel 1 on the left and Panel 2 on the right in equal-width columns.
- Keep both panels at the same visual scale.
- The `A-Yes` and `A-No` markers are continuation anchors and replace edge-cropping.
- If exported as SVG/PDF, text remains readable when printed.
