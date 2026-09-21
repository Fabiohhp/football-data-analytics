-- The league table, and everything that sits beside it: xPTS, points − xPTS, xG
-- difference and PPDA, one row per club per league-season (CLAUDE.md §6).
--
-- Every figure here is a GROUP BY over `int_team_matches`, which has already
-- settled which matches count. Two things this mart is careful about:
--
--   * **xG coverage is reported, not hidden.** A null xG means the sources never
--     paired that match (§5 trap 7). SQL's `sum()` skips nulls silently, so the
--     xG totals below cover `matches_with_xg` matches, not `played` — and
--     `points_minus_xpts` compares points and xPTS over *the same* matches rather
--     than a full season of points against a partial season of xPTS. Getting that
--     wrong would invent a points overperformance out of a missing fixture.
--
--   * **`table_position` uses points, then goal difference, then goals scored.**
--     That is the Premier League, Bundesliga and Ligue 1 rule. La Liga and Serie A
--     break ties on head-to-head results first, which Gold has no aggregate for,
--     so a position here can differ from the official table where two clubs finish
--     level on points. The points, goals and xG columns are unaffected.

with per_team_season as (

    select
        team_key,
        season,
        competition_code,
        max(competition_name) as competition_name,

        count(*) as played,
        count(*) filter (where is_home) as played_home,
        count(*) filter (where points = 3) as won,
        count(*) filter (where points = 1) as drawn,
        count(*) filter (where points = 0) as lost,

        sum(goals_for) as goals_for,
        sum(goals_against) as goals_against,
        sum(goals_for) - sum(goals_against) as goal_difference,
        sum(points) as points,

        -- How many of `played` the xG figures below actually cover.
        count(xg_for) as matches_with_xg,
        sum(xg_for) as xg_for,
        sum(xg_against) as xg_against,
        sum(xg_for) - sum(xg_against) as xg_difference,
        sum(npxg_for) as npxg_for,
        sum(npxg_against) as npxg_against,

        count(xpts) as matches_with_xpts,
        sum(xpts) as xpts,
        -- The points actually earned in the matches that have an xPTS, so that
        -- points − xPTS is a like-for-like comparison.
        sum(points) filter (where xpts is not null) as points_in_xpts_matches,

        count(ppda) as matches_with_ppda,
        avg(ppda) as ppda,

        min(match_date) as first_match_date,
        max(match_date) as last_match_date

    from {{ ref('int_team_matches') }}
    group by 1, 2, 3

),

with_season_shape as (

    select
        *,
        -- A full double round robin: every other club home and away. Derived from
        -- the clubs present rather than from a hardcoded 38 or 34, because Ligue 1
        -- and the Bundesliga run 18 clubs and league sizes change between seasons.
        2 * (count(*) over (partition by season, competition_code) - 1) as scheduled_per_team
    from per_team_season

)

select
    s.team_key,
    t.team_name,
    s.season,
    s.competition_code,
    s.competition_name,

    played,
    played_home,
    won,
    drawn,
    lost,
    goals_for,
    goals_against,
    goal_difference,
    points,
    points / played as points_per_match,

    row_number() over (
        partition by s.season, s.competition_code
        order by points desc, goal_difference desc, goals_for desc, s.team_key
    ) as table_position,

    matches_with_xg,
    xg_for,
    xg_against,
    xg_difference,
    xg_for / nullif(matches_with_xg, 0) as xg_for_per_match,
    xg_against / nullif(matches_with_xg, 0) as xg_against_per_match,
    npxg_for,
    npxg_against,

    matches_with_xpts,
    xpts,
    points_in_xpts_matches,
    -- The headline of question 1 in CLAUDE.md §8: positive means the club has more
    -- points than its chances deserved.
    points_in_xpts_matches - xpts as points_minus_xpts,

    matches_with_ppda,
    ppda,

    scheduled_per_team,
    played = scheduled_per_team as team_fixtures_complete,
    -- True only when *every* club in the league-season has played its full
    -- fixture list. The in-progress season is the reason this exists: comparing
    -- season totals across a complete and a partial season is the easiest wrong
    -- number in the whole repository, so the answer lives here rather than in a
    -- notebook or a dashboard filter.
    min(played) over (partition by s.season, s.competition_code) = scheduled_per_team
        as is_season_complete,

    first_match_date,
    last_match_date

from with_season_shape s
-- The conformed club name, so a chart never has to resolve a key. A LEFT join:
-- a club missing from dim_teams would be a Part 1 bug, and losing its season from
-- the league table is a worse way to find out than seeing a null name.
left join {{ ref('stg_teams') }} t on t.team_key = s.team_key
