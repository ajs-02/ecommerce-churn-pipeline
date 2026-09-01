SELECT *
FROM {{ source('olist', 'geolocation') }}
