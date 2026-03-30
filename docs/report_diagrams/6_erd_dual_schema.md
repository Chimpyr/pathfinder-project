# Entity-Relationship Diagram (ERD)

This diagram illustrates the dual-database architecture of the Scenic Pathfinding Engine. It highlights the strict boundary between the `user_db` (managed by SQLAlchemy and Alembic) and the `spatial_db` (managed by PostGIS overlay tables seeded from OSM/council sources).

```mermaid
erDiagram
    %% USER DB SCHEMA
    User {
        Integer id PK
        String email UK
        String password_hash
        DateTime created_at
    }

    SavedPin {
        Integer id PK
        Integer user_id FK
        String label
        Float latitude
        Float longitude
        DateTime created_at
    }

    SavedQuery {
        Integer id PK
        Integer user_id FK
        String name
        Float start_lat
        Float start_lon
        Float end_lat "nullable — loop routes share start"
        Float end_lon "nullable — loop routes share start"
        JSON weights_json
        JSON route_geometry
        Float distance_km
        Boolean is_loop
        DateTime created_at
    }

    %% NOTE: The report body may reference a "SavedRoute" model.
    %% No such model exists. SavedQuery fulfils this role via
    %% route_geometry (JSON) and is_loop (Boolean) columns.
    %% See: app/models/saved_query.py

    %% Relationships in user_db
    User ||--o{ SavedPin : "owns"
    User ||--o{ SavedQuery : "owns"

    %% POSTGIS DB SCHEMA (street-lighting overlay)
    council_streetlights_raw {
        Integer id PK
        Text source
        Text source_detail
        Text source_uid
        Text lit_status
        Text lighting_regime
        Text regime_text
        Geometry geom "Point (EPSG:3857)"
    }

    street_lighting {
        BigInt osm_id PK
        Text lit_status
        Text lit_source_primary
        Text lit_source_detail
        Text lit_tag_type
        Text lighting_regime
        Text lighting_regime_text
        Text osm_lit_raw
        Integer council_match_count
        Geometry geom "LineString (EPSG:3857)"
    }

    council_streetlights_raw ||--o{ street_lighting : "spatial match (ST_DWithin)"

    %% STRICT BOUNDARY NOTE
    %% There are NO relationships drawn between user_db and spatial_db
```

## Architectural Justification (Dual-Schema Segregation)

As detailed in **ADR-012**, the architecture deliberately physically segregates the User Database from the Spatial Database.

Notice in the ERD that there are **no foreign key relationships** crossing between the tables.

- **The `user_db`** is entirely stateless geographically. A `SavedPin` stores raw `Float` coordinates rather than heavy PostGIS `Geometry` types. It is strictly tied to the Flask application layer and managed gracefully via Flask-Migrate (Alembic) schema migrations.
- **The `spatial_db`** is volatile and exists purely for visual rendering. Seeder jobs can rebuild `street_lighting`, reload/update `council_streetlights_raw`, and refresh tile SQL functions without affecting user accounts. If user data was co-located, routine map-overlay refreshes could wipe account data.

Because of this strict segregation, the Flask Python backend **never queries PostGIS directly**. Instead:

1.  **Graph Building (Offline Routing):** Celery workers natively parse local `.pbf` files into memory using `pyrosm`, then enrich edges with council streetlight points before writing cached graphs.
2.  **Visual Overlays (Frontend):** The `spatial_db` (PostGIS) is exclusively queried by the containerised **Martin** tileserver, which streams Mapbox Vector Tiles (MVT) from `street_lighting` via `street_lighting_filtered(...)`.

**Why is there no strict FK between council points and street segments?**
The merge between `council_streetlights_raw` and `street_lighting` is spatial (`ST_DWithin`) rather than identity-based. A council point can match multiple nearby segments and many segments may have no council match. Provenance and match quality are preserved directly in `street_lighting` columns (`lit_source_primary`, `lit_source_detail`, `council_match_count`) instead of rigid relational foreign keys.

This extreme decoupling ensures the pathfinding logic remains completely independent from the visual rendering pipeline, preventing complex SQL joins and avoiding ORM mapping overheads for billions of OSM nodes.
