-- The foundation of every team metric (CLAUDE.md §6): one row per team per
-- *counting* match, so two rows per fixture. League tables, form and home
-- advantage are all a GROUP BY over this model, and nothing downstream repeats
-- the filters below.
--
-- "Counting" is two filters. Both are load-bearing, and neither implies the other:
--
--   status in ('FINISHED', 'AWARDED')          §5 trap 6
--     Three matches were abandoned and then awarded by the federation. They were
--     really played, they carry a real score and real xG, and they counted towards
--     the real league table. Filtering on 'FINISHED' alone drops them, and six
--     clubs across three league-seasons then read 33 matches played in a 34-match
--     season. The same filter excludes the one POSTPONED match, which was never
--     played but carries a phantom 0-0 with result = 'DRAW' and no xG.
--
--   football_data_match_id is not null        §5 trap 13
--     Twelve fixtures exist as two rows, because the sources disagreed on the
--     calendar date of a late kickoff and the cross-source join missed. Measured
--     in section 5 of notebooks/01_data_profile.ipynb: **both halves are
--     `FINISHED` and both carry a scoreline**, so the status filter does not
--     separate them — only the Football-Data id does. Keeping the result-bearing
--     half is what makes a league table add up, and dropping the other is what
--     stops a club playing 39 matches in a 38-match season.
--
-- What this model does *not* do is COALESCE anything. A null `xg_for` means the
-- sources never paired that match (§5 trap 7); it travels through as null and the
-- marts count how many matches their xG figures actually cover.

with counting_matches as (

    select *
    from {{ ref('stg_matches') }}
    where status in ('FINISHED', 'AWARDED')
      and football_data_match_id is not null

),

one_row_per_side as (

    select
        match_key,
        match_date,
        season,
        competition_code,
        competition_name,
        matchday,
        referee_key,
        stadium_key,
        home_team_key as team_key,
        away_team_key as opponent_key,
        true as is_home,
        home_goals as goals_for,
        away_goals as goals_against,
        home_xg as xg_for,
        away_xg as xg_against,
        home_npxg as npxg_for,
        away_npxg as npxg_against,
        home_deep as deep_for,
        away_deep as deep_against,
        home_ppda as ppda,
        away_ppda as opponent_ppda,
        home_xpts as xpts,
        away_xpts as opponent_xpts
    from counting_matches

    union all

    select
        match_key,
        match_date,
        season,
        competition_code,
        competition_name,
        matchday,
        referee_key,
        -- Still the home club's ground: the away side's row describes the same
        -- fixture, played at the same stadium.
        stadium_key,
        away_team_key as team_key,
        home_team_key as opponent_key,
        false as is_home,
        away_goals as goals_for,
        home_goals as goals_against,
        away_xg as xg_for,
        home_xg as xg_against,
        away_npxg as npxg_for,
        home_npxg as npxg_against,
        away_deep as deep_for,
        home_deep as deep_against,
        away_ppda as ppda,
        home_ppda as opponent_ppda,
        away_xpts as xpts,
        home_xpts as opponent_xpts
    from counting_matches

)

select
    *,

    -- Which match of the season this is for this club, 1-based. Lives here rather
    -- than in a mart because two marts order a club's season the same way and the
    -- ordering may only be defined once: `mart_team_form` rolls a window over it
    -- and `mart_team_season_half` cuts the season in two by it. `match_key` breaks
    -- ties so two matches on one date always order the same way between runs.
    row_number() over (
        partition by team_key, season, competition_code
        order by match_date, match_key
    ) as match_number,

    goals_for - goals_against as goal_difference,
    xg_for - xg_against as xg_difference,

    -- Points from the scoreline rather than from `fact_matches.result`: one
    -- derivation that is right for an AWARDED match too, and that cannot disagree
    -- with the goals in the same row. `assert_points_agree_with_reported_result`
    -- checks it against Gold's own `result` wherever Gold reports one.
    --
    -- The null guard is not decoration. Gold allows a null score, and without it
    -- an unplayed fixture that slipped through the status filter would quietly
    -- score 0 points — a loss — instead of failing the `not_null` test below.
    case
        when goals_for is null or goals_against is null then null
        when goals_for > goals_against then 3
        when goals_for = goals_against then 1
        else 0
    end as points

from one_row_per_side
