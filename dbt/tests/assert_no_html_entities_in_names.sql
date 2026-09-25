-- No name reaches a mart still HTML-escaped (§5 trap 15).
--
-- Understat serves names escaped and Part 1 stores them that way, so Gold really
-- contains `Nico O&#039;Reilly`. `html_unescape` repairs the entities we have seen;
-- this fails if one arrives that it does not know about, which is the only way that
-- would otherwise be noticed — by a reader spotting it on a chart.
--
-- The pattern matches the *shape* of an entity rather than a bare ampersand, so
-- `Brighton & Hove Albion` passes, as it must.

with names as (

    select 'mart_player_season' as source, player_name as name
    from {{ ref('mart_player_season') }}

    union all
    select 'mart_shots.player', player_name from {{ ref('mart_shots') }}

    union all
    select 'mart_shots.team', team_name from {{ ref('mart_shots') }}

    union all
    select 'mart_team_season', team_name from {{ ref('mart_team_season') }}

    union all
    select 'mart_team_form.team', team_name from {{ ref('mart_team_form') }}

    union all
    select 'mart_team_form.opponent', opponent_name from {{ ref('mart_team_form') }}

)

select distinct source, name
from names
where regexp_matches(name, '&(#[0-9]+|#[xX][0-9A-Fa-f]+|[A-Za-z]+);')
