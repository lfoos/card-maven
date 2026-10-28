{#- "Raw", or grader and grade without a trailing ".0": "PSA 10", "BGS 9.5". -#}
{% macro condition_bucket(condition, grader, grade) -%}
case
    when {{ condition }} = 'graded'
        then {{ grader }} || ' ' || regexp_replace({{ grade }}::text, '\.0+$', '')
    else 'Raw'
end
{%- endmacro %}

{#- The as-of date for windowed marts: var('as_of_date'), else today in UTC. -#}
{% macro as_of_date() -%}
{%- if var('as_of_date') -%}
date '{{ var("as_of_date") }}'
{%- else -%}
(now() at time zone 'utc')::date
{%- endif -%}
{%- endmacro %}
