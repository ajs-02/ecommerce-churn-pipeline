{{ config(materialized='table') }}

-- Grain: one row per customer_unique_id with a complete first delivered order.
-- Predictors come from that order only. The customer is absent when the order
-- lacks order_approved_ts, order_delivered_carrier_ts,
-- order_delivered_customer_ts, or order_estimated_delivery_ts.
-- Do not impute those durations and do not emit *_missing columns.
-- total_orders is the lifetime delivered count and is label-only. Do not use it
-- as a predictor.
-- The review-score average is avg(review_score) over all of stg_order_reviews,
-- not the first-order frame. A later train/test split sees that global scalar.
-- Do not join products or translation. Do not emit category or photo columns.
-- One delivered first order has no payment rows (Olist source gap). For that
-- case, total_spent and average_order_value use sum(item_price + freight_value)
-- instead of coalescing the payment total to 0. The test is a missing payment
-- row (payment_order_id is null), not a null favorite_payment_type.
-- favorite_payment_type stays null.

with as_of as (
    select
        coalesce(
            {% if var('as_of_date', none) %}
            '{{ var("as_of_date") }}'::date
            {% else %}
            null
            {% endif %},
            max(order_purchase_ts)::date
        ) as as_of_date
    from {{ ref('stg_orders') }}
),

delivered_orders as (
    select
        c.customer_unique_id,
        c.customer_state,
        o.order_id,
        o.order_purchase_ts,
        o.order_approved_ts,
        o.order_delivered_carrier_ts,
        o.order_delivered_customer_ts,
        o.order_estimated_delivery_ts,
        coalesce(p.total_payment_value, 0) as total_payment_value,
        p.order_id as payment_order_id,
        p.favorite_payment_type,
        coalesce(p.used_voucher, false) as used_voucher
    from {{ ref('stg_customers') }} c
    inner join {{ ref('stg_orders') }} o
        on c.customer_id = o.customer_id
    left join {{ ref('stg_order_payments') }} p
        on o.order_id = p.order_id
    where o.order_status = 'delivered'
),

lifetime as (
    select
        customer_unique_id,
        count(distinct order_id) as total_orders
    from delivered_orders
    group by customer_unique_id
),

first_order as (
    select distinct on (customer_unique_id)
        customer_unique_id,
        customer_state,
        order_id,
        order_purchase_ts,
        order_approved_ts,
        order_delivered_carrier_ts,
        order_delivered_customer_ts,
        order_estimated_delivery_ts,
        total_payment_value,
        payment_order_id,
        favorite_payment_type,
        used_voucher
    from delivered_orders
    order by customer_unique_id, order_purchase_ts, order_id
),

eligible_first_order as (
    select *
    from first_order
    where order_approved_ts is not null
        and order_delivered_carrier_ts is not null
        and order_delivered_customer_ts is not null
        and order_estimated_delivery_ts is not null
),

first_order_items as (
    select
        fo.order_id,
        count(*) as item_count,
        sum(i.freight_value) as freight_value,
        sum(i.item_price + i.freight_value) as item_spend
    from eligible_first_order fo
    inner join {{ ref('stg_order_items') }} i
        on fo.order_id = i.order_id
    group by fo.order_id
),

score_avg as (
    select avg(review_score) as avg_review_score
    from {{ ref('stg_order_reviews') }}
),

first_order_review as (
    select
        fo.order_id,
        coalesce(
            bool_or(r.review_score < (select avg_review_score from score_avg)),
            false
        ) as review_below_average
    from eligible_first_order fo
    left join {{ ref('stg_order_reviews') }} r
        on fo.order_id = r.order_id
    group by fo.order_id
),

order_durations as (
    select
        fo.customer_unique_id,
        fo.customer_state,
        fo.order_id,
        fo.order_purchase_ts,
        fo.total_payment_value,
        fo.payment_order_id,
        fo.favorite_payment_type,
        fo.used_voucher,
        extract(epoch from (fo.order_delivered_customer_ts - fo.order_purchase_ts))
            / 86400.0 as delivery_days,
        extract(epoch from (fo.order_approved_ts - fo.order_purchase_ts))
            / 86400.0 as approval_days,
        extract(epoch from (fo.order_delivered_carrier_ts - fo.order_purchase_ts))
            / 86400.0 as carrier_days,
        case
            when fo.order_delivered_customer_ts::date
                <= fo.order_estimated_delivery_ts::date
            then 0
            else fo.order_delivered_customer_ts::date
                - fo.order_estimated_delivery_ts::date
        end as after_estimated_delivery
    from eligible_first_order fo
)

select
    od.customer_unique_id,
    od.customer_state,
    lt.total_orders,
    case
        when od.payment_order_id is null
        then coalesce(foi.item_spend, 0)
        else od.total_payment_value
    end as total_spent,
    case
        when od.payment_order_id is null
        then coalesce(foi.item_spend, 0)
        else od.total_payment_value
    end as average_order_value,
    (ao.as_of_date - od.order_purchase_ts::date) as days_since_last_purchase,
    od.favorite_payment_type,
    coalesce(foi.item_count, 0) as item_count,
    coalesce(foi.freight_value, 0) as freight_value,
    od.used_voucher,
    od.delivery_days,
    od.approval_days,
    od.carrier_days,
    od.after_estimated_delivery,
    forv.review_below_average
from order_durations od
cross join as_of ao
inner join lifetime lt
    on od.customer_unique_id = lt.customer_unique_id
inner join first_order_review forv
    on od.order_id = forv.order_id
left join first_order_items foi
    on od.order_id = foi.order_id
