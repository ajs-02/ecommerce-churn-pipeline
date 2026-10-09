-- One row per order-scoped customer_id. Light cleaning only; grain stays as in raw.

with source as (
    select customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state from {{ source('olist', 'customers') }}
)

select
    cast(customer_id as text) as customer_id,
    cast(customer_unique_id as text) as customer_unique_id,
    cast(customer_zip_code_prefix as integer) as customer_zip_code_prefix,
    cast(customer_city as text) as customer_city,
    upper(customer_state) as customer_state
from source
