{{ config(materialized='table') }}

-- Grain: one row per customer_unique_id, delivered orders only.

with customers as (
    select * from {{ ref('stg_customers') }}
),

orders as (
    select * from {{ ref('stg_orders') }}
    where order_status = 'delivered'
),

payments as (
    select * from {{ ref('stg_order_payments') }}
),

customer_orders as (
    select
        c.customer_unique_id,
        c.customer_state,
        o.order_id,
        o.order_purchase_ts,
        p.total_payment_value,
        p.favorite_payment_type
    from customers c
    inner join orders o
        on c.customer_id = o.customer_id
    inner join payments p
        on o.order_id = p.order_id
),

customer_payment_pref as (
    select distinct on (customer_unique_id)
        customer_unique_id,
        favorite_payment_type
    from (
        select
            customer_unique_id,
            favorite_payment_type,
            sum(total_payment_value) as type_spend
        from customer_orders
        group by customer_unique_id, favorite_payment_type
    ) type_totals
    order by customer_unique_id, type_spend desc
)

select
    co.customer_unique_id,
    mode() within group (order by co.customer_state) as customer_state,
    count(distinct co.order_id) as total_orders,
    sum(co.total_payment_value) as total_spent,
    sum(co.total_payment_value)
        / nullif(count(distinct co.order_id), 0) as average_order_value,
    (current_date - max(co.order_purchase_ts)::date) as days_since_last_purchase,
    cpp.favorite_payment_type
from customer_orders co
inner join customer_payment_pref cpp
    on co.customer_unique_id = cpp.customer_unique_id
group by co.customer_unique_id, cpp.favorite_payment_type
