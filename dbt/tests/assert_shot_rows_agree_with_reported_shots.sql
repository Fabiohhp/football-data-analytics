-- Understat reports each player's shot count on their match line *and* ships the
-- individual shots. The two must agree, or the deduplication in `int_shots` is
-- removing real shots rather than copies.
--
-- Exact, measured across all 115,410 player-match rows, once own goals are
-- excluded from the shot side: an `OwnGoal` is a row in `fact_shots` but is not
-- counted in `fact_player_events.shots`. That is the sharp end of §5 trap 11 —
-- own goals are a shot *result*, so they arrive wherever shots do.
--
-- This is the test that would fail if the dedup key were ever loosened. Widening
-- it to drop genuinely distinct shots shows up here immediately, where a summed
-- xG that is quietly 5.9 too low would not.

select
    player_event_key,
    understat_match_id,
    understat_player_id,
    shots              as reported_by_understat,
    shots_deduplicated as shot_rows_after_dedup
from {{ ref('int_player_matches') }}
where shots is distinct from shots_deduplicated
