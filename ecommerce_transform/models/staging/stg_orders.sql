SELECT *
FROM {{ source('olist', 'orders') }}
