-- Every shot, once, with the player, team, match and season attached and ready to
-- display: the shot map on the dashboard and the "where do goals come from"
-- analysis (§8 question 4) both read this.
--
-- The deduplication and the season/competition resolution happen upstream in
-- `int_shots`, because `int_player_matches` needs exactly the same deduplicated
-- rows to build npxG from and that calculation may only exist once.
--
-- Coordinates are Understat's, normalized to [0, 1] and **not** rescaled here
-- (§5 trap 10). Higher `x` is closer to the goal being attacked, `y = 0.5` is the
-- middle of the pitch, and the penalty spot is exactly `(0.885, 0.5)`. The
-- notebooks' mplsoccer plots multiply by 100 to land on an Opta pitch, and the
-- dashboard's hand-drawn SVG uses them as-is; both therefore agree on orientation.

select
    s.shot_key,
    s.understat_shot_id,
    s.match_key,
    s.understat_match_id,
    s.match_date,
    s.season,
    s.competition_code,
    s.competition_name,

    s.understat_player_id,
    p.player_name,
    s.team_key,
    t.team_name,
    s.is_home,

    s.assist_player_key,
    a.player_name as assist_player_name,

    s.minute,
    s.x,
    s.y,
    s.xg,
    s.result,
    s.situation,
    s.shot_type,
    s.is_goal,
    s.is_penalty

from {{ ref('int_shots') }} s
-- Names come from the *current* player version. `dim_players` is SCD Type 2, but
-- exactly one version per `understat_player_id` is current (4,048 of 4,048), so
-- this is a one-row lookup and cannot fan the grain out. A name is a label here,
-- not a fact about the match — the club the shot was taken for is `team_key` on
-- the shot itself (§5 trap 2), never the player's current club.
left join {{ ref('stg_players') }} p
       on p.understat_player_id = s.understat_player_id and p.is_current
left join {{ ref('stg_players') }} a
       on a.player_key = s.assist_player_key
left join {{ ref('stg_teams') }} t on t.team_key = s.team_key
