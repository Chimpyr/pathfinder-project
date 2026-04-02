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

**System dependencies** — Installs geospatial libraries (GEOS, PROJ, GDAL) and `osmium-tool`. The `osmium-tool` is essential for pre-extracting bounding box regions to prevent out-of-memory errors on large PBF files. Cleanup at end reduces image size.

```dockerfile
COPY requirements.txt .
RUN echo 'setuptools<70' > /tmp/constraints.txt && ...
```

**Layer caching & Workarounds** — Copies dependencies first so pip install is cached. The `setuptools<70` pip constraint is a workaround for `pyrosm`/`pyrobuf` compatibility issues during build isolation.

```dockerfile
COPY . .
```

**Copy code** — Done last so code edits don't invalidate pip cache.

```dockerfile
EXPOSE 5000
```

**Documentation only** — Says "this container listens on 5000". Does NOT publish the port — that's done in `docker-compose.yml` with `ports:`.

```dockerfile
CMD ["python", "run.py"]
```

**Default command** — Runs Flask. Override in `docker-compose.yml` for workers.

---

## docker-compose.yml Architecture

ScenicPathFinder is broken into multiple microservices:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             Host Machine                                    │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌──────────┐                     │
│  │  Redis  │◄─►│   API   │◄─►│ Worker  │   │  Flower  │ (Optional Profile)  │
│  │  :6379  │   │  :5001  │   │         │   │  :5555   │                     │
│  └────┬────┘   └────┬────┘   └────┬────┘   └──────────┘                     │
│       │             │             │                                         │
│       └─────────────┴──────┬──────┘                                         │
│                            │                                                │
│         ┌────────────┐     │        ┌────────────┐                          │
│         │   Martin   │◄────┤        │  pgAdmin   │                          │
│         │ Tileserver │     │        │   :5050    │                          │
│         │   :3000    │     ▼        └──────┬─────┘                          │
│         └──────┬─────┘  ┌─────────┐        │                                │
│                └───────►│ PostGIS │◄───────┘                                │
│                         │  :5432  │◄────┐                                   │
│                         └─────────┘     │  ┌─────────┐                      │
│                                         └──┤ Seeder  │ (Optional Profile)   │
│                                            └─────────┘                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Core Services**:

- **api:** The main Flask backend. Bound to port `5001` on the host to avoid default `5000` conflicts (like AirPlay on macOS).
- **worker:** Celery processes performing heavy graph building tasks async.
- **redis:** Message queue handling API-Worker communication.
- **db:** PostGIS instance storing geometry data for street lighting maps.
- **tileserver (Martin):** Serves Vector Tiles directly from PostGIS over HTTP.

---

## Port Mapping: `"5001:5000"`

Format: `HOST:CONTAINER`

```text
Browser → localhost:5001 → Container's internal port 5000
```

They CAN differ:

```yaml
ports:
  - "5001:5000" # Browser uses 5001, Flask inside uses 5000
```

---

## Volumes Explained

### Bind Mount (files you control)

```yaml
- ./app/data:/app/app/data
```

Format: `HOST_PATH:CONTAINER_PATH`

| Side              | Path            | Location                            |
| ----------------- | --------------- | ----------------------------------- |
| Left (host)       | `./app/data`    | `c:\...\ScenicPathFinder\app\data\` |
| Right (container) | `/app/app/data` | Inside container filesystem         |

The `.` is relative to `docker-compose.yml` location.

### Named Volume (Docker-managed)

```yaml
- redis_data:/data
```

**No `./` prefix** — Docker stores this internally (e.g., `C:\ProgramData\Docker\volumes\...`). You don't browse it directly.

| Type         | Syntax         | Use Case              |
| ------------ | -------------- | --------------------- |
| Bind mount   | `./path:/path` | Code/data you edit    |
| Named volume | `name:/path`   | Persistent DB storage |

---

## Why Two Cache Mounts?

```yaml
volumes:
  - ./app/data:/app/app/data # Explicit cache sharing
  - .:/app # Live code reload (dev only)
```

With `.:/app`, the entire project is mounted, making the first line redundant. But:

| Environment | `.:/app`              | `./app/data:/app/app/data` |
| ----------- | --------------------- | -------------------------- |
| Development | ✅ Keep (live reload) | Redundant but harmless     |
| Production  | ❌ Remove             | ✅ Keep (shared cache)     |

The explicit cache mount ensures API and Worker share graphs even when dev mount is removed.

---

## Profiles (Conditional Services)

Some services in `docker-compose.yml` are not started by default:

```yaml
profiles:
  - seed
```

You can start them manually with the `--profile` flag:

- **`docker-compose --profile seed up seeder`**: Triggers the one-off job that pushes `.pbf` data into PostGIS.
- **`docker-compose --profile monitoring up flower`**: Starts the Celery dashboard on `localhost:5555`.

---

## Service Communication

```yaml
environment:
  - CELERY_BROKER_URL=redis://redis:6379/0
  - POSTGRES_DB_HOST=db
```

`redis` and `db` in these variables are the **service names** — Docker's internal DNS resolves them to that container's IP inside the Docker network.

`/0` and `/1` in Redis URLs are database numbers (separate logical DBs).

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

| Directive      | Purpose                  |
| -------------- | ------------------------ |
| `image:`       | Use pre-built image      |
| `build:`       | Build from Dockerfile    |
| `ports: "A:B"` | Map host:container ports |
| `volumes:`     | Share/persist files      |
| `environment:` | Set env vars             |
| `depends_on:`  | Startup order            |
| `command:`     | Override CMD             |
| `profiles:`    | Optional services        |

---

## Mac ARM64 (Apple Silicon) Notes

Macs with M-series chips run `linux/arm64/v8`. Some Docker Hub images are **only built for `linux/amd64`** and will fail with:

```
no matching manifest for linux/arm64/v8 in the manifest list entries
```

### Known affected images in this project

| Image                           | Issue                 | Fix applied                                                             |
| ------------------------------- | --------------------- | ----------------------------------------------------------------------- |
| `postgis/postgis:16-3.5-alpine` | No ARM64 build at all | Switched to `postgis/postgis:16-3.5` (Debian) + `platform: linux/amd64` |

### The fix: `platform: linux/amd64`

Adding `platform: linux/amd64` to a service forces Docker to pull the x86 image. Docker Desktop on Apple Silicon runs it transparently via **Rosetta 2** emulation — no manual steps required.

```yaml
db:
  image: postgis/postgis:16-3.5
  platform: linux/amd64 # <-- forces amd64 emulation on Apple Silicon
```

### Why not use the `-alpine` tag?

`postgis/postgis:16-3.5-alpine` is only published for `linux/amd64`. The standard Debian-based `postgis/postgis:16-3.5` tag also only has an `amd64` manifest for this version, so `platform: linux/amd64` is still required. Clearing the Docker cache or daemon does **not** fix this — the image simply doesn't exist for ARM64.

### If another service hits the same error

Add `platform: linux/amd64` to that service block. Performance is slightly lower due to emulation, but it is functionally transparent for development use.
