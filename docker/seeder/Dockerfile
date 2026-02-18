FROM debian:bookworm-slim

# Install osm2pgsql and postgresql-client (for pg_isready) in a single layer
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       osm2pgsql \
       postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/wait-for-postgres.sh /wait-for-postgres.sh
COPY app/data/lighting.lua /lighting.lua

# Strip Windows CRLF line endings and ensure the script is executable
RUN sed -i 's/\r//' /wait-for-postgres.sh && chmod +x /wait-for-postgres.sh

ENTRYPOINT ["/wait-for-postgres.sh"]
