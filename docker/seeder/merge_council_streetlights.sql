BEGIN;

ALTER TABLE public.street_lighting
    ADD COLUMN IF NOT EXISTS osm_lit_raw text,
    ADD COLUMN IF NOT EXISTS lit_source_primary text,
    ADD COLUMN IF NOT EXISTS lit_source_detail text,
    ADD COLUMN IF NOT EXISTS lit_tag_type text,
    ADD COLUMN IF NOT EXISTS lighting_regime text,
    ADD COLUMN IF NOT EXISTS lighting_regime_text text,
    ADD COLUMN IF NOT EXISTS council_match_count integer DEFAULT 0;

UPDATE public.street_lighting
SET lit_source_primary = 'osm',
    lit_source_detail = 'osm',
    lit_tag_type = COALESCE(NULLIF(lit_tag_type, ''), 'osm_lit'),
    lighting_regime = COALESCE(
        NULLIF(lighting_regime, ''),
        CASE
            WHEN lit_status = 'lit' THEN 'all_night'
            WHEN lit_status = 'unlit' THEN 'unlit'
            ELSE 'unknown'
        END
    ),
    lighting_regime_text = COALESCE(NULLIF(lighting_regime_text, ''), COALESCE(osm_lit_raw, lit_status, 'unknown')),
    council_match_count = 0;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'council_streetlights_raw'
    ) THEN
        ALTER TABLE public.council_streetlights_raw
            ADD COLUMN IF NOT EXISTS source text,
            ADD COLUMN IF NOT EXISTS lit text,
            ADD COLUMN IF NOT EXISTS lit_tag_type text,
            ADD COLUMN IF NOT EXISTS lighting_regime text,
            ADD COLUMN IF NOT EXISTS lighting_regime_text text;

        UPDATE public.council_streetlights_raw
        SET source = COALESCE(NULLIF(lower(trim(source)), ''), 'council'),
            lit = COALESCE(NULLIF(lower(trim(lit)), ''), 'yes'),
            lit_tag_type = COALESCE(NULLIF(lower(trim(lit_tag_type)), ''), 'council_point'),
            lighting_regime = COALESCE(NULLIF(lower(trim(lighting_regime)), ''), 'unknown'),
            lighting_regime_text = COALESCE(NULLIF(trim(lighting_regime_text), ''), lit_tag_type)
        WHERE TRUE;

        CREATE INDEX IF NOT EXISTS idx_council_streetlights_raw_geom_gix
            ON public.council_streetlights_raw USING GIST (geom);

        DROP TABLE IF EXISTS _council_line_matches;

        CREATE TEMP TABLE _council_line_matches AS
        SELECT
            sl.ctid AS row_ctid,
            COUNT(*)::integer AS council_match_count,
            mode() WITHIN GROUP (ORDER BY c.source) AS lit_source_detail,
            mode() WITHIN GROUP (ORDER BY c.lit_tag_type) AS lit_tag_type,
            mode() WITHIN GROUP (ORDER BY c.lighting_regime) AS lighting_regime,
            mode() WITHIN GROUP (ORDER BY c.lighting_regime_text) AS lighting_regime_text
        FROM public.street_lighting sl
        JOIN public.council_streetlights_raw c
          ON ST_DWithin(sl.geom, c.geom, 15)
        GROUP BY sl.ctid;

        UPDATE public.street_lighting sl
        SET lit_status = 'lit',
            lit_source_primary = 'council',
            lit_source_detail = COALESCE(m.lit_source_detail, 'council'),
            lit_tag_type = COALESCE(m.lit_tag_type, 'council_point'),
            lighting_regime = COALESCE(m.lighting_regime, 'unknown'),
            lighting_regime_text = COALESCE(m.lighting_regime_text, sl.lighting_regime_text),
            council_match_count = m.council_match_count
        FROM _council_line_matches m
        WHERE sl.ctid = m.row_ctid;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION public.street_lighting_filtered(
    z integer,
    x integer,
    y integer,
    query_params json DEFAULT '{}'::json
)
RETURNS bytea
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
WITH
params AS (
    SELECT
        lower(COALESCE(query_params->>'source_filter', 'all')) AS source_filter,
        lower(COALESCE(query_params->>'regime_filter', 'all')) AS regime_filter
),
bounds AS (
    SELECT ST_TileEnvelope(z, x, y) AS geom
),
mvtgeom AS (
    SELECT
        sl.osm_id,
        sl.lit_status,
        sl.lit_source_primary,
        sl.lit_source_detail,
        sl.lit_tag_type,
        sl.lighting_regime,
        sl.lighting_regime_text,
        sl.council_match_count,
        ST_AsMVTGeom(sl.geom, bounds.geom, 4096, 256, true) AS geom
        FROM public.street_lighting sl, bounds, params
    WHERE sl.geom && bounds.geom
      AND ST_Intersects(sl.geom, bounds.geom)
      AND (
                        params.source_filter = 'all'
                        OR lower(COALESCE(sl.lit_source_primary, 'osm')) = params.source_filter
                        OR lower(COALESCE(sl.lit_source_detail, 'osm')) = params.source_filter
          )
      AND (
                        params.regime_filter = 'all'
                        OR lower(COALESCE(sl.lighting_regime, 'unknown')) = params.regime_filter
          )
)
SELECT ST_AsMVT(mvtgeom, 'street_lighting', 4096, 'geom')
FROM mvtgeom;
$$;

CREATE INDEX IF NOT EXISTS idx_street_lighting_geom_gix
    ON public.street_lighting USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_street_lighting_source_primary
    ON public.street_lighting (lit_source_primary);
CREATE INDEX IF NOT EXISTS idx_street_lighting_source_detail
    ON public.street_lighting (lit_source_detail);
CREATE INDEX IF NOT EXISTS idx_street_lighting_regime
    ON public.street_lighting (lighting_regime);
CREATE INDEX IF NOT EXISTS idx_street_lighting_status
    ON public.street_lighting (lit_status);

ANALYZE public.street_lighting;

COMMIT;
