-- Fail when the mart keeps a customer whose first delivered order lacks an
-- approval, carrier, customer-delivery, or estimated-delivery timestamp, when
-- an eligible customer is missing, or when a duration column is null.
-- First-order grain matches the mart: earliest purchase_ts, then order_id.
-- Lifetime delivered orders are not the exclusion grain.

with first_delivered as (
    select distinct on (c.customer_unique_id)
        c.customer_unique_id,
        o.order_approved_ts,
        o.order_delivered_carrier_ts,
        o.order_delivered_customer_ts,
        o.order_estimated_delivery_ts
    from {{ ref('stg_customers') }} c
    inner join {{ ref('stg_orders') }} o
        on c.customer_id = o.customer_id
    where o.order_status = 'delivered'
    order by c.customer_unique_id, o.order_purchase_ts, o.order_id
),

eligible as (
    select customer_unique_id
    from first_delivered
    where order_approved_ts is not null
        and order_delivered_carrier_ts is not null
        and order_delivered_customer_ts is not null
        and order_estimated_delivery_ts is not null
),

mart as (
    select
        customer_unique_id,
        delivery_days,
        approval_days,
        carrier_days,
        after_estimated_delivery
    from {{ ref('customer_features') }}
)

select
    coalesce(m.customer_unique_id, e.customer_unique_id) as customer_unique_id
from mart m
full outer join eligible e
    on m.customer_unique_id = e.customer_unique_id
where e.customer_unique_id is null
    or m.customer_unique_id is null
    or m.delivery_days is null
    or m.approval_days is null
    or m.carrier_days is null
    or m.after_estimated_delivery is null
