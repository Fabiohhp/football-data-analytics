-- The same league table as `mart_team_season`, cut in two: each club's first half
-- of a season and its second half, as separate rows.
--
-- Exists for §8 question 1, which asks whether a club's points-over-xPTS gap
-- *persists* — and that can only be asked by measuring the gap in one stretch of
-- matches and looking at what the next stretch did. The natural place to write
-- that split would be the notebook, but the honest version of `points − xPTS`
-- needs the coverage discipline `mart_team_season` already has (points counted
-- over exactly the matches that carry an xPTS, §5 trap 7), and a calculation may
-- not exist in two places (CLAUDE.md §4). So it is a mart.
--
-- **The halves are by match number, not by date.** Clubs play the same number of
-- matches but not on the same days — postponements alone would put a different
-- number of fixtures either side of a calendar cut-off, and a club with 20
-- first-half matches compared against one with 18 is not a fair comparison. Match
-- number is per club, so both halves hold exactly half a fixture list.
--
-- Only complete seasons can be halved meaningfully, so `is_season_complete` is
-- carried through and the analysis filters on it. An in-progress season still
-- produces rows; they just describe a first half and a partial second.

with scheduled as (

    select
        team_key,
        season,
        competition_code,
        scheduled_per_team,
        is_season_complete
    from {{ ref('mart_team_season') }}

),

halved as (

    select
        m.*,
        s.scheduled_per_team,
        s.is_season_complete,
        case
            when m.match_number <= s.scheduled_per_team / 2.0 then 1
            else 2
        end as season_half
    from {{ ref('int_team_matches') }} m
    join scheduled s
      on s.team_key = m.team_key
     and s.season = m.season
     and s.competition_code = m.competition_code

)

select
    h.team_key,
    t.team_name,
    h.season,
    h.competition_code,
    h.season_half,
    max(h.is_season_complete)  as is_season_complete,
    max(h.scheduled_per_team)  as scheduled_per_team,

    count(*)                   as played,
    sum(h.points)              as points,
    sum(h.goals_for)           as goals_for,
    sum(h.goals_against)       as goals_against,
    sum(h.goals_for) - sum(h.goals_against) as goal_difference,

    -- Coverage first, as everywhere else: these totals cover `matches_with_xg`
    -- matches, not `played` (§5 trap 7).
    count(h.xg_for)            as matches_with_xg,
    sum(h.xg_for)              as xg_for,
    sum(h.xg_against)          as xg_against,
    sum(h.xg_for) - sum(h.xg_against) as xg_difference,

    count(h.xpts)              as matches_with_xpts,
    sum(h.xpts)                as xpts,
    sum(h.points) filter (where h.xpts is not null) as points_in_xpts_matches,
    sum(h.points) filter (where h.xpts is not null) - sum(h.xpts) as points_minus_xpts,

    -- Per-match rates, so the two halves stay comparable even if one of them is
    -- short — which it is for every in-progress season.
    sum(h.points) / count(*)                       as points_per_match,
    (sum(h.xg_for) - sum(h.xg_against)) / nullif(count(h.xg_for), 0) as xg_difference_per_match,

    min(h.match_date)          as first_match_date,
    max(h.match_date)          as last_match_date

from halved h
left join {{ ref('stg_teams') }} t on t.team_key = h.team_key
group by 1, 2, 3, 4, 5
