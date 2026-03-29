-- docker/seeder/lighting.lua
local tables = {}

-- Define the output table schema
-- explicitly enforce SRID 3857 (Web Mercator) for compatibility with Martin
-- lit_status stores three states:
--   'lit'     = confirmed lit (lit=yes / true / automatic / 24/7)
--   'unlit'   = confirmed unlit (lit=no)
--   'unknown' = no lit tag present (absence of data)
tables.street_lighting = osm2pgsql.define_table({
    name = 'street_lighting',
    ids = { type = 'any', id_column = 'osm_id' },
    columns = {
        { column = 'lit_status', type = 'text' },
        { column = 'lit_source_primary', type = 'text' },
        { column = 'lit_source_detail', type = 'text' },
        { column = 'lit_tag_type', type = 'text' },
        { column = 'lighting_regime', type = 'text' },
        { column = 'lighting_regime_text', type = 'text' },
        { column = 'osm_lit_raw', type = 'text' },
        { column = 'council_match_count', type = 'int4' },
        { column = 'geom',       type = 'geometry', projection = 3857 },
    }
})

function osm2pgsql.process_way(object)
    -- fast fail: if it's not a highway, we don't care
    if not object.tags.highway then
        return
    end

    local lit_tag = object.tags.lit
    local lit_status
    local lighting_regime

    if lit_tag == 'yes' or lit_tag == 'true' or lit_tag == 'automatic' or lit_tag == '24/7' then
        lit_status = 'lit'
        lighting_regime = 'all_night'
    elseif lit_tag == 'no' then
        lit_status = 'unlit'
        lighting_regime = 'unlit'
    else
        -- Tag is absent or has an unrecognised value — we have no data
        lit_status = 'unknown'
        lighting_regime = 'unknown'
    end

    tables.street_lighting:add_row({
        lit_status = lit_status,
        lit_source_primary = 'osm',
        lit_source_detail = 'osm',
        lit_tag_type = 'osm_lit',
        lighting_regime = lighting_regime,
        lighting_regime_text = lit_tag or lit_status,
        osm_lit_raw = lit_tag,
        council_match_count = 0,
        geom = { create = 'line' }
    })
end
