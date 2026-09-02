-- One row per product, with English category when a translation exists.

with products as (
    select * from {{ source('olist', 'products') }}
),

translation as (
    select * from {{ source('olist', 'product_category_name_translation') }}
)

select
    p.product_id,
    p.product_category_name,
    coalesce(
        t.product_category_name_english,
        p.product_category_name,
        'unknown'
    ) as category_english,
    p.product_weight_g,
    p.product_length_cm,
    p.product_height_cm,
    p.product_width_cm
from products p
left join translation t
    on p.product_category_name = t.product_category_name
