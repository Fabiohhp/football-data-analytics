-- No two rows in `int_shots` describe the same shot (§5 trap 14).
--
-- The shape is the identity here, not the id: Understat returned every shot of two
-- La Liga matches twice under *different* shot ids, so a `unique` test on
-- `shot_key` passes happily while 46 rows are duplicates. This checks the thing
-- that actually has to be unique.

select
    understat_match_id,
    player_key,
    minute,
    result,
    x,
    y,
    xg,
    count(*) as copies
from {{ ref('int_shots') }}
group by 1, 2, 3, 4, 5, 6, 7
having count(*) > 1
