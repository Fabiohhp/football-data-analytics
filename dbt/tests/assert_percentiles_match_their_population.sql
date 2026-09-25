-- A percentile is only meaningful against a stated population, so two things have to
-- hold: it exists for exactly the players in that population, and it spans it.
--
-- The population is players in the same season and league who clear the minutes
-- floor. A player below the floor must get NULL — not a percentile measured against
-- a group they are not in, which would read as a real ranking on the dashboard and
-- be the plausible wrong number this repository exists to prevent.

select 'percentile set for a player below the minutes floor' as failure,
       count(*) as rows
from {{ ref('mart_player_season') }}
where not meets_minutes_floor
  and coalesce(npxg_per_90_percentile, np_goals_per_90_percentile,
               xa_per_90_percentile, shots_per_90_percentile) is not null
having count(*) > 0

union all

select 'percentile missing for a player above the floor', count(*)
from {{ ref('mart_player_season') }}
where meets_minutes_floor and npxg_per_90_percentile is null
having count(*) > 0

union all

select 'percentile outside 0-100', count(*)
from {{ ref('mart_player_season') }}
where npxg_per_90_percentile not between 0 and 100
   or np_goals_per_90_percentile not between 0 and 100
   or xa_per_90_percentile not between 0 and 100
   or shots_per_90_percentile not between 0 and 100
having count(*) > 0

union all

-- A rank must fit its league: 1 to however many clubs are in it.
select 'rank outside the size of its league', count(*)
from {{ ref('mart_team_season') }}
where points_minus_xpts_rank not between 1 and clubs_in_league
   or xg_difference_rank not between 1 and clubs_in_league
having count(*) > 0
