-- int_team_matches must hold exactly two rows per counting match, one per side.
--
-- The filters are spelled out again here rather than read from the model, on
-- purpose. A test that asked the model what its own filter was would move the
-- goalposts along with it; this one is an independent count, so widening or
-- dropping a filter in the model fails here.
--
-- This catches a lost or duplicated row. It does **not** catch a wrong filter —
-- the count stays internally consistent whichever matches you let in — which is
-- what assert_completed_seasons_have_full_fixture_lists is for.

with expected as (

    select 2 * count(*) as rows_expected
    from {{ ref('stg_matches') }}
    where status in ('FINISHED', 'AWARDED')
      and football_data_match_id is not null

),

actual as (

    select count(*) as rows_actual
    from {{ ref('int_team_matches') }}

)

select rows_expected, rows_actual
from expected, actual
where rows_expected <> rows_actual
