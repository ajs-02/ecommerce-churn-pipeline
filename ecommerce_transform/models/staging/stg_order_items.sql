-- One row per line item within an order.

with source as (
    select * from {{ source('olist', 'order_items') }}
)

select
    order_id,
    order_item_id,
    product_id,
    seller_id,
    cast(shipping_limit_date as timestamp) as shipping_limit_ts,
    cast(price as numeric(10, 2)) as item_price,
    cast(freight_value as numeric(10, 2)) as freight_value
from source
