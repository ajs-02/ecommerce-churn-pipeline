{{ config(materialized='table') }}
{{ validate_feature_configuration() }}
{{ validate_feature_money() }}
-- One candidate for every first-delivered customer, selected before exclusions.
with all_orders as (
    select c.customer_unique_id,c.customer_state,o.*
    from {{ ref('stg_orders') }} o
    join {{ ref('stg_customers') }} c on c.customer_id=o.customer_id
),
anchor as (
    select distinct on (customer_unique_id) *
    from all_orders where order_status='delivered'
    order by customer_unique_id,order_purchase_ts,order_id collate "C"
),
settings as (
    select
        {% if var('as_of_date', none) is not none %}
        '{{ var("as_of_date") | replace("'", "''") }}'::date
        {% else %}maximum_purchase_ts::date{% endif %} as as_of_date,
        {% if var('observation_end_ts', none) is not none %}
        '{{ var("observation_end_ts") | replace("'", "''") }}'::timestamp
        {% else %}maximum_purchase_ts{% endif %} as observation_end_ts,
        '{% if var("observation_end_ts", none) is not none %}explicit_override{% else %}maximum_recorded_purchase{% endif %}'::text as observation_end_provenance
    from (select max(order_purchase_ts) as maximum_purchase_ts from {{ ref('stg_orders') }}) recorded
),
activity as (
    select a.customer_unique_id,
        count(distinct o.order_id) filter (where o.order_status='delivered') as total_orders,
        count(distinct o.order_id) filter (
            where o.order_id<>a.order_id
                and o.order_purchase_ts between a.order_purchase_ts and a.order_purchase_ts+interval '180 days'
        ) as repeat_order_count
    from anchor a join all_orders o using(customer_unique_id)
    group by a.customer_unique_id
),
items as (
    select order_id,count(*) as item_count,bool_or(item_price=0) as has_zero_item_price,
        case when count(freight_value)=count(*) then sum(freight_value) end as freight_value,
        case when count(item_price)=count(*) and count(freight_value)=count(*) then sum(item_price+freight_value) end as item_spend
    from {{ ref('stg_order_items') }} group by order_id
),
reviews as (
    select order_id,count(*)>0 as has_first_order_review,
        coalesce(bool_or(review_score<(select avg(review_score) from {{ ref('stg_order_reviews') }})),false) as review_below_average
    from {{ ref('stg_order_reviews') }} group by order_id
),
values as (
    select a.customer_unique_id,a.customer_state,a.order_id as first_delivered_order_id,
        a.order_purchase_ts as first_delivered_purchase_ts,
        a.order_purchase_ts+interval '180 days' as target_window_end_ts,
        s.observation_end_ts,s.observation_end_provenance,s.as_of_date,
        a.order_purchase_ts+interval '180 days'<=s.observation_end_ts as has_complete_followup,
        case when act.repeat_order_count>0 then 1
             when a.order_purchase_ts+interval '180 days'<=s.observation_end_ts then 0 end as repeat_within_180_days,
        act.total_orders,act.repeat_order_count,
        case when p.order_id is null then i.item_spend else p.total_payment_value end as total_spent,
        p.order_id is null and i.item_spend is not null as spend_recovered_from_items,
        coalesce(i.has_zero_item_price,false) as has_zero_item_price,
        i.item_spend,(s.as_of_date-a.order_purchase_ts::date)::bigint*86400 as seconds_since_first_purchase,
        p.favorite_payment_type,i.item_count,i.freight_value,coalesce(p.used_voucher,false) as used_voucher,
        extract(epoch from a.order_delivered_customer_ts-a.order_purchase_ts) as delivery_seconds,
        extract(epoch from a.order_approved_ts-a.order_purchase_ts) as approval_seconds,
        extract(epoch from a.order_delivered_carrier_ts-a.order_purchase_ts) as carrier_seconds,
        case when a.order_delivered_customer_ts is not null and a.order_estimated_delivery_ts is not null
            then greatest(a.order_delivered_customer_ts::date-a.order_estimated_delivery_ts::date,0)::bigint*86400 end as after_estimated_delivery_seconds,
        coalesce(r.review_below_average,false) as review_below_average,
        coalesce(r.has_first_order_review,false) as has_first_order_review,
        a.order_approved_ts,a.order_delivered_carrier_ts,a.order_delivered_customer_ts,a.order_estimated_delivery_ts
    from anchor a cross join settings s join activity act using(customer_unique_id)
    left join items i on i.order_id=a.order_id
    left join {{ ref('stg_order_payments') }} p on p.order_id=a.order_id
    left join reviews r on r.order_id=a.order_id
)
 ,reasons as (
    select *,array_remove(array[
        case when order_approved_ts is null then 'missing_approval_timestamp' end,
        case when order_delivered_carrier_ts is null then 'missing_carrier_timestamp' end,
        case when order_delivered_customer_ts is null then 'missing_delivery_timestamp' end,
        case when order_estimated_delivery_ts is null then 'missing_estimate_timestamp' end,
        case when item_count is null then 'no_items' end,
        case when customer_state is null then 'null_customer_state' end,
        case when total_spent is null then 'null_total_spent' end,
        case when favorite_payment_type is null then 'null_favorite_payment_type' end,
        case when freight_value is null then 'null_freight_value' end,
        case when seconds_since_first_purchase is null then 'null_recency' end,
        case when approval_seconds<0 then 'negative_approval_seconds' end,
        case when carrier_seconds<0 then 'negative_carrier_seconds' end,
        case when delivery_seconds<0 then 'negative_delivery_seconds' end
    ],null)::text[] as exclusion_reasons,
        array_remove(array[
            case when order_delivered_carrier_ts<order_approved_ts then 'carrier_before_approval' end,
            case when order_delivered_customer_ts<order_delivered_carrier_ts then 'delivery_before_carrier' end,
            case when order_approved_ts>order_delivered_customer_ts then 'approval_after_delivery' end,
            case when order_estimated_delivery_ts<first_delivered_purchase_ts then 'estimate_before_purchase' end,
            case when has_zero_item_price then 'zero_item_price' end,
            case when total_spent=0 then 'zero_order_spend' end,
            case when not spend_recovered_from_items and abs(total_spent-item_spend)>0.01 then 'payment_item_discrepancy' end
        ],null)::text[] as warning_reasons
    from values
)
select *,cardinality(exclusion_reasons)=0 as is_eligible from reasons
