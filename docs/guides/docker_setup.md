# Docker Setup Guide

Understanding the Dockerfile and docker-compose.yml for ScenicPathFinder.

---

## Dockerfile Breakdown

```dockerfile
FROM python:3.11-slim
```
**Base image** — Starts from minimal Python 3.11 on Debian. `slim` reduces image size.

```dockerfile
WORKDIR /app
```
**Working directory** — Creates `/app` inside container, all commands run from here. Convention like using `src/` in code.

```dockerfile
RUN apt-get update && apt-get install -y ... && rm -rf /var/lib/apt/lists/*
```
**System dependencies** — Installs geospatial libraries (GEOS, PROJ, GDAL). Cleanup at end reduces image size.

```dockerfile
COPY requirements.txt .
RUN pip install -r requirements.txt
```
**Layer caching** — Copy deps first so pip install is cached. Code changes don't trigger reinstall.

```dockerfile
COPY . .
```
**Copy code** — Done last so code edits don't invalidate pip cache.

```dockerfile
EXPOSE 5000
```
**Documentation only** — Says "this container listens on 5000". Does NOT publish the port — that's done in docker-compose.yml with `ports:`.

```dockerfile
CMD ["python", "run.py"]
```
**Default command** — Runs Flask. Override in docker-compose for workers.

---

## docker-compose.yml Architecture

```
┌───────────────────────────────────────────────────────────┐
│                    Host Machine                           │
│  ┌─────────┐    ┌─────────┐    ┌─────────┐               │
│  │  Redis  │◄──►│   API   │◄──►│ Worker  │               │
│  │  :6379  │    │  :5000  │    │         │               │
│  └────┬────┘    └────┬────┘    └────┬────┘               │
│       │              │              │                     │
│       └──────────────┴──────────────┘                     │
│                      │                                    │
│              ./app/data (shared cache)                    │
└───────────────────────────────────────────────────────────┘
```

---

## Port Mapping: `"5000:5000"`

Format: `HOST:CONTAINER`

```
Browser → localhost:5000 → Container's port 5000
```

They CAN differ:
```yaml
ports:
  - "8080:5000"  # Browser uses 8080, Flask inside uses 5000
```

---

## Volumes Explained

### Bind Mount (files you control)

```yaml
- ./app/data:/app/app/data
```

Format: `HOST_PATH:CONTAINER_PATH`

| Side | Path | Location |
|------|------|----------|
| Left (host) | `./app/data` | `c:\...\ScenicPathFinder\app\data\` |
| Right (container) | `/app/app/data` | Inside container filesystem |

The `.` is relative to `docker-compose.yml` location.

### Named Volume (Docker-managed)

```yaml
- redis_data:/data
```

**No `./` prefix** — Docker stores this internally (e.g., `C:\ProgramData\Docker\volumes\...`). You don't browse it directly.

| Type | Syntax | Use Case |
|------|--------|----------|
| Bind mount | `./path:/path` | Code/data you edit |
| Named volume | `name:/path` | Persistent DB storage |

---

## Why Two Cache Mounts?

```yaml
volumes:
  - ./app/data:/app/app/data    # Explicit cache sharing
  - .:/app                       # Live code reload (dev only)
```

With `.:/app`, the entire project is mounted, making the first line redundant. But:

| Environment | `.:/app` | `./app/data:/app/app/data` |
|-------------|----------|---------------------------|
| Development | ✅ Keep (live reload) | Redundant but harmless |
| Production | ❌ Remove | ✅ Keep (shared cache) |

The explicit cache mount ensures API and Worker share graphs even when dev mount is removed.

---

## Service Communication

```yaml
environment:
  - CELERY_BROKER_URL=redis://redis:6379/0
```

`redis` in the URL is the **service name** — Docker's internal DNS resolves it to that container's IP.

`/0` and `/1` are Redis database numbers (separate logical DBs).

---

## Health Checks

```yaml
depends_on:
  redis:
    condition: service_healthy
```

API waits for Redis to pass its healthcheck (`redis-cli ping`) before starting. Prevents connection errors on startup.

---

## Quick Reference

| Directive | Purpose |
|-----------|---------|
| `image:` | Use pre-built image |
| `build:` | Build from Dockerfile |
| `ports: "A:B"` | Map host:container ports |
| `volumes:` | Share/persist files |
| `environment:` | Set env vars |
| `depends_on:` | Startup order |
| `command:` | Override CMD |
| `profiles:` | Optional services |