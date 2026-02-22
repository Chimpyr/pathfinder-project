# ADR-012: Dual-Database Segregation for User Persistence

**Status:** Accepted  
**Date:** 2026-02-22

---

## Context

ScenicPathFinder requires server-side persistence for user accounts, saved locations, and routing preferences. The existing PostGIS container (`scenic-db`) already hosts a database (`scenic_tiles`) that stores volatile OpenStreetMap data — specifically street lighting vector tiles imported by `osm2pgsql`.

User data is fundamentally different from OSM routing data:

| Characteristic | OSM Data (`scenic_tiles`) | User Data (`user_db`) |
|----------------|--------------------------|----------------------|
| **Volatility** | Rebuilt from PBF files; disposable | Persistent; irreplaceable |
| **Schema owner** | `osm2pgsql` (external tool) | Our ORM (SQLAlchemy) |
| **Backup strategy** | Re-import from Geofabrik | `pg_dump` required |
| **Migration tool** | None (recreated from scratch) | Alembic (Flask-Migrate) |

Mixing these two concerns in a single database creates several risks:
1. Accidental data loss when `osm2pgsql --create` wipes tables
2. Alembic autogenerate detecting spatial extension tables (`spatial_ref_sys`, `planet_osm_*`) and generating destructive migration scripts
3. Backup complexity — `pg_dump` of the full database would include multi-GB OSM data unnecessarily

### Alternative Considered: Separate Schema

Using a separate PostgreSQL **schema** (`CREATE SCHEMA user_data`) inside the existing `scenic_tiles` database would halve connection pool overhead (one connection can access multiple schemas) and permit cross-schema JOINs.

However, this approach was rejected because:
- `osm2pgsql --create` drops and recreates the `public` schema, and misconfiguration could affect a co-located schema
- Alembic's introspection would still discover the spatial tables unless carefully filtered
- Independent `pg_dump` targeting is more complex with schemas than with separate databases

---

## Decision

**Create a second PostgreSQL database (`user_db`) on the same PostGIS container**, hosted alongside `scenic_tiles` but completely isolated at the database boundary level.

### Implementation

- Flask-SQLAlchemy connects to `user_db` via `SQLALCHEMY_DATABASE_URI`
- The existing `scenic_tiles` database continues to serve Martin tileserver and `osm2pgsql` without any coupling
- No SQLAlchemy `SQLALCHEMY_BINDS` are needed — the application only connects to `user_db` via ORM; `scenic_tiles` is accessed exclusively by Martin and the seeder container

### Connection String

```python
SQLALCHEMY_DATABASE_URI = "postgresql://{user}:{password}@{host}:{port}/user_db"
```

---

## Consequences

### Positive

- **Blast radius isolation** — `osm2pgsql --create` on `scenic_tiles` cannot affect `user_db`
- **Simple targeted backups** — `pg_dump user_db` captures only user state
- **Clean Alembic scope** — Alembic only sees `user_db` metadata, never the spatial tables
- **Independent lifecycle** — `user_db` can be backed up, restored, or migrated without touching routing infrastructure

### Negative

- **Additional database overhead** — PostgreSQL allocates separate shared buffers and catalogue per database, using marginally more memory
- **No cross-database JOINs** — Any logic comparing user pins against routing spatial data must be handled in the Python application layer (see ADR-016)
- **Connection pool duplication** — Each process maintains a separate connection pool for `user_db` (mitigated via pool tuning — see ADR-015)

---

## Files Modified

| File | Changes |
|------|---------|
| `config.py` | Added `SQLALCHEMY_DATABASE_URI` pointing to `user_db` |
| `docker-compose.yml` | Added `POSTGRES_DB_HOST`, `USER_DB_NAME` env vars to api/worker services |
| `.env` / `.env.example` | Added `USER_DB_NAME=user_db` |
| `app/__init__.py` | Initialises SQLAlchemy against `user_db` URI |

---

## References

- [PostgreSQL CREATE DATABASE](https://www.postgresql.org/docs/current/sql-createdatabase.html)
- [Flask-SQLAlchemy Configuration](https://flask-sqlalchemy.readthedocs.io/en/stable/config/)
- [ADR-013: Automated Database Bootstrapping](ADR-013-automated-database-bootstrapping.md) — How `user_db` is created
- [ADR-015: Connection Pool Tuning](ADR-015-connection-pool-tuning.md) — Mitigating pool overhead
