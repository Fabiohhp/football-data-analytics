-- Every shot, once, with the match and season it belongs to attached.
--
-- Two jobs, both of which more than one downstream model needs, which is why they
-- happen here rather than in `mart_shots`:
--
-- **Deduplication (§5 trap 14).** Understat returned every shot of two La Liga
-- matches twice under different shot ids, so 46 rows are genuine duplicates and
-- shot counts and summed xG double there. Duplicates are found by the *shape* of a
-- shot, not its id — the ids differ, which is exactly why `distinct shot_key`
-- would not help.
--
-- The documented shape is `(match_key, player_key, minute, result, x, y, xg)`;
-- this uses `understat_match_id` in place of `match_key` **on purpose**.
-- `match_key` is nullable (§5 trap 4) and SQL groups NULLs together, so a
-- `match_key`-based dedup would treat two shots from two *different* unmatched
-- matches as copies of each other whenever the rest of the shape agreed —
-- over-deduplicating exactly where the data is already weakest.
-- `fact_shots.understat_match_id` is NOT NULL, so it cannot do that.
--
-- **Resolving the match.** Joined on `understat_match_id` rather than `match_key`,
-- for the same reason: it is the shot's own non-null key. The competition comes
-- from `int_club_seasons`, not from the match, because the match is the Understat
-- half of a split fixture for 307 of these shots and carries no competition code.

with deduplicated as (

    select *
    from {{ ref('stg_shots') }}
    -- Keep the lowest shot_key of each set of copies, so the survivor is stable
    -- from run to run rather than whichever row the scan happened to reach first.
    qualify row_number() over (
        partition by understat_match_id, player_key, minute, result, x, y, xg
        order by shot_key
    ) = 1

)

select
    s.shot_key,
    s.understat_shot_id,
    s.understat_match_id,
    s.match_key,
    m.match_date,
    m.season,
    cs.competition_code,
    cs.competition_name,

    s.player_key,
    p.understat_player_id,
    s.team_key,
    s.assist_player_key,
    s.is_home,
    s.minute,

    s.x,
    s.y,
    s.xg,
    s.result,
    s.situation,
    s.shot_type,

    -- The two flags every shot metric starts from, so no model has to remember
    -- that `OwnGoal` is a value of `result` and that `MissedShots` is plural
    -- (§5 trap 11). `is_goal` deliberately excludes own goals: an own goal is a
    -- goal for the *opponent*, and this row sits on the scorer's own team.
    s.result = 'Goal' as is_goal,
    s.situation = 'Penalty' as is_penalty

from deduplicated s
left join {{ ref('stg_matches') }} m on m.understat_match_id = s.understat_match_id
left join {{ ref('int_club_seasons') }} cs
       on cs.team_key = s.team_key and cs.season = m.season
left join {{ ref('stg_players') }} p on p.player_key = s.player_key
