-- Every penalty is taken from one point of the pitch, so if the coordinates mean
-- what §5 trap 10 says they do, all of them collapse onto `(0.885, 0.5)`.
--
-- This is the check that establishes the orientation of the whole coordinate
-- system — which way `x` runs, and therefore whether every shot map in the
-- notebooks and on the dashboard is drawn forwards or backwards. It is cheap, and
-- it is the only thing standing between a reversed axis and a plausible-looking
-- picture, so it runs on every build rather than living in a notebook.

select
    count(*)                                  as penalties,
    min(x)                                    as min_x,
    max(x)                                    as max_x,
    min(y)                                    as min_y,
    max(y)                                    as max_y,
    round(avg(xg), 3)                         as mean_xg
from {{ ref('mart_shots') }}
where is_penalty
having min(x) <> 0.885
    or max(x) <> 0.885
    or min(y) <> 0.5
    or max(y) <> 0.5
    -- A penalty is worth about 0.76 goals. A band this wide will not trip on a
    -- season's worth of drift, but catches the situation being mislabelled.
    or avg(xg) not between 0.70 and 0.80
