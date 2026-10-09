-- Payment rows remain authoritative even when their total is unknown.
select d.customer_unique_id
from {{ ref('customer_feature_diagnostics') }} d
left join {{ ref('stg_order_payments') }} p on p.order_id=d.first_delivered_order_id
where d.total_spent is distinct from
    case when p.order_id is null then d.item_spend else p.total_payment_value end
    or d.spend_recovered_from_items is distinct from (p.order_id is null and d.item_spend is not null)
