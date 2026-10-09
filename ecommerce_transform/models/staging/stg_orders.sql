-- One row per order with typed lifecycle timestamps. No joins or business logic.

with source as (
    select order_id, customer_id, order_status, order_purchase_timestamp, order_approved_at, order_delivered_carrier_date, order_delivered_customer_date, order_estimated_delivery_date from {{ source('olist', 'orders') }}
)

select
    cast(order_id as text) as order_id,
    cast(customer_id as text) as customer_id,
    cast(order_status as text) as order_status,
    cast(order_purchase_timestamp as timestamp) as order_purchase_ts,
    cast(order_approved_at as timestamp) as order_approved_ts,
    cast(order_delivered_carrier_date as timestamp) as order_delivered_carrier_ts,
    cast(order_delivered_customer_date as timestamp) as order_delivered_customer_ts,
    cast(order_estimated_delivery_date as timestamp) as order_estimated_delivery_ts
from source
