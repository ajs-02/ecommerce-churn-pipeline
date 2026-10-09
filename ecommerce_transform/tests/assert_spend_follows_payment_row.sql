-- Fail when a kept customer with a payment row has total_spent different from
-- that payment total, or when the known no-payment customer is missing, has a
-- payment type, or has total_spent of 0.
-- First-order grain matches the mart: earliest purchase_ts, then order_id.

with first_delivered as (
    select distinct on (c.customer_unique_id)
        c.customer_unique_id,
        o.order_id,
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
    select customer_unique_id, order_id
    from first_delivered
    where order_approved_ts is not null
        and order_delivered_carrier_ts is not null
        and order_delivered_customer_ts is not null
        and order_estimated_delivery_ts is not null
),

payment_mismatch as (
    select cf.customer_unique_id
    from {{ ref('customer_features') }} cf
    inner join eligible e
        on cf.customer_unique_id = e.customer_unique_id
    inner join {{ ref('stg_order_payments') }} p
        on e.order_id = p.order_id
    where abs(cf.total_spent - p.total_payment_value) > 0.01
),

known_gap as (
    select '830d5b7aaa3b6f1e9ad63703bec97d23'::text as customer_unique_id
    where not exists (
        select 1
        from {{ ref('customer_features') }}
        where customer_unique_id = '830d5b7aaa3b6f1e9ad63703bec97d23'
            and favorite_payment_type is null
            and total_spent <> 0
    )
)

select customer_unique_id from payment_mismatch
union all
select customer_unique_id from known_gap
