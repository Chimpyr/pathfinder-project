# 3D. Geometric Loop Solver — Step-Code + Legend (Maximum Compression)

**Goal:** Minimise text inside nodes for print legibility; keep full semantics in a legend table.

```mermaid
flowchart LR
    classDef entry fill:#E69F00,stroke:#000,stroke-width:2px,color:#000
    classDef process fill:#0072B2,stroke:#000,stroke-width:2px,color:#FFF
    classDef decision fill:#CC79A7,stroke:#000,stroke-width:2px,color:#000
    classDef success fill:#009E73,stroke:#000,stroke-width:2px,color:#FFF
    classDef fail fill:#D55E00,stroke:#000,stroke-width:2px,color:#FFF
    classDef feedback fill:#56B4E9,stroke:#000,stroke-width:2px,color:#000

    S0(["S0"]):::entry --> S1["S1"]:::process --> D1{"D1"}:::decision
    D1 -->|"Y"| S2["S2"]:::process
    D1 -->|"N"| S3["S3"]:::process
    S2 --> D2{"D2"}:::decision
    S3 --> D2

    D2 -->|"0"| S4["S4"]:::process
    D2 -->|"≥1"| S5["S5"]:::process
    D2 -->|"≥2"| S6["S6"]:::process

    S4 --> S7["S7"]:::process
    S5 --> S7
    S6 --> S7

    S7 --> S8["S8"]:::process --> S9["S9"]:::process --> S10["S10"]:::process --> S11["S11"]:::process --> D3{"D3"}:::decision
    D3 -->|"Y"| S12["S12"]:::success --> D6{"D6"}:::decision

    D3 -->|"N"| D4{"D4"}:::decision
    D4 -->|"Y"| S13["S13"]:::feedback --> S8
    D4 -->|"N"| S14["S14"]:::process --> D5{"D5"}:::decision
    D5 -->|"Y"| S15["S15"]:::success --> D6
    D5 -->|"N"| S16["S16"]:::fail --> D6

    D6 -->|"Y"| S7
    D6 -->|"N"| S17["S17"]:::process --> S18(["S18"]):::entry
```

## Legend

| Code | Meaning |
|---|---|
| S0 | User requests loop route |
| S1 | `solve(target_distance, variety_level, directional_bias)` |
| D1 | directional bias set? |
| S2 | scenic sector bearing analysis |
| S3 | equidistant bearings |
| D2 | variety-level gate |
| S4 | configs: Triangle |
| S5 | configs: Triangle + Quad |
| S6 | configs: Tri + Quad + Pentagon |
| S7 | iterate bearing + shape config |
| S8 | generate waypoints (`τ` scale) |
| S9 | smart snap (`SNAP_K=50`, anti-U-turn penalty) |
| S10 | try polygon route |
| S11 | prune spurs + recalc distance |
| D3 | within tolerance (`-5%`, `+15%`)? |
| S12 | accept candidate |
| D4 | retries remaining (`<5`)? |
| S13 | update `τ`: `τ × clamp(actual/target, 0.85, 1.15)` |
| S14 | out-and-back fallback |
| D5 | out-and-back within tolerance? |
| S15 | accept out-and-back |
| S16 | abandon bearing |
| D6 | more bearings to try? |
| S17 | select top-K diverse candidates |
| S18 | return K loop candidates |

## Notes

- This is the densest printable form and often the easiest to fit into strict report templates.
- It trades immediate readability for compactness; use when page space is constrained.
