# 1. Asynchronous Architecture Data Flow

**Section:** High-Level System Architecture
**Purpose:** Visualises the decoupled nature of the client, the API gateway, the Redis broker, and the Celery workers, alongside dual-database segregation. Uses Okabe-Ito colour palette and distinct shapes per tier for accessibility.

```mermaid
flowchart TB
 subgraph Tier1["Tier 1: Client"]
    direction TB
        Frontend(["Leaflet.js Frontend UI"])
        Polling(["Async Polling Logic"])
  end
 subgraph Tier2["Tier 2: API Gateway & Routing"]
        Flask["Flask REST API (Executes WSM A* Engine)"]
  end
 subgraph Tier3["Tier 3: Async Queue"]
        Redis[/"Redis Job Queue"\]
  end
 subgraph Tier4["Tier 4: Background Computation Unit"]
        Celery{{"Celery Workers (Async Graph Builder)"}}
        GeoPandas[["GeoPandas / pyrosm (In-Memory Spatial Data)"]]
  end
 subgraph Tier5["Tier 5: Distributed Storage Segregation"]
    direction LR
        UserDB[("PostgreSQL (Persistent User Data)")]
        Cache[("Hybrid Cache (LRU In-Memory &amp; Pickle)")]
        PostGIS[("PostGIS / Martin (Dynamic Vector Tiles)")]
  end
    Frontend <-- User Interaction --> Polling
    Polling -- "1. POST Route Parameters" --> Flask
    Flask -. "2. Return Task ID \n (Non-blocking if cache miss)" .-> Polling
    Polling -- "3. Repeated GET /status \n (Polling)" --> Flask
    PostGIS -. "Dynamic Map Overlays \n (e.g. Streetlights)" .-> Frontend
    Flask -- "4. Enqueue Tile Build Job" --> Redis
    Redis -- "5. Distribute Job" --> Celery
    Celery -. "6. Publish Progress Updates" .-> Redis
    Cache -- Load Processed Graph Tiles --> Flask
    Flask -- Save Completed Route --> UserDB
    Celery <-- "7. Extract/Parse OSM \n .PBF Extracts" --> GeoPandas
    Celery -- "8. Save Preprocessed Graph Tiles" --> Cache

     Frontend:::client
     Polling:::client
     Flask:::api
     Redis:::broker
     Celery:::processing
     GeoPandas:::processing
     UserDB:::db
     Cache:::cache
     PostGIS:::db
    classDef client fill:#56B4E9,stroke:#000000,stroke-width:2px,color:#000000
    classDef api fill:#0072B2,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef broker fill:#E69F00,stroke:#000000,stroke-width:2px,color:#000000
    classDef processing fill:#D55E00,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef db fill:#009E73,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef cache fill:#CC79A7,stroke:#000000,stroke-width:2px,color:#FFFFFF
```
