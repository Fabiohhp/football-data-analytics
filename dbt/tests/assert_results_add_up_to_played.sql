-- The league table has to be internally consistent: won + drawn + lost = played,
-- and goals for minus goals against = goal difference. Cheap, and it catches a
-- mis-scoped `filter (where ...)` in the mart, which is otherwise invisible — the
-- numbers stay plausible and only the total gives it away.

select
    team_key,
    season,
    competition_code,
    played,
    won,
    drawn,
    lost,
    goals_for,
    goals_against,
    goal_difference
from {{ ref('mart_team_season') }}
where won + drawn + lost <> played
   or goals_for - goals_against <> goal_difference
