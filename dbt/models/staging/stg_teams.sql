-- One row per club, from `gold.dim_teams` (SCD Type 1 — no history).
-- `canonical_name` is the conformed cross-source name and the only one a chart
-- should ever show; the per-source names are kept for tracing a number back.

select
    team_key,
    canonical_name as team_name,
    football_data_name,
    understat_name,
    football_data_id,
    understat_id,
    loaded_at

from {{ source('gold', 'dim_teams') }}
