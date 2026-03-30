# Async Request Flow Sequence Diagram

This sequence diagram illustrates the decoupled architecture of the Scenic Pathfinding Engine. The full flow is split across three diagrams for A4 readability: this **overview** plus **Detail A** (Enqueue & Lock) and **Detail B** (Async Graph Build).

---

## Overview — Three-Phase Request Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Client as Web Client
    participant Flask as Flask API
    participant Redis as Redis
    participant Disk as Pickle Cache

    rect rgb(230, 159, 0)
        Note over Client,Flask: Phase 1 — Cold Cache Request
        Client->>Flask: POST /api/route (start, end, weights)
        Flask->>Disk: is_cache_valid()?
        Disk-->>Flask: False — tile missing
        Flask-->>Client: 202 Accepted (task_id)
        Note over Flask,Redis: See Detail A — Enqueue and Lock
    end

    rect rgb(86, 180, 233)
        Note over Client,Redis: Phase 2 — Async Build and Polling
        loop Poll every 3s
            Client->>Flask: GET /api/task/{task_id}
            Flask->>Redis: AsyncResult(task_id).state
            Redis-->>Flask: PENDING or BUILDING
            Flask-->>Client: 200 OK status: building
        end
        Note over Redis: See Detail B — Async Graph Build
        Client->>Flask: GET /api/task/{task_id}
        Flask->>Redis: AsyncResult(task_id).state
        Redis-->>Flask: SUCCESS
        Flask-->>Client: 200 OK status: complete
    end

    rect rgb(0, 158, 115)
        Note over Client,Disk: Phase 3 — Fast-Path Cache Hit
        Client->>Flask: POST /api/route (start, end, weights)
        Flask->>Disk: is_cache_valid()?
        Disk-->>Flask: True — graph ready
        Flask->>Disk: get_graph_for_route()
        Disk-->>Flask: NetworkX graph (deserialised)
        Flask->>Flask: Execute WSM A* pathfinding
        Flask-->>Client: 200 OK (route_coords, stats)
    end
```

---

## Detail A — Enqueue and Redis Lock

Expands Phase 1, Steps 4–5. Shows how `TaskManager` prevents duplicate concurrent tile builds via a Redis `setex` lock (NFR-03).

```mermaid
sequenceDiagram
    autonumber
    participant Flask as Flask API
    participant TM as TaskManager
    participant Redis as Redis (Broker + Locks)

    Flask->>TM: enqueue_tile_build(tile_id, region)
    TM->>Redis: GET building_tile:region:tile_id
    Redis-->>TM: None (no existing lock)
    TM->>Redis: LPUSH — push build_tile_task to Celery queue
    TM->>Redis: SETEX building_tile:region:tile_id lock_timeout task_id
    TM-->>Flask: Return task_id
    Flask-->>Flask: (Already returned 202 to client)
```

> **Concurrency note (ADR-005):** If a second request arrives for the same tile while the lock exists, `GET building_tile:…` returns the existing `task_id`. No duplicate task is enqueued — all concurrent callers poll the same Celery job.

---

## Detail B — Async Graph Build

Expands Phase 2 background work. Shows the Celery worker parsing `.pbf`, building the graph, and releasing the Redis lock.

```mermaid
sequenceDiagram
    autonumber
    participant Redis as Redis
    participant Celery as Celery Worker
    participant Disk as Pickle Cache (Disk)
    participant TM as TaskManager

    Redis->>Celery: Dispatch build_tile_task
    Celery->>Disk: Parse .pbf via pyrosm (no PostGIS)
    Disk-->>Celery: Raw spatial features (parks, lights, water)
    Celery->>Celery: build_graph() — interpolate WSM edge weights
    Celery->>Disk: save_graph() — Pickle serialise NetworkX graph
    Disk-->>Celery: Write confirmed
    Celery->>TM: clear_tile_lock(tile_id)
    TM->>Redis: DEL building_tile:region:tile_id
    Celery->>Redis: Set AsyncResult state = SUCCESS
```

> **Decoupling rationale:** `build_graph()` takes 60–120 seconds for large regions. Offloading to Celery means the Flask API never blocks, achieving NFR-01 (warm-cache sub-2s) alongside NFR-02 (build under 120s).

---

## Architectural Justification

- **Decoupling:** The heavy `build_graph()` process (parsing OSM `.pbf` via `pyrosm`) can take over 60 seconds. Offloading to Celery means Flask never blocks or hits a gateway timeout.
- **Concurrency Control (ADR-005):** The `TaskManager` Redis lock guarantees NFR-03: 4 concurrent requests for the same uncached tile result in exactly 1 Celery task execution.
- **Polling:** The client polls actively (Phase 2), providing UI feedback rather than a frozen page.
- **Caching Strategy (ADR-007):** Phase 3 leverages the graph written by the worker. Flask immediately enters memory-bound A\* traversal, achieving the sub-2-second NFR-01 goal.
