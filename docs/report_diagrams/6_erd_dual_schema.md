# Entity-Relationship Diagram (ERD)

This diagram illustrates the dual-database architecture of the Scenic Pathfinding Engine. It highlights the strict boundary between the `user_db` (managed by SQLAlchemy and Alembic) and the `spatial_db` (managed by osm2pgsql and PostGIS).

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
        Float end_lat
        Float end_lon
        JSON weights_json
        JSON route_geometry
        Float distance_km
        Boolean is_loop
        DateTime created_at
    }

    %% Relationships in user_db
    User ||--o{ SavedPin : "owns"
    User ||--o{ SavedQuery : "owns"

    %% POSTGIS DB SCHEMA (osm2pgsql structure)
    planet_osm_point {
        BigInt osm_id PK
        Geometry way "Point (EPSG:3857)"
        String name
        Text amenity
        Text highway
        HStore tags
    }

    planet_osm_line {
        BigInt osm_id PK
        Geometry way "LineString/Polygon"
        String name
        Text highway
        Text surface
        HStore tags
    }

    planet_osm_polygon {
        BigInt osm_id PK
        Geometry way "Polygon"
        String name
        Text landuse
        Text leisure
        HStore tags
    }

    planet_osm_roads {
        BigInt osm_id PK
        Geometry way "LineString"
        String name
        Text highway
        HStore tags
    }

    %% STRICT BOUNDARY NOTE
    %% There are NO relationships drawn between user_db and spatial_db
```

## Architectural Justification (Dual-Schema Segregation)
As detailed in **ADR-012**, the architecture deliberately physically segregates the User Database from the Spatial Database. 

Notice in the ERD that there are **no foreign key relationships** crossing between the tables. 
*   **The `user_db`** is entirely stateless geographically. A `SavedPin` stores raw `Float` coordinates rather than heavy PostGIS `Geometry` types. It is strictly tied to the Flask application layer and managed gracefully via Flask-Migrate (Alembic) schema migrations.
*   **The `spatial_db`** is volatile and exists purely for visual rendering. The `planet_osm_*` tables are routinely destroyed and re-created from scratch whenever a new `.pbf` map file is ingested via `osm2pgsql`. If User Data was stored alongside this, a routine map update could catastrophically wipe all user accounts.

Because of this strict segregation, the Flask Python backend **never queries PostGIS directly**. Instead:
1.  **Graph Building (Offline Routing):** Celery workers natively parse local `.pbf` files into memory using `pyrosm` to build NetworkX routing matrices.
2.  **Visual Overlays (Frontend):** The `spatial_db` (PostGIS) is exclusively queried by the containerised **Martin** tileserver, which streams Mapbox Vector Tiles (MVT) representing streetlights and greenery directly to the client's browser layer. 

This extreme decoupling ensures the pathfinding logic remains completely independent from the visual rendering pipeline, preventing complex SQL joins and avoiding ORM mapping overheads for billions of OSM nodes.
