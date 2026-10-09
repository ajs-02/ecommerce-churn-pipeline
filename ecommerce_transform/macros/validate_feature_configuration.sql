{% macro validate_feature_configuration() %}
{% if execute %}
    {% set observation = var('observation_end_ts', none) %}
    {% set as_of = var('as_of_date', none) %}
    {% if observation is not none %}
        {% set query %}
            select '{{ observation | replace("'", "''") }}'::timestamp < max(order_purchase_ts)
            from {{ ref('stg_orders') }}
        {% endset %}
        {% if run_query(query).rows[0][0] %}
            {{ exceptions.raise_compiler_error('observation_end_ts precedes recorded purchases') }}
        {% endif %}
    {% endif %}
    {% if as_of is not none %}
        {% set query %}
            select '{{ as_of | replace("'", "''") }}'::date < max(order_purchase_ts)::date
            from (
                select distinct on (c.customer_unique_id) o.order_purchase_ts
                from {{ ref('stg_orders') }} o
                join {{ ref('stg_customers') }} c on c.customer_id=o.customer_id
                where o.order_status='delivered'
                order by c.customer_unique_id,o.order_purchase_ts,o.order_id collate "C"
            ) anchors
        {% endset %}
        {% if run_query(query).rows[0][0] %}
            {{ exceptions.raise_compiler_error('as_of_date produces negative anchor recency') }}
        {% endif %}
    {% endif %}
{% endif %}
{% endmacro %}
