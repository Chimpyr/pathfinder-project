# ADR-015: Connection Pool Tuning for Dual-Database Architecture

**Status:** Accepted  
**Date:** 2026-02-22

---

## Context

With the introduction of `user_db` ([ADR-012](ADR-012-dual-database-segregation.md)), the Flask application maintains a SQLAlchemy connection pool to the user database. PostgreSQL has a hard limit on concurrent connections (default: `max_connections = 100`). Other services on the same PostGIS container (Martin tileserver, seeder) also consume connections.

### Connection Consumers

| Service | Processes | Pools per Process | Connections per Pool | Max Connections |
|---------|-----------|-------------------|---------------------|-----------------|
| **api** (Flask) | 1 | 1 (`user_db`) | pool_size + max_overflow | 5 |
| **worker** (Celery) | 4 | 1 (`user_db`) | pool_size + max_overflow | 20 |
| **tileserver** (Martin) | 1 | 1 (`scenic_tiles`) | internal pool | ~10 |
| **seeder** (osm2pgsql) | 1 (ephemeral) | 1 (`scenic_tiles`) | 1 | 1 |
| **PostgreSQL internals** | — | — | — | ~3 |

Without tuning, SQLAlchemy's default pool (`pool_size=5`, `max_overflow=10`) would create up to 15 connections per process, totalling 75 connections from the API + workers alone — dangerously close to the 100 limit.

---

## Decision

**Set conservative pool parameters explicitly in `SQLALCHEMY_ENGINE_OPTIONS`:**

```python
SQLALCHEMY_ENGINE_OPTIONS = {
    'pool_size': 3,        # Steady-state connections per process
    'max_overflow': 2,     # Burst connections above pool_size
    'pool_pre_ping': True, # Detect stale connections before use
}
```

### Arithmetic

```
API:      1 process  × (3 + 2) = 5 connections
Workers:  4 processes × (3 + 2) = 20 connections
─────────────────────────────────
Total user_db:           25 connections (worst case)
Martin + seeder + PG:   ~14 connections
─────────────────────────────────
Grand total:            ~39 connections (39% of max 100)
```

This leaves a **61-connection headroom** for additional workers, debugging connections, or future services.

### `pool_pre_ping`

Enables a lightweight `SELECT 1` health check before reusing a pooled connection. This prevents `OperationalError: server closed the connection unexpectedly` after PostgreSQL restarts or idle connection timeouts, at a cost of ~1ms per checkout.

---

## Consequences

### Positive

- **Safe margin** — Peak usage stays well below `max_connections`
- **Predictable behaviour** — Explicit configuration prevents surprises from SQLAlchemy defaults
- **Resilient** — `pool_pre_ping` handles PostgreSQL restarts gracefully
- **Scalable** — Clear arithmetic makes it easy to adjust when adding workers

### Negative

- **Lower burst capacity** — `max_overflow=2` limits concurrent request handling during traffic spikes (mitigated by Flask's single-threaded nature per request)
- **Queuing under load** — If all 5 connections are busy, new requests wait for a free connection (acceptable at current scale)

---

## Alternatives Considered

1. **Use PgBouncer as a connection proxy** — Would multiplex many application connections through fewer PostgreSQL connections. Rejected as premature optimisation; the current arithmetic comfortably fits within limits without adding infrastructure.

2. **NullPool (no pooling)** — Create and destroy connections per request. Rejected due to TCP/TLS handshake overhead (~5-15ms per connection vs ~0ms from pool).

3. **Increase PostgreSQL max_connections** — Change the PostgreSQL config to 200+. Rejected because higher limits increase PostgreSQL memory usage (each connection allocates ~5MB of working memory), and the current architecture doesn't warrant it.

---

## Files Modified

| File | Changes |
|------|---------|
| `config.py` | Added `SQLALCHEMY_ENGINE_OPTIONS` with tuned pool parameters |

---

## References

- [SQLAlchemy Connection Pool Configuration](https://docs.sqlalchemy.org/en/20/core/engines.html#engine-creation-api)
- [PostgreSQL max_connections](https://www.postgresql.org/docs/current/runtime-config-connection.html)
- [ADR-012: Dual-Database Segregation](ADR-012-dual-database-segregation.md)
