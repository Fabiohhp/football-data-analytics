-- One row per ground, from `gold.dim_stadiums` (SCD Type 1).
--
-- `city` and `capacity` are carried through and are **always null** — Gold has no
-- source for them (§5 trap 9). They are selected here rather than dropped so that
-- the contract's shape stays visible, and so nothing is tempted to impute them.

select
    stadium_key,
    {{ html_unescape('stadium_name') }} as stadium_name,
    city,
    country,
    capacity,
    address,
    loaded_at

from {{ source('gold', 'dim_stadiums') }}
