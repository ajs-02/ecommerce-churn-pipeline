-- Split payments aggregate at order grain; favorite ranks total value per type.
with source as (
    select
        cast(order_id as text) as order_id,
        cast(payment_type as text) as payment_type,
        cast(payment_value as numeric) as payment_value,
        cast(payment_installments as integer) as payment_installments
    from {{ source('olist', 'order_payments') }}
),
aggregated as (
    select
        order_id,
        case when count(payment_value) = count(*) then sum(payment_value) end as total_payment_value,
        max(payment_installments) as max_installments,
        count(*) as payment_row_count,
        bool_or(coalesce(payment_type = 'voucher', false)) as used_voucher
    from source
    group by order_id
),
type_totals as (
    select order_id, payment_type,
        case when count(payment_value) = count(*) then sum(payment_value) end as type_value
    from source
    group by order_id, payment_type
),
ranked as (
    select order_id, payment_type,
        row_number() over (
            partition by order_id
            order by type_value desc nulls last, payment_type collate "C" asc nulls last
        ) as rn
    from type_totals
)
select
    a.order_id,
    a.total_payment_value,
    a.max_installments,
    a.payment_row_count,
    a.used_voucher,
    case when a.total_payment_value is not null then r.payment_type end as favorite_payment_type
from aggregated a
join ranked r on a.order_id = r.order_id and r.rn = 1
