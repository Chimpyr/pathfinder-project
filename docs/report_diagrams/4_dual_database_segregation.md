# 4. Dual-Database Segregation Boundary

**Section:** High-Level System Architecture  
**Purpose:** Illustrates the strict physical separation between the **volatile spatial database** (PostGIS / `scenic_tiles`) and the **persistent user database** (PostgreSQL / `user_db`). No data flows cross the boundary. The Celery graph-building pipeline bypasses PostGIS entirely, using `pyrosm` to parse local `.pbf` files directly.

**Sources:**

- [`docker-compose.yml`](../../docker-compose.yml) — service definitions: `db` (PostGIS), `tileserver` (Martin), `seeder` (osm2pgsql), `api` (Flask), `worker` (Celery), `redis`
- [`config.py`](../../config.py#L20) — `SQLALCHEMY_DATABASE_URI` points to `user_db`; no SQLAlchemy bind to `scenic_tiles`
- [ADR-012: Dual-Database Segregation](../../docs/decisions/ADR-012-dual-database-segregation.md)

```mermaid
flowchart LR
    classDef volatile fill:#D55E00,stroke:#000,stroke-width:2px,color:#FFF
    classDef persistent fill:#0072B2,stroke:#000,stroke-width:2px,color:#FFF
    classDef neutral fill:#56B4E9,stroke:#000,stroke-width:2px,color:#000
    classDef client fill:#E69F00,stroke:#000,stroke-width:2px,color:#000
    classDef cache fill:#009E73,stroke:#000,stroke-width:2px,color:#FFF
    classDef boundary stroke:#CC79A7,stroke-width:3px,stroke-dasharray:8 4

    %% ══════════════════════════════════════════════════════════════
    %%  LEFT: VOLATILE  (Spatial / Rendering Pipeline)
    %% ══════════════════════════════════════════════════════════════
    subgraph VOLATILE ["🔴 Volatile — Spatial Rendering (scenic_tiles)"]
        direction TB
        PBF["Local .pbf\n(OSM extract)"]:::volatile
        Seeder["osm2pgsql seeder\n(docker: scenic-seeder)"]:::volatile
        PostGIS[("PostGIS\nscenic_tiles DB\nplanet_osm_* tables")]:::volatile
        Martin["Martin Tile Server\n(docker: scenic-tileserver)\nPort 3000"]:::volatile

        PBF -->|"Import & flatten\n(DROP + CREATE)"| Seeder
        Seeder -->|"Write spatial tables"| PostGIS
        PostGIS -->|"ST_AsMVT\n(read-only)"| Martin
    end

    %% ══════════════════════════════════════════════════════════════
    %%  RIGHT: PERSISTENT  (User / Application Data)
    %% ══════════════════════════════════════════════════════════════
    subgraph PERSISTENT ["🔵 Persistent — User Data (user_db)"]
        direction TB
        FlaskAPI["Flask API\n(docker: scenic-api)\nPort 5001"]:::persistent
        ORM["SQLAlchemy ORM\n+ Alembic Migrations"]:::persistent
        UserDB[("PostgreSQL\nuser_db\nUser, SavedQuery, SavedPin")]:::persistent

        FlaskAPI <-->|"CRUD operations"| ORM
        ORM <-->|"Schema migrations"| UserDB
    end

    %% ══════════════════════════════════════════════════════════════
    %%  CELERY PIPELINE  (Bypasses PostGIS entirely)
    %% ══════════════════════════════════════════════════════════════
    subgraph CELERY ["⚡ Celery Graph-Building Pipeline"]
        direction TB
        Redis[("Redis\n(Broker & Locks)\nPort 6379")]:::neutral
        Worker["Celery Worker\n(docker: scenic-worker)\npyrosm parser"]:::neutral
        PickleCache["Pickle Cache\n(Shared Disk Volume)\n/app/data/"]:::cache
    end

    %% ── Celery flow (bypasses PostGIS) ───────────────────────────
    FlaskAPI -->|"enqueue_tile_build()"| Redis
    Redis -->|"Dispatch task"| Worker
    Worker -->|"Parse local .pbf\n(pyrosm — no PostGIS)"| PickleCache
    PickleCache -->|"Load cached graph\n(NetworkX pickle)"| FlaskAPI

    %% ── Client connections ───────────────────────────────────────
    Client(["Web Client\n(Leaflet.js)"]):::client
    Martin -->|"MVT vector tiles\n(street lighting overlay)"| Client
    Client -->|"API requests\n(routes, auth, saves)"| FlaskAPI

    %% ══════════════════════════════════════════════════════════════
    %%  BLAST RADIUS BOUNDARY  (No lines cross)
    %% ══════════════════════════════════════════════════════════════
    %% NOTE: There are deliberately NO edges between VOLATILE and
    %% PERSISTENT subgraphs. The Celery pipeline connects to Flask
    %% via disk cache, never via PostGIS. A full osm2pgsql re-import
    %% can DROP all spatial tables without affecting user_db.
```

## Blast Radius Isolation

The core architectural invariant is:

> **No data flows cross the boundary between `scenic_tiles` and `user_db`.**

This means:

1. The `osm2pgsql` seeder can aggressively `DROP` and recreate all `planet_osm_*` tables during a map update without any risk to user accounts, saved routes, or saved pins.
2. The Flask API's `SQLALCHEMY_DATABASE_URI` points **only** to `user_db` — there is no SQLAlchemy bind to the spatial database.
3. Celery workers parse `.pbf` files locally via `pyrosm` and write pickle-serialised NetworkX graphs to a shared disk volume — PostGIS is never queried during graph building.
4. PostGIS is **exclusively** consumed by the Martin tile server for read-only Mapbox Vector Tile (MVT) generation, streamed directly to the client's Leaflet map layer.
