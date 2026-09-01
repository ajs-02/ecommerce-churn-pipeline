SELECT *
FROM {{ source('olist', 'customers') }}
