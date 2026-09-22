-- A shot without a season, or a player-season without a league, is allowed — but
-- only for one reason, and this pins it to that reason.
--
-- The alternative was a `not_null` test on those columns, which is what was
-- written first. It passes on the real snapshot, where there are no orphan rows
-- (§5 trap 4), and fails on the CI fixture, which carries one on purpose. That
-- makes it a test of *today's data* rather than of the models — and the fixture
-- was right: `match_key` is nullable, Understat really does supply rows before
-- the cross-source join matches their fixture, and the models are supposed to
-- carry those rows through rather than break on them.
--
-- So the invariant is not "these are never null". It is **"these are null only
-- when nothing could have filled them"** — which fails loudly if a join is ever
-- changed in a way that starts blanking rows that do resolve, while staying true
-- whether the orphan count is zero or not.

-- A shot has no season only if no match carries its Understat id.
select
    'shot with no season, but its match is in the snapshot' as failure,
    cast(s.shot_key as varchar)                            as offending_key,
    cast(s.understat_match_id as varchar)                  as detail
from {{ ref('int_shots') }} s
where s.season is null
  and exists (
      select 1 from {{ ref('stg_matches') }} m
      where m.understat_match_id = s.understat_match_id
  )

union all

-- A player-season has no league only if their primary club played no counting
-- matches that season.
select
    'player-season with no league, but the club has counting matches',
    cast(p.understat_player_id as varchar),
    p.season
from {{ ref('mart_player_season') }} p
where p.competition_code is null
  and exists (
      select 1 from {{ ref('int_club_seasons') }} cs
      where cs.team_key = p.primary_team_key and cs.season = p.season
  )
