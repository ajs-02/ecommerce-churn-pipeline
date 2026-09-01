SELECT *
FROM {{ source('olist', 'order_items') }}
