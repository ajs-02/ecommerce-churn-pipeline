select cf.*
from {{ ref('customer_features') }} cf
where item_count<=0 or item_count<>trunc(item_count)
    or repeat_within_180_days not in (0,1)
    or exists (
        select 1 from (values (total_spent),(freight_value),(delivery_seconds),
            (approval_seconds),(carrier_seconds),(after_estimated_delivery_seconds),
            (seconds_since_first_purchase::numeric),(item_count::numeric)) amounts(value)
        where value<0 or value::text in ('NaN','Infinity','-Infinity') or value is null
    )
