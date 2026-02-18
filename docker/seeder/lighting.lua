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

    if lit_tag == 'yes' or lit_tag == 'true' or lit_tag == 'automatic' or lit_tag == '24/7' then
        lit_status = 'lit'
    elseif lit_tag == 'no' then
        lit_status = 'unlit'
    else
        -- Tag is absent or has an unrecognised value — we have no data
        lit_status = 'unknown'
    end

    tables.street_lighting:add_row({
        lit_status = lit_status,
        geom = { create = 'line' }
    })
end
