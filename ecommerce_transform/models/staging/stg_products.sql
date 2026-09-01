SELECT *
FROM {{ source('olist', 'products') }}
