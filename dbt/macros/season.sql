{#
    Season derivation — CLAUDE.md §5, trap 5.

    Only `fact_matches` carries `season`. Every other fact has to derive it, and
    the derivation has to be Part 1's, not a plausible-looking one of our own:
    Part 1's `season_label()` in `src/common/sources.py` labels a season by its
    starting year with an **August cutoff**, so a match played in July 2025
    belongs to 2024/25 and one played in August 2025 to 2025/26.

    Defined once here and reused, so no model can quietly disagree with another.
    `tests/assert_derived_season_matches_gold.sql` compares the output against
    Gold's own `season` column on every match — the one place the two can be
    checked against each other.

    Known limit, inherited from Part 1: the cutoff mislabels matches played in
    August of a season that ran late, as 2019/20 did. Nothing in the loaded range
    is affected; if that season is ever backfilled, this is where the fix goes.
#}

{% macro season_start_year(match_date) -%}
    (case
        when month({{ match_date }}) >= 8 then year({{ match_date }})
        else year({{ match_date }}) - 1
    end)
{%- endmacro %}


{% macro season_label(match_date) -%}
    (
        cast({{ season_start_year(match_date) }} as varchar)
        || '/'
        || lpad(cast(({{ season_start_year(match_date) }} + 1) % 100 as varchar), 2, '0')
    )
{%- endmacro %}
