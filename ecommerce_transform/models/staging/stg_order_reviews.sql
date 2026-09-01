SELECT *
FROM {{ source('olist', 'order_reviews') }}
