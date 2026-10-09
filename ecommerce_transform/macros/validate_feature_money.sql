{% macro validate_feature_money() %}
{% if execute %}
    {% set query %}
        select exists(
            select 1 from {{ source('olist', 'order_items') }}
            where price::numeric<0 or freight_value::numeric<0
                or price::numeric::text in ('NaN','Infinity','-Infinity')
                or freight_value::numeric::text in ('NaN','Infinity','-Infinity')
            union all
            select 1 from {{ source('olist', 'order_payments') }}
            where payment_value::numeric<0
                or payment_value::numeric::text in ('NaN','Infinity','-Infinity')
        )
    {% endset %}
    {% if run_query(query).rows[0][0] %}
        {{ exceptions.raise_compiler_error('Raw monetary values must be finite and nonnegative; feature publication aborted') }}
    {% endif %}
{% endif %}
{% endmacro %}
