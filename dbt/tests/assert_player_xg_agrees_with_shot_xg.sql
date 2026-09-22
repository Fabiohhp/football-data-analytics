-- `fact_player_events.xg` must equal the sum of that player's shot xG in the same
-- match. This is what makes npxG trustworthy: there is no non-penalty xG per
-- player in Gold (§5 trap 8), so every npxG figure in this project is rebuilt from
-- `fact_shots` — and it is only worth rebuilding if the shots reconstruct the
-- total Understat itself reports.
--
-- Measured: the largest disagreement across 115,410 rows is 0.0002, which is
-- rounding on a NUMERIC(8,4) sum. The tolerance is 0.01, comfortably above the
-- noise and far below anything that would matter to a conclusion.
--
-- It also pins the join. `int_player_matches` joins the two facts on
-- `(understat_match_id, player_key)` rather than on `match_key`, because
-- `match_key` is nullable (§5 trap 4); if that join were ever changed to one that
-- mismatches rows, the xG on either side would stop lining up here.

select
    player_event_key,
    understat_match_id,
    understat_player_id,
    xg      as reported_by_understat,
    shot_xg as summed_from_shots,
    abs(xg - shot_xg) as gap
from {{ ref('int_player_matches') }}
where xg is not null
  and abs(xg - shot_xg) > 0.01
