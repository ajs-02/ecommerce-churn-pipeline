{{ config(materialized='table') }}

-- Grain: one row per customer_unique_id.
-- Predictors come from the first delivered order only (completed purchases —
-- timing features need delivery timestamps). This is intentional, not a silent
-- extra-spec filter.
-- total_orders is the lifetime delivered count and is label-only; do not use it
-- as a predictor.
-- Duration means and the review-score average are extract-wide scalars on the
-- first-order frame. A later train/test split will see a global mart mean, not
-- a train-fold-only mean.
-- Do not join products or translation; do not emit category or photo columns.

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
        favorite_payment_type,
        used_voucher
    from delivered_orders
    order by customer_unique_id, order_purchase_ts, order_id
),

first_order_items as (
    select
        fo.order_id,
        count(*) as item_count,
        sum(i.freight_value) as freight_value
    from first_order fo
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
    from first_order fo
    left join {{ ref('stg_order_reviews') }} r
        on fo.order_id = r.order_id
    group by fo.order_id
),

raw_durations as (
    select
        fo.customer_unique_id,
        fo.customer_state,
        fo.order_id,
        fo.order_purchase_ts,
        fo.total_payment_value,
        fo.favorite_payment_type,
        fo.used_voucher,
        extract(epoch from (fo.order_delivered_customer_ts - fo.order_purchase_ts))
            / 86400.0 as delivery_days_raw,
        extract(epoch from (fo.order_approved_ts - fo.order_purchase_ts))
            / 86400.0 as approval_days_raw,
        extract(epoch from (fo.order_delivered_carrier_ts - fo.order_purchase_ts))
            / 86400.0 as carrier_days_raw,
        case
            when fo.order_delivered_customer_ts is null
                or fo.order_estimated_delivery_ts is null
            then null
            when fo.order_delivered_customer_ts::date
                <= fo.order_estimated_delivery_ts::date
            then 0
            else fo.order_delivered_customer_ts::date
                - fo.order_estimated_delivery_ts::date
        end as after_estimated_delivery_raw
    from first_order fo
),

duration_means as (
    select
        avg(delivery_days_raw) as mean_delivery_days,
        avg(approval_days_raw) as mean_approval_days,
        avg(carrier_days_raw) as mean_carrier_days
    from raw_durations
)

select
    rd.customer_unique_id,
    rd.customer_state,
    lt.total_orders,
    rd.total_payment_value as total_spent,
    rd.total_payment_value as average_order_value,
    (ao.as_of_date - rd.order_purchase_ts::date) as days_since_last_purchase,
    rd.favorite_payment_type,
    coalesce(foi.item_count, 0) as item_count,
    coalesce(foi.freight_value, 0) as freight_value,
    rd.used_voucher,
    coalesce(rd.delivery_days_raw, dm.mean_delivery_days) as delivery_days,
    (rd.delivery_days_raw is null) as delivery_days_missing,
    coalesce(rd.approval_days_raw, dm.mean_approval_days) as approval_days,
    (rd.approval_days_raw is null) as approval_days_missing,
    coalesce(rd.carrier_days_raw, dm.mean_carrier_days) as carrier_days,
    (rd.carrier_days_raw is null) as carrier_days_missing,
    coalesce(rd.after_estimated_delivery_raw, 0) as after_estimated_delivery,
    (rd.after_estimated_delivery_raw is null) as after_estimated_delivery_missing,
    forv.review_below_average
from raw_durations rd
cross join as_of ao
cross join duration_means dm
inner join lifetime lt
    on rd.customer_unique_id = lt.customer_unique_id
inner join first_order_review forv
    on rd.order_id = forv.order_id
left join first_order_items foi
    on rd.order_id = foi.order_id
