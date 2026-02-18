#!/bin/sh
set -e  # Exit immediately if any command fails

echo "Checking PostGIS availability..."

# Robust Health Check: Loop until the Database Engine is ready to accept connections
# -h: host, -U: user. We ignore the exit code in the loop condition using 'until'.
until pg_isready -h db -U "$POSTGRES_USER"; do
  echo "PostGIS is unavailable - sleeping 1s..."
  sleep 1
done

echo "PostGIS is ready! Starting import..."

# Resolve PBF path — try common filenames in order
if [ -f /data/england-latest.osm.pbf ]; then
  PBF=/data/england-latest.osm.pbf
elif [ -f /data/england.osm.pbf ]; then
  PBF=/data/england.osm.pbf
else
  echo "ERROR: No England PBF found. Expected one of:"
  echo "  /data/england-latest.osm.pbf"
  echo "  /data/england.osm.pbf"
  exit 1
fi

echo "Using PBF: $PBF"

# Run the import
# --create: Wipes and recreates the database tables (idempotent for seeding)
osm2pgsql --create --slim --cache 4000 \
  --output=flex --style=/lighting.lua \
  --database=postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@db/$POSTGRES_DB \
  "$PBF"


echo "Import finished successfully."
