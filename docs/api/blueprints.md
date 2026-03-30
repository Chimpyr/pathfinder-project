# Flask Blueprints

> How the ScenicPathFinder Flask application is organized.

---

## Overview

Flask Blueprints are modular components that group related routes and views. Instead of defining all routes in a single file, blueprints allow logical separation of concerns.

```
app/
├── routes.py           # Main blueprint (main pages + routing API)
└── blueprints/
    ├── __init__.py     # Blueprint registration
    ├── admin.py        # Admin dashboard and monitoring endpoints
    └── tasks.py        # Async task polling endpoints
```

---

## How Blueprints Work

### 1. Blueprint Definition

Each blueprint is created with a name and optional URL prefix:

```python
# app/blueprints/admin.py
from flask import Blueprint

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/')        # Becomes: GET /admin/
def dashboard():
    ...

@admin_bp.route('/cache')   # Becomes: GET /admin/cache
def cache_status():
    ...
```

### 2. Blueprint Registration

Blueprints are registered with the Flask app in `__init__.py`:

```python
# app/__init__.py
from flask import Flask
from app.routes import main
from app.blueprints.admin import admin_bp
from app.blueprints.tasks import tasks_bp

def create_app():
    app = Flask(__name__)

    # Register blueprints
    app.register_blueprint(main)           # No prefix - routes at /
    app.register_blueprint(admin_bp)       # Routes at /admin/*
    app.register_blueprint(tasks_bp)       # Routes at /api/task/*

    return app
```

### 3. URL Prefixes

| Blueprint  | Prefix      | Example Route              |
| ---------- | ----------- | -------------------------- |
| `main`     | (none)      | `GET /`, `POST /api/route` |
| `admin_bp` | `/admin`    | `GET /admin/cache`         |
| `tasks_bp` | `/api/task` | `GET /api/task/<id>`       |

---

## Blueprint Summary

### Main Blueprint (`routes.py`)

Core user-facing routes.

| Endpoint       | Method | Purpose                        |
| -------------- | ------ | ------------------------------ |
| `/`            | GET    | Render main map page           |
| `/api/geocode` | POST   | Convert address to coordinates |
| `/api/route`   | POST   | Calculate scenic route         |

### Admin Blueprint (`app/blueprints/admin.py`)

Development and monitoring endpoints.

| Endpoint              | Method | Purpose                      |
| --------------------- | ------ | ---------------------------- |
| `/admin/`             | GET    | Dashboard overview (HTML)    |
| `/admin/tasks/active` | GET    | Active Celery tasks (JSON)   |
| `/admin/cache`        | GET    | Cache statistics (JSON)      |
| `/admin/workers`      | GET    | Worker health info (JSON)    |
| `/admin/config`       | GET    | Current configuration (JSON) |

### Tasks Blueprint (`app/blueprints/tasks.py`)

Async task polling for graph building.

| Endpoint                     | Method | Purpose               |
| ---------------------------- | ------ | --------------------- |
| `/api/task/<task_id>`        | GET    | Get task status       |
| `/api/task/<task_id>/cancel` | POST   | Cancel a running task |

---

## Adding a New Blueprint

1. Create new file in `app/blueprints/`:

   ```python
   # app/blueprints/my_feature.py
   from flask import Blueprint, jsonify

   my_feature_bp = Blueprint('my_feature', __name__, url_prefix='/my-feature')

   @my_feature_bp.route('/status')
   def status():
       return jsonify({'status': 'ok'})
   ```

2. Register in `app/__init__.py`:

   ```python
   from app.blueprints.my_feature import my_feature_bp
   app.register_blueprint(my_feature_bp)
   ```

3. Endpoint is now available at: `GET /my-feature/status`

---

## See Also

- [API Reference](api_reference.md) - Complete endpoint documentation
- [Celery Redis Architecture](../architecture/celery_redis_architecture.md) - Async task flow
