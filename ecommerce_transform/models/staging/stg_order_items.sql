-- One row per line item within an order.

with source as (
    select order_id, order_item_id, product_id, seller_id, shipping_limit_date, price, freight_value from {{ source('olist', 'order_items') }}
)

select
    cast(order_id as text) as order_id,
    cast(order_item_id as integer) as order_item_id,
    cast(product_id as text) as product_id,
    cast(seller_id as text) as seller_id,
    cast(shipping_limit_date as timestamp) as shipping_limit_ts,
    cast(price as numeric) as item_price,
    cast(freight_value as numeric) as freight_value
from source
