-- Product attributes support relationship checks, not model predictors.
select
    cast(p.product_id as text) as product_id,
    cast(p.product_category_name as text) as product_category_name,
    cast(coalesce(t.product_category_name_english, p.product_category_name, 'unknown') as text) as category_english,
    cast(p.product_weight_g as numeric) as product_weight_g,
    cast(p.product_length_cm as numeric) as product_length_cm,
    cast(p.product_height_cm as numeric) as product_height_cm,
    cast(p.product_width_cm as numeric) as product_width_cm
from {{ source('olist', 'products') }} p
left join {{ source('olist', 'product_category_name_translation') }} t
    on p.product_category_name = t.product_category_name
