-- Warns (does not fail) when customer_features.total_spent does not match the
-- first delivered order's line-item total (sum of item_price + freight_value).
-- First-order grain matches the mart: earliest purchase_ts, then order_id.
-- Severity is warn so we can count payment-vs-item mismatches before deciding
-- whether to keep this test.

{{ config(severity='warn') }}

with first_order as (
    select distinct on (c.customer_unique_id)
        c.customer_unique_id,
        o.order_id
    from {{ ref('stg_customers') }} c
    inner join {{ ref('stg_orders') }} o
        on c.customer_id = o.customer_id
    where o.order_status = 'delivered'
    order by c.customer_unique_id, o.order_purchase_ts, o.order_id
),

item_spend as (
    select
        fo.customer_unique_id,
        coalesce(sum(i.item_price + i.freight_value), 0) as item_total
    from first_order fo
    left join {{ ref('stg_order_items') }} i
        on fo.order_id = i.order_id
    group by fo.customer_unique_id
)

select
    cf.customer_unique_id,
    cf.total_spent,
    s.item_total as item_price_plus_freight
from {{ ref('customer_features') }} cf
inner join item_spend s
    on cf.customer_unique_id = s.customer_unique_id
where abs(cf.total_spent - s.item_total) > 0.01
