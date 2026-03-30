# 4. Dual-Database Segregation Boundary (Plan)

**Section:** High-Level System Architecture
**Format:** Container/Database Boundary Diagram

## What it should include:
A clear bifurcation of your data layer:
1. **Left Side (Volatile):** The PostGIS container hosting `scenic_tiles`. Show the `osm2pgsql` importer aggressively dropping and rebuilding tables. Show the Martin Tile Server reading from this and firing lightweight styling vector tiles directly to Leaflet.js.
2. **Right Side (Persistent):** The PostgreSQL instance hosting `user_db`. Show SQLAlchemy, Alembic Migrations, and your Flask API safely interacting with persistent user states (saved routes, login data).
3. **The Boundary:** A clear red line heavily denoting the "Blast Radius Isolation" between the two.

## Data Required & Where to Find it:
*   **The ADRs:** `docs/decisions/ADR-012-dual-database-segregation.md`, `ADR-013-automated-database-bootstrapping.md`.
*   **The Code:** `docker-compose.yml`, `config.py`.

## What it Proves & Why it is Positive:
This proves advanced **Data Engineering and Scalable Architecture**. It visually proves to the marker that you understand the "blast radius" of spatial extensions. It illustrates that you didn't clump everything into a single database out of laziness, but actively engineered an isolation tier that prevents your volatile mapping data from corrupting user persistence during Alembic migrations.

## Most Efficient Way to Create It:
**Mermaid.js (Architecture Graph)**
The most efficient, modifiable way to build this is natively in Markdown using a `mermaid` code block. Mermaid uses simple text syntax to declare nodes, boxes, and arrows, and renders perfectly in GitHub and most markdown viewers. If you update your tech stack later, you just change a word of text, rather than recreating a complex image in Figma or Draw.io.
