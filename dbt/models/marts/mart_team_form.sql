-- Rolling xG for and against over a club's last N matches, with the results that
-- came with them: one row per club per counting match (CLAUDE.md §6).
--
-- This is what the dashboard's Team page draws, and what a "who is trending up"
-- question is answered from. N is the `form_window` var (default 5) and travels
-- on every row as `form_window`, so no chart can show a rolling line without
-- being able to say how long the window is.
--
-- Three details that decide whether the line means anything:
--
--   * **The window never crosses a season or a competition.** It is partitioned by
--     club, season and competition code, so a club's opening match of a season
--     starts a fresh window rather than averaging in last May.
--
--   * **Null xG is not averaged as zero** (§5 trap 7). `avg()` skips nulls, so a
--     window containing an unpaired match averages the matches that do have xG —
--     and `window_xg_matches` says how many that was. A chart that wants a
--     complete window filters on it rather than drawing a dip that is really a
--     missing fixture.
--
--   * **The first N−1 matches of a season have a short window.** `window_matches`
--     counts the rows actually behind each value, so those points can be dropped
--     or drawn differently instead of reading as a genuine slow start.

{% set form_window = var('form_window') %}

with team_matches as (

    select
        m.team_key,
        m.match_key,
        m.match_date,
        m.season,
        m.competition_code,
        m.matchday,
        m.is_home,
        m.opponent_key,
        m.goals_for,
        m.goals_against,
        m.goal_difference,
        m.points,
        m.xg_for,
        m.xg_against,
        m.xg_difference,
        m.xpts
    from {{ ref('int_team_matches') }} m

)

select
    tm.team_key,
    t.team_name,
    tm.match_key,
    tm.match_date,
    tm.season,
    tm.competition_code,
    tm.matchday,
    tm.is_home,
    tm.opponent_key,
    o.team_name as opponent_name,

    tm.goals_for,
    tm.goals_against,
    tm.goal_difference,
    tm.points,
    tm.xg_for,
    tm.xg_against,
    tm.xg_difference,
    tm.xpts,

    -- Which match of the season this is for this club. `match_key` breaks ties so
    -- two matches on one date always order the same way from run to run.
    row_number() over (
        partition by tm.team_key, tm.season, tm.competition_code
        order by tm.match_date, tm.match_key
    ) as match_number,

    {{ form_window }} as form_window,

    count(*) over w as window_matches,
    count(tm.xg_for) over w as window_xg_matches,
    avg(tm.xg_for) over w as rolling_xg_for,
    avg(tm.xg_against) over w as rolling_xg_against,
    avg(tm.points) over w as rolling_points,
    sum(tm.points) over w as window_points

from team_matches tm
left join {{ ref('stg_teams') }} t on t.team_key = tm.team_key
left join {{ ref('stg_teams') }} o on o.team_key = tm.opponent_key
window w as (
    partition by tm.team_key, tm.season, tm.competition_code
    order by tm.match_date, tm.match_key
    rows between {{ form_window - 1 }} preceding and current row
)
