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


# Optional: import canonical council streetlights and enrich overlay table.
COUNCIL_GPKG=/data/streetlight/combined_streetlights.gpkg
PG_CONN="PG:host=db user=$POSTGRES_USER dbname=$POSTGRES_DB password=$POSTGRES_PASSWORD"
PG_URL="postgresql://$POSTGRES_USER:$POSTGRES_PASSWORD@db/$POSTGRES_DB"

if [ -f "$COUNCIL_GPKG" ]; then
  echo "Council dataset found: $COUNCIL_GPKG"
  echo "Importing council points into public.council_streetlights_raw..."
  ogr2ogr -f PostgreSQL "$PG_CONN" "$COUNCIL_GPKG" \
    combined_streetlights \
    -nln public.council_streetlights_raw \
    -nlt POINT \
    -lco GEOMETRY_NAME=geom \
    -lco FID=id \
    -t_srs EPSG:3857 \
    -overwrite
else
  echo "Council dataset not found, using OSM-only overlay fallback."
  psql "$PG_URL" -c "DROP TABLE IF EXISTS public.council_streetlights_raw;"
fi

echo "Applying council merge and metadata enrichment..."
psql "$PG_URL" -f /merge_council_streetlights.sql


echo "Import finished successfully."
