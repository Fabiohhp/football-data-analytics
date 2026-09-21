-- A null xG means the two sources never paired that match, not that no chances
-- were created (§5 trap 7). COALESCE-ing it to 0 would score the match 0.0 xG and
-- drag every average and every rolling line down.
--
-- `home_xg` and `away_xg` are always null as a pair — measured, and the reason the
-- arithmetic below is exact — so each counting match without xG has to produce
-- exactly two rows with a null `xg_for`. Fewer means something filled them in.

with expected as (

    select 2 * count(*) as null_xg_rows_expected
    from {{ ref('stg_matches') }}
    where status in ('FINISHED', 'AWARDED')
      and football_data_match_id is not null
      and home_xg is null

),

actual as (

    select count(*) as null_xg_rows_actual
    from {{ ref('int_team_matches') }}
    where xg_for is null

)

select null_xg_rows_expected, null_xg_rows_actual
from expected, actual
where null_xg_rows_expected <> null_xg_rows_actual
