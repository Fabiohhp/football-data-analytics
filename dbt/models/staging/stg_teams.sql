-- One row per club, from `gold.dim_teams` (SCD Type 1 — no history).
-- `canonical_name` is the conformed cross-source name and the only one a chart
-- should ever show; the per-source names are kept for tracing a number back.

select
    team_key,
    -- §5 trap 15. A real ampersand survives: Brighton & Hove Albion is not escaped.
    {{ html_unescape('canonical_name') }} as team_name,
    {{ html_unescape('football_data_name') }} as football_data_name,
    {{ html_unescape('understat_name') }} as understat_name,
    football_data_id,
    understat_id,
    loaded_at

from {{ source('gold', 'dim_teams') }}
