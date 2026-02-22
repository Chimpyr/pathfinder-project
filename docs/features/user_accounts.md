# User Accounts & Authentication

This document describes the user account system for ScenicPathFinder, covering registration, login, session management, and security.

---

## Overview

The application provides optional user accounts to enable persistent data (saved pins, saved routes, routing preferences). Authentication is session-based using Flask-Login, with passwords hashed using `werkzeug.security`.

Users who do not register can still use all routing features — accounts only gate data persistence.

---

## Architecture

```
┌────────────────┐      POST /auth/register       ┌──────────────┐
│    Frontend    │ ──────────────────────────────→ │  auth.py     │
│                │      POST /auth/login           │  Blueprint   │
│   (JS fetch)  │ ──────────────────────────────→ │              │
│                │      POST /auth/logout          │              │
│                │ ──────────────────────────────→ │              │
│                │      GET  /auth/me              │              │
│                │ ──────────────────────────────→ │              │
└────────────────┘                                 └──────┬───────┘
                                                          │
                                                          ▼
                                                   ┌──────────────┐
                                                   │   user_db    │
                                                   │  (PostGIS)   │
                                                   │              │
                                                   │  users table │
                                                   └──────────────┘
```

---

## API Endpoints

### `POST /auth/register`

Create a new user account.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Responses:**
| Code | Meaning |
|------|---------|
| 201 | Account created, user logged in |
| 400 | Invalid email or password < 8 chars |
| 409 | Email already registered |

---

### `POST /auth/login`

Authenticate and create a session.

**Request:**
```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "remember": true
}
```

**Responses:**
| Code | Meaning |
|------|---------|
| 200 | Logged in, session cookie set |
| 401 | Invalid email or password |

---

### `POST /auth/logout`

Clear the current session. Requires authentication.

**Response:** `200 {"message": "Logged out"}`

---

### `GET /auth/me`

Return the currently authenticated user's profile. Requires authentication.

**Response:**
```json
{
  "user": {
    "id": 1,
    "email": "user@example.com",
    "created_at": "2026-02-22T17:00:00+00:00"
  }
}
```

---

## Security Model

### Password Hashing

Passwords are hashed using `werkzeug.security.generate_password_hash()` with the default PBKDF2-SHA256 algorithm and random salt. Plain-text passwords **never** touch the database or ORM session.

```python
user.set_password("securepassword123")
# Stores: "pbkdf2:sha256:600000$salt$hash"

user.check_password("securepassword123")  # → True
```

### Session Management

Flask-Login manages session state via signed cookies (using `SECRET_KEY`). The `user_loader` callback retrieves the user from `user_db` by primary key on each request.

### Input Validation

| Field | Rule |
|-------|------|
| Email | Must contain `@`, normalised to lowercase, trimmed |
| Password | Minimum 8 characters |

### Protected Endpoints

All data endpoints (`/api/pins`, `/api/routes`) are decorated with `@login_required`. Unauthenticated requests receive a `401 Unauthorized` response.

---

## Data Model

See [User model](../../app/models/user.py):

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | Integer | Primary Key, auto-increment |
| `email` | String(254) | Unique, indexed, not null |
| `password_hash` | String(256) | Not null |
| `created_at` | DateTime | UTC, auto-set on creation |

### Relationships

- `User` → `SavedPin` (one-to-many, cascade delete)
- `User` → `SavedRoute` (one-to-many, cascade delete)

---

## Related Documentation

- [Saved Data (Pins & Routes)](saved_data.md) — CRUD endpoints for user-saved data
- [ADR-012: Dual-Database Segregation](../decisions/ADR-012-dual-database-segregation.md) — Why user data lives in a separate database
- [ADR-013: Automated Bootstrapping](../decisions/ADR-013-automated-database-bootstrapping.md) — How the database is auto-created
