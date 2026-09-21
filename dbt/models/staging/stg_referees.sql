-- One row per match official, from `gold.dim_referees` (SCD Type 1).
--
-- Key `0` is the `Unknown` member, and it means **no official was reported** —
-- not an official named Unknown (§5 trap 3). In the current snapshot 64 matches
-- point at it. Any per-referee metric excludes key 0 explicitly and reports how
-- many rows that removed; this model keeps the row so that count is possible.

select
    referee_key,
    football_data_id,
    referee_name,
    nationality,
    loaded_at

from {{ source('gold', 'dim_referees') }}
