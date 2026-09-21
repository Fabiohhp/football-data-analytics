-- int_team_matches derives points from the scoreline rather than from
-- `fact_matches.result`, because that is also right for an AWARDED match. This
-- checks the derivation against Gold's own reported result wherever Gold reports
-- one, from both sides of every fixture.

with sides as (

    select
        t.match_key,
        t.team_key,
        t.is_home,
        t.goals_for,
        t.goals_against,
        t.points,
        m.result
    from {{ ref('int_team_matches') }} t
    join {{ ref('stg_matches') }} m on m.match_key = t.match_key
    where m.result is not null

)

select *
from sides
where points <> case
        when result = 'DRAW' then 1
        -- True for the home club when the home club won, and for the away club
        -- when the away club won.
        when (result = 'HOME_TEAM') = is_home then 3
        else 0
    end
