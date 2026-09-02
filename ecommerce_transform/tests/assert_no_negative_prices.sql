-- Fails (returns rows) if any order item has a negative price or freight value.

select *
from {{ ref('stg_order_items') }}
where item_price < 0
   or freight_value < 0
