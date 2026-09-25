{#
    Undo HTML escaping in source names — CLAUDE.md §5, trap 15.

    Understat serves player names HTML-escaped, and Part 1 stores them exactly as
    received. So Gold really holds `Nico O&#039;Reilly`, and 16 players across 399
    event rows read that way on a chart, in a dropdown and in a notebook table.

    **The right fix is in Part 1, at ingestion.** This is the wrong layer: it repairs
    a value rather than renaming or casting it, and every consumer of Gold has to do
    the same repair independently. It is here because a dashboard that misspells a
    player is not something to leave standing while an upstream change is scheduled,
    and because `assert_no_html_entities_in_names` then fails loudly if Part 1 starts
    emitting an entity this macro does not know about.

    `&amp;` is decoded **last**, deliberately. Decoding it first would turn a
    double-escaped `&amp;#039;` into `&#039;` and then into an apostrophe, inventing
    a character that was never in the name. Every other entity is decoded before the
    ampersand that could have produced it.

    Legitimate ampersands survive: `Brighton & Hove Albion` is stored unescaped and
    matches none of these patterns.
#}

{% macro html_unescape(column) -%}
    {%- set replacements = [
        ("&#039;", "'"),
        ("&#39;", "'"),
        ("&apos;", "'"),
        ("&#x27;", "'"),
        ("&quot;", '"'),
        ("&#034;", '"'),
        ("&#34;", '"'),
        ("&lt;", "<"),
        ("&gt;", ">"),
        ("&nbsp;", " "),
        ("&amp;", "&"),
    ] -%}
    {%- set ns = namespace(expression = column) -%}
    {%- for entity, character in replacements -%}
        {%- set literal = "''" if character == "'" else character -%}
        {%- set ns.expression =
            "replace(" ~ ns.expression ~ ", '" ~ entity ~ "', '" ~ literal ~ "')" -%}
    {%- endfor -%}
    {{ ns.expression }}
{%- endmacro %}
