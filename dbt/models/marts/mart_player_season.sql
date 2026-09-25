-- One row per player per season: totals, per-90s, and the two finishing measures
-- that §8 question 2 turns on.
--
-- **Grain is player × season, not player × season × club** — a deliberate change
-- from the plan in CLAUDE.md §6, for the reason behind §5 trap 1. That trap says
-- not to group by `player_key`, because a transferred player has several and the
-- season splits in two. Splitting by *club* does the same thing for the same
-- player: 94 player-seasons in 2024/25 and 92 in 2025/26 span two clubs while
-- clearing the minutes floor, and at club grain each half is a different, shorter
-- season that often clears no floor at all. A question about whether a player
-- finishes well needs their whole season. The club is kept as an attribute —
-- `primary_team_name`, where they played the most minutes, plus `clubs` — and
-- `int_player_matches` still has the per-club detail if a later analysis wants it.
--
-- **No match filter.** Player totals keep the Understat half of a split fixture,
-- because that is where the goals are (§5 trap 13). That is the opposite choice
-- from `int_team_matches`, which drops it, and the two disagree by about 0.3% by
-- design — each states which rule it used, as §5 requires.
--
-- **Two different finishing measures, and the second is the real one.**
-- `goals_minus_xg` uses Understat's per-player xG, which *includes penalties*
-- (§5 trap 8) — a penalty taker's number is then mostly a statement about
-- penalties. `np_goals_minus_npxg` strips them by going to the shots, and is what
-- the analysis uses.

with per_player_season as (

    select
        understat_player_id,
        season,

        count(*)                  as matches,
        sum(minutes_played)       as minutes,
        count(distinct team_key)  as clubs,

        sum(goals)                as goals,
        sum(own_goals)            as own_goals,
        sum(assists)              as assists,
        sum(shots)                as shots_reported,
        sum(shots_deduplicated)   as shots,
        sum(key_passes)           as key_passes,
        sum(xg)                   as xg,
        sum(xa)                   as xa,
        sum(xg_chain)             as xg_chain,
        sum(xg_buildup)           as xg_buildup,
        sum(yellow_cards)         as yellow_cards,
        sum(red_cards)            as red_cards,

        sum(penalties_taken)      as penalties_taken,
        sum(penalty_goals)        as penalty_goals,
        sum(np_goals)             as np_goals,
        sum(npxg)                 as npxg,

        min(match_date)           as first_match_date,
        max(match_date)           as last_match_date,
        -- 0.3% of player-match rows sit on a match with no competition code; the
        -- club-season lookup fills them, and this says so rather than assuming it.
        count(competition_code)   as matches_with_competition

    from {{ ref('int_player_matches') }}
    group by 1, 2

),

-- Where the player spent most of the season. Minutes, then `team_key`, so a
-- player who split a season exactly evenly still lands the same way every run.
primary_club as (

    select
        understat_player_id,
        season,
        team_key as primary_team_key
    from (
        select
            understat_player_id,
            season,
            team_key,
            row_number() over (
                partition by understat_player_id, season
                order by sum(minutes_played) desc, team_key
            ) as rn
        from {{ ref('int_player_matches') }}
        group by 1, 2, 3
    )
    where rn = 1

)

select
    s.understat_player_id,
    p.player_name,
    s.season,
    c.primary_team_key,
    t.team_name    as primary_team_name,
    cs.competition_code,
    cs.competition_name,
    s.clubs,

    s.matches,
    s.minutes,
    s.matches_with_competition,

    s.goals,
    s.own_goals,
    s.assists,
    s.shots,
    s.shots_reported,
    s.key_passes,
    s.xg,
    s.xa,
    s.xg_chain,
    s.xg_buildup,
    s.yellow_cards,
    s.red_cards,

    s.penalties_taken,
    s.penalty_goals,
    s.np_goals,
    s.npxg,

    -- Finishing. Positive means more goals than the chances were worth.
    s.goals - s.xg           as goals_minus_xg,
    s.np_goals - s.npxg      as np_goals_minus_npxg,

    -- Per 90. `nullif` rather than a filter: a player with zero recorded minutes
    -- keeps their row and their totals, and reads null for the rates instead of
    -- dividing by zero or quietly disappearing from a leaderboard.
    90.0 * s.goals    / nullif(s.minutes, 0) as goals_per_90,
    90.0 * s.np_goals / nullif(s.minutes, 0) as np_goals_per_90,
    90.0 * s.xg       / nullif(s.minutes, 0) as xg_per_90,
    90.0 * s.npxg     / nullif(s.minutes, 0) as npxg_per_90,
    90.0 * s.assists  / nullif(s.minutes, 0) as assists_per_90,
    90.0 * s.xa       / nullif(s.minutes, 0) as xa_per_90,
    90.0 * s.shots    / nullif(s.minutes, 0) as shots_per_90,
    90.0 * (s.np_goals - s.npxg) / nullif(s.minutes, 0) as np_goals_minus_npxg_per_90,

    -- --- reading aids -------------------------------------------------------
    -- "Is 0.80 npxG per 90 good?" is the question a rate invites and cannot answer
    -- on its own. A percentile answers it, and it is a metric, not formatting: it
    -- depends entirely on which players are in the comparison. The population is
    -- **the same season and the same league, among players who clear the minutes
    -- floor** — comparing a Bundesliga forward against every squad player in Europe
    -- would flatter him, and comparing across seasons would move the yardstick.
    --
    -- Players below the floor get NULL rather than a percentile against a population
    -- they are not part of. 0 = lowest, 100 = highest.
    {% set rate_columns = [
        ("npxg_per_90", "npxg_per_90"),
        ("np_goals_per_90", "np_goals_per_90"),
        ("xa_per_90", "xa_per_90"),
        ("shots_per_90", "shots_per_90"),
    ] %}
    {% for name, expression in rate_columns %}
    case when s.minutes >= {{ var('min_minutes') }} then round(100 * percent_rank() over (
        partition by s.season, cs.competition_code,
                     (s.minutes >= {{ var('min_minutes') }})
        order by 90.0 * s.{{ 'npxg' if name == 'npxg_per_90'
                             else 'np_goals' if name == 'np_goals_per_90'
                             else 'xa' if name == 'xa_per_90'
                             else 'shots' }} / nullif(s.minutes, 0)
    )) end as {{ name }}_percentile,
    {% endfor %}

    -- The minutes floor is a dbt var (`min_minutes`, default 900 — ten full
    -- matches), carried as a column so a chart can filter on it and state it
    -- without hardcoding the number a second time (CLAUDE.md §6).
    {{ var('min_minutes') }}                 as min_minutes,
    s.minutes >= {{ var('min_minutes') }}    as meets_minutes_floor,

    s.first_match_date,
    s.last_match_date

from per_player_season s
join primary_club c
  on c.understat_player_id = s.understat_player_id and c.season = s.season
left join {{ ref('int_club_seasons') }} cs
       on cs.team_key = c.primary_team_key and cs.season = s.season
left join {{ ref('stg_players') }} p
       on p.understat_player_id = s.understat_player_id and p.is_current
left join {{ ref('stg_teams') }} t on t.team_key = c.primary_team_key
