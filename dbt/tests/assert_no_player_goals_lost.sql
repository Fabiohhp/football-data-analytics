-- Nothing is lost between the raw player fact and the player mart.
--
-- This is the test CLAUDE.md §12 promised for §5 trap 4 and deferred out of phase
-- 2, when there was no model reading the event facts for an orphan to be dropped
-- *from*. Now there is. `match_key` is nullable, so an inner join anywhere in
-- `int_player_matches` or `mart_player_season` would silently drop the rows
-- Understat supplied before the cross-source join matched their fixture — and a
-- silently smaller goal total is precisely the kind of plausible wrong number this
-- repository is built to catch.
--
-- The count is zero orphans today. The point is that it costs nothing if it stops
-- being zero: the totals must survive either way, which is why this compares sums
-- rather than asserting the orphan count stays at zero. The CI fixture carries an
-- orphan on purpose, so this test is doing real work on every run.

with staged as (

    select
        sum(goals)          as goals,
        sum(assists)        as assists,
        sum(minutes_played) as minutes,
        count(*)            as rows
    from {{ ref('stg_player_events') }}

),

marted as (

    select
        sum(goals)   as goals,
        sum(assists) as assists,
        sum(minutes) as minutes,
        sum(matches) as rows
    from {{ ref('mart_player_season') }}

)

select
    staged.goals   as staged_goals,   marted.goals   as marted_goals,
    staged.assists as staged_assists, marted.assists as marted_assists,
    staged.minutes as staged_minutes, marted.minutes as marted_minutes,
    staged.rows    as staged_rows,    marted.rows    as marted_rows
from staged, marted
where staged.goals   is distinct from marted.goals
   or staged.assists is distinct from marted.assists
   or staged.minutes is distinct from marted.minutes
   or staged.rows    is distinct from marted.rows
