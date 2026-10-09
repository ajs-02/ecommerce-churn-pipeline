{{ config(tags=['staging']) }}
-- Test every split payment, including negatives hidden by positive order totals.
select order_id, payment_sequential, payment_value
from {{ source('olist', 'order_payments') }}
where cast(payment_value as numeric) < 0
   or cast(cast(payment_value as numeric) as text) in ('NaN', 'Infinity', '-Infinity')
