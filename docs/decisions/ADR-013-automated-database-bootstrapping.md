# ADR-013: Automated Database Bootstrapping

**Status:** Accepted  
**Date:** 2026-02-22

---

## Context

The `user_db` database (see [ADR-012](ADR-012-dual-database-segregation.md)) must exist on the PostGIS container before the Flask application can connect to it via SQLAlchemy. The Docker Compose `db` service only creates the database specified by `POSTGRES_DB` (which is `scenic_tiles`), leaving `user_db` uncreated.

### The Problem

Without an automated bootstrapping mechanism, deploying the application to a new environment requires a manual step:

```bash
docker exec scenic-db psql -U scenic -c "CREATE DATABASE user_db;"
```

This manual intervention:
1. **Breaks reproducibility** — a clean `docker compose up` on a new machine will fail
2. **Confuses new developers** — the error message (`FATAL: database "user_db" does not exist`) gives no guidance
3. **Prevents CI/CD automation** — any pipeline that starts from a blank volume will fail
4. **Violates Infrastructure-as-Code** — the system is not self-healing

### PostgreSQL Limitation

`CREATE DATABASE` cannot be executed inside a standard transactional block. Any implementation must use autocommit mode.

---

## Decision

**Implement a pre-flight Python bootstrap script (`scripts/db_bootstrap.py`) that runs before the Flask application fully initialises, using a raw `psycopg2` connection with autocommit isolation level.**

### Implementation

```python
def ensure_user_db():
    conn = psycopg2.connect(dbname='postgres', ...)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (user_db_name,))
    if not cursor.fetchone():
        cursor.execute(f'CREATE DATABASE "{user_db_name}"')
```

### Execution Sequence

```
docker compose up
  └─► scenic-db starts (healthcheck: pg_isready)
       └─► scenic-api starts
            └─► create_app() called
                 └─► ensure_user_db()           ← Bootstrap fires HERE
                      ├─ Connects to 'postgres' maintenance DB
                      ├─ Queries pg_database
                      ├─ CREATE DATABASE user_db (if missing)
                      └─ Returns
                 └─► db.init_app(app)           ← SQLAlchemy connects to user_db
                 └─► db.create_all()            ← Tables created
```

### Graceful Degradation

If PostgreSQL is unreachable (e.g., running locally without Docker), the script logs a warning and returns `False`. The application continues to serve routing features without user persistence — no crash, no exceptions propagated to the caller.

---

## Consequences

### Positive

- **Self-healing** — `docker compose down -v && docker compose up` works from scratch
- **Idempotent** — Safe to run on every startup; `SELECT 1 FROM pg_database` is a no-op if database exists
- **Zero-downtime for routing** — Failure to connect to PostgreSQL does not prevent A* routing from working
- **Developer-friendly** — No manual setup steps required

### Negative

- **Startup latency** — Adds ~50ms to application startup (single TCP connection + query)
- **psycopg2 dependency** — The raw driver is needed in addition to SQLAlchemy's ORM layer (already required by `psycopg2-binary`)

---

## Alternatives Considered

1. **Docker init script** — Mount a `.sql` file into `/docker-entrypoint-initdb.d/`. Rejected because this only runs on first container creation, not when a volume already exists but `user_db` was dropped.

2. **`POSTGRES_MULTIPLE_DATABASES` pattern** — A custom entrypoint script for the PostgreSQL container that creates multiple databases. Rejected because it requires a custom Docker image, complicating the existing `postgis/postgis:16-3.5-alpine` base.

3. **SQLAlchemy `create_engine` with `create_database`** — Using `sqlalchemy_utils.create_database()`. Rejected because it introduces another dependency and doesn't handle the autocommit requirement as transparently.

---

## Files Modified

| File | Changes |
|------|---------|
| `scripts/db_bootstrap.py` | **[NEW]** Bootstrap script with `ensure_user_db()` |
| `app/__init__.py` | Calls `ensure_user_db()` before `db.init_app(app)` |
| `docker-compose.yml` | Both `api` and `worker` depend on `db: service_healthy` |

---

## References

- [PostgreSQL CREATE DATABASE docs](https://www.postgresql.org/docs/current/sql-createdatabase.html)
- [psycopg2 isolation levels](https://www.psycopg.org/docs/extensions.html#isolation-level-constants)
- [ADR-012: Dual-Database Segregation](ADR-012-dual-database-segregation.md)
