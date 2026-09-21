-- The `season_label` macro is Part 1's `season_label()` rewritten in SQL, and
-- every fact but `fact_matches` depends on it (§5 trap 5). `fact_matches` is the
-- one place the two can be compared, so they are compared on every row: if the
-- August cutoff here ever drifts from Part 1's, every derived season downstream is
-- wrong and nothing else would notice.

select
    match_key,
    match_date,
    season as season_from_gold,
    {{ season_label('match_date') }} as season_derived
from {{ ref('stg_matches') }}
where season is not null
  and season <> {{ season_label('match_date') }}
