-- A club cannot play more matches than the fixture list holds, and in a completed
-- season it must have played all of them: exactly twice its number of opponents
-- (CLAUDE.md §6). This is the test that catches a wrong *filter*, which the row
-- count in assert_int_team_matches_two_rows_per_counting_match cannot — that count
-- stays internally consistent whichever matches you let in.
--
-- Two checks, because a filter can go wrong in both directions and the gate below
-- only guards one of them:
--
--   over_played   No gate. A club with more matches than a full double round robin
--                 is impossible in any season, finished or not. This is what a
--                 missing `football_data_match_id` filter looks like: both halves
--                 of a duplicated fixture count, and the club plays 39 matches in a
--                 38-match season. It needs to be ungated, because an over-count
--                 also pushes the season past the completeness gate and would
--                 otherwise silence the second check.
--
--   short_season  Gated on the season being complete. `status = 'FINISHED'` alone
--                 drops three awarded matches, and six clubs across three
--                 league-seasons then read 33 played in a 34-match season.
--
-- "Completed" is derived, not listed, so the in-progress season joins the test by
-- itself when it finishes and no code has to change: a league-season counts as
-- complete once one of its clubs has played a full fixture list, and from that
-- point every other club must have too.

with per_team as (

    select
        season,
        competition_code,
        team_key,
        count(*) as played,
        count(distinct opponent_key) as opponents
    from {{ ref('int_team_matches') }}
    group by 1, 2, 3

),

per_season as (

    select
        season,
        competition_code,
        2 * (count(*) - 1) as scheduled_per_team,
        max(played) as most_played_by_any_club
    from per_team
    group by 1, 2

),

checked as (

    select
        t.season,
        t.competition_code,
        t.team_key,
        t.played,
        t.opponents,
        2 * t.opponents as played_expected,
        s.scheduled_per_team,
        s.most_played_by_any_club >= s.scheduled_per_team as season_is_complete
    from per_team t
    join per_season s
      on s.season = t.season
     and s.competition_code = t.competition_code

)

select *, 'over_played' as failure
from checked
where played > scheduled_per_team

union all

select *, 'short_season' as failure
from checked
where season_is_complete
  and played <> played_expected
