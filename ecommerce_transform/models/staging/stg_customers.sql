-- One row per order-scoped customer_id. Light cleaning only; grain stays as in raw.

with source as (
    select * from {{ source('olist', 'customers') }}
)

select
    customer_id,
    customer_unique_id,
    customer_zip_code_prefix,
    customer_city,
    upper(customer_state) as customer_state
from source
