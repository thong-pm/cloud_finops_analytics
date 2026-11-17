{% macro clean_null_str(col) %}
    nullif(nullif(trim(cast({{ col }} as {{ dbt.type_string() }})), ''), 'NULL')
{% endmacro %}

{% macro safe_cast_numeric(col) %}
    coalesce(
        cast({{ clean_null_str(col) }} as {{ dbt.type_numeric() }}),
        0
    )
{% endmacro %}

{% macro safe_cast_date(col) %}
    {% if target.type == 'bigquery' %}
        date(cast({{ col }} as timestamp), 'UTC')
    {% else %}
        cast((cast({{ col }} as timestamptz) at time zone 'UTC') as date)
    {% endif %}
{% endmacro %}

{% macro json_extract_tag(col, key) %}
    {% if target.type == 'bigquery' %}
        json_extract_scalar(
            case
                when {{ clean_null_str(col) }} is not null
                 and left({{ clean_null_str(col) }}, 1) = '{'
                then {{ clean_null_str(col) }}
                else null
            end,
            '$.{{ key }}'
        )
    {% else %}
        case
            when {{ clean_null_str(col) }} is not null
             and left({{ clean_null_str(col) }}, 1) = '{'
            then ({{ clean_null_str(col) }}::jsonb)->>'{{ key }}'
            else null
        end
    {% endif %}
{% endmacro %}
