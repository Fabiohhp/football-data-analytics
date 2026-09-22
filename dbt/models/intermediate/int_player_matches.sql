-- One row per player per match: Understat's player line, plus the two things it
-- does not carry — a season, and anything non-penalty.
--
-- **Every row of `stg_player_events` survives.** No filter, and the joins are all
-- LEFT. Two reasons, both from §5. A player's goals live on the Understat half of
-- a split fixture (trap 13), so the `football_data_match_id` filter that a league
-- table needs would lose a goal or two a season here — Retegui would read 24
-- rather than 25. And `match_key` is nullable (trap 4), so an inner join to the
-- match would silently drop orphan rows; there are none today, and the models are
-- written so that there being some tomorrow costs nothing.
--
-- **Shots join on `(understat_match_id, player_key)`.** Both facts carry
-- `understat_match_id` NOT NULL, so this join cannot be broken by trap 4 the way a
-- `match_key` join could. Measured: all 93,988 deduplicated shots find their
-- player-event row this way, and `fact_player_events.xg` equals the sum of that
-- player's shot xG to the fourth decimal for all 3,276 players who took one —
-- which is what makes npxG derived here trustworthy.
--
-- **npXG has to come from the shots** because there is no non-penalty xG per
-- player anywhere in Gold (§5 trap 8): `fact_player_events.xg` includes penalties.

with shots_per_player_match as (

    select
        understat_match_id,
        player_key,

        -- Own goals are excluded from the shot *count* — an own goal is not an
        -- attempt at the opponent's goal. Understat agrees: measured across all
        -- 115,410 player-match rows, `fact_player_events.shots` equals the shot
        -- rows minus the own goals, exactly and with no exceptions. Excluding
        -- them here makes the two sources agree on the nose, which is what
        -- `assert_shot_rows_agree_with_reported_shots` then holds them to.
        count(*) filter (where result <> 'OwnGoal')        as shots_taken,

        count(*) filter (where is_penalty)                 as penalties_taken,
        count(*) filter (where is_penalty and is_goal)     as penalty_goals,
        count(*) filter (where not is_penalty and is_goal) as np_goals,

        -- Every row, own goals included, so this can be checked against
        -- `fact_player_events.xg`. It costs nothing to include them: all 299 own
        -- goals in the snapshot carry exactly 0.0000 xG.
        sum(xg)                                            as shot_xg,

        -- Non-penalty *and* non-own-goal, so that the numerator and denominator
        -- of `np_goals - npxg` describe the same set of attempts.
        sum(xg) filter (where not is_penalty and result <> 'OwnGoal') as npxg

    from {{ ref('int_shots') }}
    group by 1, 2

)

select
    e.player_event_key,
    e.understat_match_id,
    e.match_key,
    e.match_date,
    e.season,
    e.understat_player_id,
    e.player_key,
    e.team_key,
    cs.competition_code,
    cs.competition_name,
    e.position,

    e.minutes_played,
    e.goals,
    e.own_goals,
    e.assists,
    e.shots,
    e.key_passes,
    e.xg,
    e.xa,
    e.xg_chain,
    e.xg_buildup,
    e.yellow_cards,
    e.red_cards,

    -- A player with no shot in a match really did take none, so zero is the right
    -- value here — unlike a null xG on a match, which means "not measured" and is
    -- never zeroed (§5 trap 7). The distinction is the whole point: these counts
    -- come from rows that exist, not from a measurement that is missing.
    coalesce(sp.shots_taken, 0)     as shots_deduplicated,
    coalesce(sp.penalties_taken, 0) as penalties_taken,
    coalesce(sp.penalty_goals, 0)   as penalty_goals,
    coalesce(sp.np_goals, 0)        as np_goals,
    coalesce(sp.npxg, 0.0)          as npxg,
    coalesce(sp.shot_xg, 0.0)       as shot_xg

from {{ ref('stg_player_events') }} e
left join shots_per_player_match sp
       on sp.understat_match_id = e.understat_match_id
      and sp.player_key = e.player_key
left join {{ ref('int_club_seasons') }} cs
       on cs.team_key = e.team_key and cs.season = e.season
