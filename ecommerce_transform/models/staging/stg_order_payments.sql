-- Aggregate to one row per order so joins do not fan out spend.
-- Favorite type is the payment_type with the largest share of that order's value.

with source as (
    select * from {{ source('olist', 'order_payments') }}
),

aggregated as (
    select
        order_id,
        sum(payment_value) as total_payment_value,
        max(payment_installments) as max_installments,
        count(*) as payment_row_count,
        bool_or(payment_type = 'voucher') as used_voucher
    from source
    group by order_id
),

ranked as (
    select
        order_id,
        payment_type,
        row_number() over (
            partition by order_id
            order by payment_value desc, payment_sequential
        ) as rn
    from source
)

select
    a.order_id,
    a.total_payment_value,
    a.max_installments,
    a.payment_row_count,
    a.used_voucher,
    r.payment_type as favorite_payment_type
from aggregated a
inner join ranked r
    on a.order_id = r.order_id
    and r.rn = 1
