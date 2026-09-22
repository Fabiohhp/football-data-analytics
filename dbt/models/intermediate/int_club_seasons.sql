-- Which league each club played in, each season. One row per club per season.
--
-- Small, and it exists to solve one specific problem. `competition_code` is NULL
-- on the Understat half of every split fixture (§5 trap 13), and the player events
-- and shots of those fixtures hang off exactly that half — 368 player rows and 307
-- shots. Reading a competition straight off the match would leave them without a
-- league, and **33 player-seasons would have no league at all**, because the only
-- match those players appeared in that season was a split half.
--
-- A club plays in exactly one competition per season, so the club's own counting
-- matches answer the question for every row: measured, 0 of 288 club-seasons span
-- two competitions, and every club-season appearing in the player facts has
-- counting matches to inherit from. Derived once here rather than in each mart
-- that needs it.

select
    team_key,
    season,
    competition_code,
    max(competition_name) as competition_name,
    count(*) as counting_matches

from {{ ref('int_team_matches') }}
group by 1, 2, 3
