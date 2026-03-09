# 1. Asynchronous Architecture Data Flow 

**Section:** High-Level System Architecture
**Purpose:** Visualises the decoupled nature of the client, the API gateway, the Redis broker, and the Celery workers, alongside dual-database segregation. Uses Okabe-Ito colour palette and distinct shapes per tier for accessibility.

```mermaid
flowchart TD
    %% Define Okabe-Ito Accessible Colour Palette
    classDef client fill:#56B4E9,stroke:#000000,stroke-width:2px,color:#000000
    classDef api fill:#0072B2,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef broker fill:#E69F00,stroke:#000000,stroke-width:2px,color:#000000
    classDef processing fill:#D55E00,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef db fill:#009E73,stroke:#000000,stroke-width:2px,color:#FFFFFF
    classDef cache fill:#CC79A7,stroke:#000000,stroke-width:2px,color:#FFFFFF

    %% Tier 1: Client Layer
    subgraph Tier1 [Tier 1: Client]
        direction TB
        Frontend(["Leaflet.js Frontend UI"]):::client
        Polling(["Async Polling Logic"]):::client
    end

    %% Tier 2: API Gateway & Pathfinding Layer
    subgraph Tier2 [Tier 2: API Gateway & Routing]
        Flask["Flask REST API \n (Executes WSM A* Engine)"]:::api
    end

    %% Tier 3: Message Broker Layer
    subgraph Tier3 [Tier 3: Async Queue]
        Redis[/"Redis Job Queue"\]:::broker
    end

    %% Tier 4: Pre-Processing Layer
    subgraph Tier4 [Tier 4: Background Computation Unit]
        Celery{{"Celery Workers \n (Async Graph Builder)"}}:::processing
        GeoPandas[["GeoPandas / pyrosm \n (In-Memory Spatial Data)"]]:::processing
    end

    %% Tier 5: Storage Layer
    subgraph Tier5 [Tier 5: Distributed Storage Segregation]
        direction LR
        UserDB[("PostgreSQL \n (Persistent User Data)")]:::db
        Cache[("Hybrid Cache \n (LRU In-Memory & Pickle)")]:::cache
        PostGIS[("PostGIS / Martin \n (Dynamic Vector Tiles)")]:::db
    end

    %% Client to API Connections
    Frontend <-->|"User Interaction"| Polling
    Polling -- "1. POST Route Parameters" --> Flask
    Flask -. "2. Return Task ID \n (Non-blocking if cache miss)" .-> Polling
    Polling -- "3. Repeated GET /status \n (Polling)" --> Flask
    
    %% Output direct to client
    PostGIS -. "Dynamic Map Overlays \n (e.g. Streetlights)" .-> Frontend
    
    %% Internal Backend Routing (Cache Miss)
    Flask -- "4. Enqueue Tile Build Job" --> Redis
    Redis -- "5. Distribute Job" --> Celery
    Celery -. "6. Publish Progress Updates" .-> Redis
    
    %% Fast Path Routing
    Cache -- "Load Processed Graph Tiles" --> Flask
    Flask -- "Save Completed Route" --> UserDB
    
    %% Computation to Storage Connections
    Celery <-->|"7. Extract/Parse OSM \n .PBF Extracts"| GeoPandas
    Celery -- "8. Save Preprocessed Graph Tiles" --> Cache
```
