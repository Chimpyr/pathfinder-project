# 3C. Geometric Loop Solver — Two-Level Figure (Overview + Detail)

**Goal:** Keep the main figure compact and move dense retry logic into a focused second diagram.

## Level 1: Master Flow (Compact)

```mermaid
flowchart LR
    classDef entry fill:#E69F00,stroke:#000,stroke-width:2px,color:#000
    classDef process fill:#0072B2,stroke:#000,stroke-width:2px,color:#FFF
    classDef decision fill:#CC79A7,stroke:#000,stroke-width:2px,color:#000
    classDef success fill:#009E73,stroke:#000,stroke-width:2px,color:#FFF

    Start(["Request loop"]):::entry --> Setup["Select bearings + shape configs"]:::process
    Setup --> Try["Project → Snap → Try polygon"]:::process
    Try --> Dist{"Within tolerance?"}:::decision

    Dist -->|"Yes"| Accept["Store candidate"]:::success
    Dist -->|"No"| Fallback["Run Retry/Fallback Subroutine (Level 2)"]:::process
    Fallback --> ReturnCandidate["Candidate accepted or bearing abandoned"]:::process

    Accept --> Next{"More bearings?"}:::decision
    ReturnCandidate --> Next

    Next -->|"Yes"| Try
    Next -->|"No"| Select["Select top-K diverse candidates"]:::process --> Result(["Return K routes"]):::entry
```

## Level 2: Retry + Out-and-Back Subroutine

```mermaid
flowchart TD
    classDef process fill:#0072B2,stroke:#000,stroke-width:2px,color:#FFF
    classDef decision fill:#CC79A7,stroke:#000,stroke-width:2px,color:#000
    classDef success fill:#009E73,stroke:#000,stroke-width:2px,color:#FFF
    classDef fail fill:#D55E00,stroke:#000,stroke-width:2px,color:#FFF
    classDef feedback fill:#56B4E9,stroke:#000,stroke-width:2px,color:#000
    classDef entry fill:#E69F00,stroke:#000,stroke-width:2px,color:#000

    In(["Entered due to distance miss"]):::entry --> Retry{"retry < 5?"}:::decision
    Retry -->|"Yes"| Tau["τ_new = τ × clamp(actual/target, 0.85, 1.15)"]:::feedback
    Tau --> ReTry["Regenerate waypoints + reroute"]:::process --> Dist2{"Within -5%/+15%?"}:::decision
    Dist2 -->|"Yes"| Acc["Accept candidate"]:::success --> Out(["Return accepted candidate"]):::entry
    Dist2 -->|"No"| Retry

    Retry -->|"No"| OAB["Try out-and-back"]:::process --> OABDist{"Within tolerance?"}:::decision
    OABDist -->|"Yes"| OABAcc["Accept out-and-back"]:::success --> Out
    OABDist -->|"No"| Rej["Abandon bearing"]:::fail --> Out2(["Return bearing abandoned"]):::entry
```

## Notes

- This method is usually easiest to read at A4 because each figure has lower node count.
- Level 1 communicates full algorithm sequence; Level 2 preserves exact retry semantics.
