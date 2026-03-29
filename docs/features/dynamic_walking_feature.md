# Dynamic Walking & Movement Preferences Feature

## Overview

The **Dynamic Walking & Movement Preferences** feature allows users to configure personal baseline travel modes to produce accurate ETAs, distance units, and effort estimates across their calculated routes.

Rather than relying on static global constants (e.g., standard 5.0 km/h walking speed), users can explicitly configure:

- Global distance unit toggles (`km` or `mi`)
- Walking Speed (km/h or mph)
- Running Speed (Easy / Recovery pace)
- Running Speed (Tempo / Race pace)

This user-defined profile cascades reactively across the entire application—dynamically updating route queries, UI element text, and rendering correct estimated times.

---

## Technical Architecture

The architecture relies on a hybrid optimistic sync pattern. A localized cache provides immediate availability and layout stability upon page load, which synchronizes asynchronously with the Flask backend.

### 1. The Reactivity Flow

1. **Change Input**: The user changes a value in the `auth_ui.js` Account panel.
2. **Local Commit**: `movement_prefs.js` immediately caches the updated preferences to `localStorage` under `movementPrefs:v1` and emits a custom DOM event (`movement-prefs-changed`).
3. **UI Cascade**: Sibling modules like `routing_ui.js` listen to the `movement-prefs-changed` event and update dropdown labels (e.g., changing "Walking (5.0 km/h)" to "Walking (4.5 km/h)") in real-time.
4. **Server Sync (If Authenticated)**: The UI attempts to `PATCH /api/preferences/movement`.
5. **Route Query**: Future routes request the server using `buildMovementRequestPayload()`, attaching the precise speed and activity type, so the routing algorithm computes precise effort factors.

---

## Technical Components & File Details

### Frontend Architecture

#### `app/static/js/modules/movement_prefs.js`

Acts as the single source of truth and state wrapper for the client sid.

- **`currentPrefs`**: In-memory JavaScript object maintaining the current values.
- **`getMovementPrefs()` / `setMovementPrefs()`**: Getters and setters for the internal object. `setMovementPrefs` persists changes to `localStorage` and updates the internal cache.
- **`syncMovementPreferencesWithServer()`**: Fetches state from `GET /api/preferences/movement` and merges it into the local store based on strict `movement_prefs_updated_at` timestamps to avoid overwriting newer local edits with stale server data.
- **`speedKmhToDisplay()` / `speedDisplayToKmh()`**: Conversion utilities rendering metric backends faithfully into imperial inputs if the user selected `mi`.

#### `app/static/js/modules/auth_ui.js`

Handles DOM hydration for the account management view.

- **`populateMovementForm()`**: Crucial initialization method that pulls current preferences and applies them safely to the respective `<input type="number">` fields. Translates deep Javascript floats to explicit `.toFixed(1)` strings so strict native HTML5 elements properly render them on a cold refresh.
- Ensures inputs correctly bounce between Speed mode (e.g., 10.0 km/h) and Pace mode (e.g., 6:00 min/km).

#### `app/static/js/modules/routing_ui.js`

Reacts to changes to provide dynamic UI inputs on the Finder page.

- **`initTravelProfileControl()`**: Initializes the `travel-profile-select` dropdown.
- **`updateTravelProfileOptionLabels()`**: Triggered by DOM `movement-prefs-changed` events. Updates the literal text of `<option>` elements on the fly so users see their customized speeds dynamically injected.
- **`buildMovementRequestPayload()`**: Reads the selected profile and attaches it to the final route boundary API footprint so the server calculates times correctly.

### Backend Architecture

#### `app/models/user.py`

The SQLAlchemy persistent layer.

- Additional Float fields configured for `walking_speed_kmh`, `running_easy_speed_kmh`, `running_race_speed_kmh`.
- `movement_prefs_updated_at`: UTC timestamp crucial for client-server sync resolution.

#### `app/blueprints/user_data.py`

The REST API Controller managing persistence operations.

- **`GET /preferences/movement`**: Retrieves the active profile for authenticated users.
- **`PATCH /preferences/movement`**: Merges partial updates from the frontend. Uses timestamp-based concurrency checks (`client_updated_at` vs internal `server_updated_at`) optionally rejecting updates with `409 Conflict` if the client sent fundamentally stale data. Validates dependent logic (e.g., `running_race_speed_kmh` must gracefully strictly equal or exceed `running_easy_speed_kmh`).

#### `app/services/movement_preferences.py`

Service-layer logic wrapping constants and core validations for separation of concerns.

- **`validate_preferences_payload()`**: Asserts limits (`SPEED_LIMITS`). Prevents malicious actors or client-side caching bugs from pushing speeds below `0.01` or beyond absurd values (like a walking speed > 9km/h).
- **`build_user_preferences()`**: Normalizes Python SQLAlchemy attributes into tightly packed frontend JSON payloads.

---

## Hard-Refresh Hydration Details

One specific vulnerability resolved in this architecture relates to HTML5 semantic hierarchy and cold UI reloads.

- The application is robust against `<form>` structure overlap. During early implementations, a missing `</form>` tag in `routing_ui` inadvertently swallowed the `movement-prefs-form` upon natural DOM layout mapping. This made values save perfectly to Postgres but caused the physical DOM element to fail rendering due to the javascript referencing a `null` target.
- Form hydration resolves immediately upon script load (`populateMovementForm(getMovementPrefs());`) _before_ the asynchronous `/auth/me` request occurs. This creates zero layout shift (CLS) for unauthenticated or returning users on slow network calls. The backend payload silently synchronizes afterward via `.then((prefs) => populateMovementForm(prefs))`.
