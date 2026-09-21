-- Key 0 is the `Unknown` dimension member (§5 trap 3). The team keys are clean in
-- the current snapshot, and if that changed, int_team_matches would fold every
-- unmatched club into one phantom team sitting in the league table.
--
-- Referees are deliberately not checked: 64 matches genuinely report no official,
-- so `referee_key = 0` is expected and a per-referee metric filters it out and says
-- how many rows that removed instead.

select 'team_key' as column_name, count(*) as rows_at_key_zero
from {{ ref('int_team_matches') }}
where team_key = 0
having count(*) > 0

union all

select 'opponent_key', count(*)
from {{ ref('int_team_matches') }}
where opponent_key = 0
having count(*) > 0
