-- A delivered order should have a delivered-customer timestamp.
-- A few real Olist rows violate this (~8 of 99,441). Warn rather than fail.

{{ config(severity='warn') }}

select *
from {{ ref('stg_orders') }}
where order_status = 'delivered'
  and order_delivered_customer_ts is null
