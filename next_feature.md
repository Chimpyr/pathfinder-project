We are adding a vector tile overlay to the application to visualise street lighting. Based on the architectural analysis and strict DevOps best practices, please implement the following four components.

1. Infrastructure (docker-compose.yml)
   Update the docker-compose.yml file to add two new services: db (PostGIS) and tileserver (Martin).

Service: db

Image: postgis/postgis:15-3.3-alpine

Environment: Define standard POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB credentials.

Volumes: Persist data to a postgres_data volume.

Network: Expose port 5432 to the internal network.

Healthcheck: (Recommended)

YAML
healthcheck:
test: ["CMD-SHELL", "pg_isready -U $POSTGRES_USER"]
interval: 5s
timeout: 5s
retries: 5
Service: tileserver

Image: ghcr.io/maplibre/martin:v0.14

Environment: DATABASE_URL=postgres://user:password@db/dbname (match credentials).

Ports: Expose 3000:3000.

Depends_on:
db:
condition: service_healthy

2. Data Normalisation (The Lua Script)
   Create app/data/lighting.lua. This uses osm2pgsql's Flex backend.

Lua
-- app/data/lighting.lua
local tables = {}

-- Define the output table schema
-- We explicitly enforce SRID 3857 (Web Mercator) for compatibility with Martin
tables.street_lighting = osm2pgsql.define_table({
name = 'street_lighting',
ids = { type = 'any', id_column = 'osm_id' },
columns = {
{ column = 'is_lit', type = 'boolean' },
{ column = 'geom', type = 'geometry', projection = 3857 },
}
})

function osm2pgsql.process_way(object)
-- fast fail: if it's not a highway, we don't care
if not object.tags.highway then
return
end

    local is_lit = false
    local lit_tag = object.tags.lit

    -- Normalize 'lit' tag values to strict boolean
    if lit_tag == 'yes' or lit_tag == 'true' or lit_tag == 'automatic' or lit_tag == '24/7' then
        is_lit = true
    end

    tables.street_lighting:add_row({
        is_lit = is_lit,
        geom = { create = 'line' }
    })

end 3. Ingestion Strategy (The Robust Seeder)
We will use a Docker Init Container pattern with pg_isready to ensure zero race conditions.

A. Create docker/seeder/Dockerfile:
Use the --chown flag to avoid image bloat and permission errors.

Dockerfile
FROM osm2pgsql/osm2pgsql:1.10

# Install postgresql-client for the pg_isready utility

USER root
RUN apt-get update && apt-get install -y postgresql-client

# Copy scripts and ensure ownership by the osm2pgsql user in a single step

COPY --chown=osm2pgsql:osm2pgsql app/data/lighting.lua /lighting.lua
COPY --chown=osm2pgsql:osm2pgsql scripts/wait-for-postgres.sh /wait-for-postgres.sh

USER osm2pgsql
ENTRYPOINT ["/wait-for-postgres.sh"]
B. Create scripts/wait-for-postgres.sh:
(Ensure this file is executable: chmod +x scripts/wait-for-postgres.sh)

Bash
#!/bin/sh
set -e # Exit immediately if any command fails

echo "Checking PostGIS availability..."

# Robust Health Check: Loop until the Database Engine is ready to accept connections

# -h: host, -U: user. We ignore the exit code in the loop condition using 'until'.

until pg_isready -h db -U "$POSTGRES_USER"; do
echo "PostGIS is unavailable - sleeping 1s..."
sleep 1
done

echo "PostGIS is ready! Starting import..."

# Run the import

# --create: Wipes and recreates the database tables (idempotent for seeding)

osm2pgsql --create --slim --cache 1000 \
 --output=flex --style=/lighting.lua \
 --database=postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@db/$POSTGRES_DB \
 /data/england-latest.osm.pbf

echo "Import finished successfully."
C. Update docker-compose.yml:
Add the seeder service with the profiles key.

YAML
seeder:
build:
context: .
dockerfile: docker/seeder/Dockerfile
environment: - POSTGRES_USER=... - POSTGRES_PASSWORD=... - POSTGRES_DB=...
volumes: - ./app/data:/data # Mount the PBFs
depends_on:
db:
condition: service_healthy
profiles: ["seed"] # Run manually via: docker-compose up seeder 4. Frontend Integration (Leaflet)
Update app/static/js/map.js to render the tiles.

A. HTML Update:
Include the vector grid library:

<script src="https://unpkg.com/leaflet.vectorgrid@latest/dist/Leaflet.VectorGrid.bundled.js"></script>

B. Controller Update:
Use a relative protocol/domain to avoid 'localhost' hardcoding issues in different environments.

JavaScript
addLightingLayer() {
// Dynamically determine the tile server URL
// For dev: assume port 3000 on the same hostname
// For prod: this should ideally be behind an nginx proxy (e.g. /tiles/...)
const protocol = window.location.protocol;
const hostname = window.location.hostname;
const url = `${protocol}//${hostname}:3000/street_lighting/{z}/{x}/{y}.pbf`;

    console.log(`Fetching tiles from: ${url}`);

    const lightingLayer = L.vectorGrid.protobuf(url, {
        vectorTileLayerStyles: {
            street_lighting: function(properties, zoom) {
                // High-performance styling function
                // Returns distinct styles for Lit vs Unlit streets
                const isLit = properties.is_lit;
                return {
                    weight: isLit ? 2 : 1,
                    color: isLit ? '#FFD700' : '#444444',
                    opacity: isLit ? 0.8 : 0.3
                };
            }
        },
        interactive: true, // Optional: enable if you need click events
    });

    lightingLayer.addTo(this.map);

}
"
