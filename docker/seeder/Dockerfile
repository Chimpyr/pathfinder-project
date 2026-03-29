FROM debian:bookworm-slim

# Install osm2pgsql, gdal tools (ogr2ogr), and postgresql-client in a single layer
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       osm2pgsql \
       gdal-bin \
       postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/wait-for-postgres.sh /wait-for-postgres.sh
COPY docker/seeder/lighting.lua /lighting.lua
COPY docker/seeder/merge_council_streetlights.sql /merge_council_streetlights.sql

# Strip Windows CRLF line endings and ensure the script is executable
RUN sed -i 's/\r//' /wait-for-postgres.sh && chmod +x /wait-for-postgres.sh

ENTRYPOINT ["/wait-for-postgres.sh"]
