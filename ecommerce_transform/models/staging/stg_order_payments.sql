SELECT *
FROM {{ source('olist', 'order_payments') }}
