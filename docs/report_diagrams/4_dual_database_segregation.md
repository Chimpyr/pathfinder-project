# 4. Dual-Database Segregation Boundary

**Section:** High-Level System Architecture  
**Purpose:** Illustrates the strict physical separation between the **volatile spatial database** (PostGIS / `scenic_tiles`) and the **persistent user database** (PostgreSQL / `user_db`). No data flows cross the boundary. The Celery graph-building pipeline bypasses PostGIS entirely, using `pyrosm` to parse local `.pbf` files directly.

**Sources:**

- [`docker-compose.yml`](../../docker-compose.yml) — service definitions: `db` (PostGIS), `tileserver` (Martin), `seeder` (osm2pgsql), `api` (Flask), `worker` (Celery), `redis`
- [`config.py`](../../config.py#L20) — `SQLALCHEMY_DATABASE_URI` points to `user_db`; no SQLAlchemy bind to `scenic_tiles`
- [ADR-012: Dual-Database Segregation](../../docs/decisions/ADR-012-dual-database-segregation.md)

```mermaid
flowchart TD
    classDef volatile fill:#D55E00,stroke:#000,stroke-width:2px,color:#FFF
    classDef persistent fill:#0072B2,stroke:#000,stroke-width:2px,color:#FFF
    classDef neutral fill:#56B4E9,stroke:#000,stroke-width:2px,color:#000
    classDef client fill:#E69F00,stroke:#000,stroke-width:2px,color:#000
    classDef cache fill:#009E73,stroke:#000,stroke-width:2px,color:#FFF

    %% ══════════════════════════════════════
    %%  VOLATILE  (Spatial / Rendering)
    %% ══════════════════════════════════════
    subgraph VOLATILE ["Volatile — Spatial Rendering (scenic_tiles)"]
        direction LR
        PBF["Local .pbf (OSM extract)"]:::volatile
        Seeder["osm2pgsql seeder"]:::volatile
        PostGIS[("PostGIS scenic_tiles")]:::volatile
        Martin["Martin Tile Server (Port 3000)"]:::volatile

        PBF -->|"DROP + CREATE"| Seeder
        Seeder -->|"Write spatial tables"| PostGIS
        PostGIS -->|"ST_AsMVT read-only"| Martin
    end

    %% ══════════════════════════════════════
    %%  CLIENT
    %% ══════════════════════════════════════
    Client(["Web Client (Leaflet.js)"]):::client

    Martin -->|"MVT vector tiles"| Client
    Client -->|"API requests"| FlaskAPI

    %% ══════════════════════════════════════
    %%  PERSISTENT  (User / Application Data)
    %% ══════════════════════════════════════
    subgraph PERSISTENT ["Persistent — User Data (user_db)"]
        direction LR
        FlaskAPI["Flask API (Port 5001)"]:::persistent
        ORM["SQLAlchemy ORM + Alembic"]:::persistent
        UserDB[("PostgreSQL user_db")]:::persistent

        FlaskAPI <-->|"CRUD"| ORM
        ORM <-->|"Migrations"| UserDB
    end

    %% ══════════════════════════════════════
    %%  CELERY  (Bypasses PostGIS entirely)
    %% ══════════════════════════════════════
    subgraph CELERY ["Celery Graph-Building Pipeline"]
        direction LR
        Redis[("Redis Broker (Port 6379)")]:::neutral
        Worker["Celery Worker (pyrosm)"]:::neutral
        PickleCache["Pickle Cache (/app/data/)"]:::cache

        Redis -->|"Dispatch task"| Worker
        Worker -->|"Parse .pbf (no PostGIS)"| PickleCache
    end

    %% ── Celery ↔ Flask ───────────────────
    FlaskAPI -->|"enqueue_tile_build()"| Redis
    PickleCache -->|"Load cached graph"| FlaskAPI

    %% NOTE: No edges cross VOLATILE / PERSISTENT boundary.
    %% osm2pgsql can DROP all spatial tables without affecting user_db.
```

## Blast Radius Isolation

The core architectural invariant is:

> **No data flows cross the boundary between `scenic_tiles` and `user_db`.**

This means:

1. The `osm2pgsql` seeder can aggressively `DROP` and recreate all `planet_osm_*` tables during a map update without any risk to user accounts, saved routes, or saved pins.
2. The Flask API's `SQLALCHEMY_DATABASE_URI` points **only** to `user_db` — there is no SQLAlchemy bind to the spatial database.
3. Celery workers parse `.pbf` files locally via `pyrosm` and write pickle-serialised NetworkX graphs to a shared disk volume — PostGIS is never queried during graph building.
4. PostGIS is **exclusively** consumed by the Martin tile server for read-only Mapbox Vector Tile (MVT) generation, streamed directly to the client's Leaflet map layer.
