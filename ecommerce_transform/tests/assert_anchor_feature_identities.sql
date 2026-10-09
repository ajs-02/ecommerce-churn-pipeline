-- Independently recompute identities from staged anchor records.
with first_order as (
    select distinct on (c.customer_unique_id) c.customer_unique_id,c.customer_state,o.*
    from {{ ref('stg_orders') }} o join {{ ref('stg_customers') }} c using(customer_id)
    where o.order_status='delivered'
    order by c.customer_unique_id,o.order_purchase_ts,o.order_id collate "C"
), item_sums as (
    select order_id,count(*) as item_count,
        case when count(freight_value)=count(*) then sum(freight_value) end as freight_value,
        case when count(item_price)=count(*) and count(freight_value)=count(*) then sum(item_price+freight_value) end as item_spend
    from {{ ref('stg_order_items') }} group by order_id
), reviews as (
    select order_id,count(*)>0 as present,
        coalesce(bool_or(review_score<(select avg(review_score) from {{ ref('stg_order_reviews') }})),false) as below
    from {{ ref('stg_order_reviews') }} group by order_id
)
select d.customer_unique_id
from {{ ref('customer_feature_diagnostics') }} d
join first_order a using(customer_unique_id)
left join item_sums i on i.order_id=a.order_id
left join {{ ref('stg_order_payments') }} p on p.order_id=a.order_id
left join reviews r on r.order_id=a.order_id
where d.first_delivered_order_id is distinct from a.order_id
    or d.customer_state is distinct from a.customer_state
    or d.item_count is distinct from i.item_count
    or d.freight_value is distinct from i.freight_value
    or d.item_spend is distinct from i.item_spend
    or d.total_spent is distinct from case when p.order_id is null then i.item_spend else p.total_payment_value end
    or d.favorite_payment_type is distinct from p.favorite_payment_type
    or d.used_voucher is distinct from coalesce(p.used_voucher,false)
    or d.has_first_order_review is distinct from coalesce(r.present,false)
    or d.review_below_average is distinct from coalesce(r.below,false)
    or d.first_delivered_purchase_ts is distinct from a.order_purchase_ts
    or d.approval_seconds is distinct from extract(epoch from a.order_approved_ts-a.order_purchase_ts)
    or d.carrier_seconds is distinct from extract(epoch from a.order_delivered_carrier_ts-a.order_purchase_ts)
    or d.delivery_seconds is distinct from extract(epoch from a.order_delivered_customer_ts-a.order_purchase_ts)
    or d.seconds_since_first_purchase is distinct from (d.as_of_date-a.order_purchase_ts::date)::bigint*86400
    or d.after_estimated_delivery_seconds is distinct from case when a.order_delivered_customer_ts is not null and a.order_estimated_delivery_ts is not null
        then greatest(a.order_delivered_customer_ts::date-a.order_estimated_delivery_ts::date,0)::bigint*86400 end

union all
select m.customer_unique_id
from {{ ref('customer_features') }} m
join {{ ref('customer_feature_diagnostics') }} d using(customer_unique_id)
where exists (
    select m.customer_state,m.first_delivered_order_id,m.first_delivered_purchase_ts,
        m.target_window_end_ts,m.observation_end_ts,m.has_complete_followup,m.repeat_within_180_days,
        m.total_orders,m.total_spent,m.seconds_since_first_purchase,m.favorite_payment_type,
        m.item_count,m.freight_value,m.used_voucher,m.delivery_seconds,m.approval_seconds,
        m.carrier_seconds,m.after_estimated_delivery_seconds,m.review_below_average,m.has_first_order_review
    except
    select d.customer_state,d.first_delivered_order_id,d.first_delivered_purchase_ts,
        d.target_window_end_ts,d.observation_end_ts,d.has_complete_followup,d.repeat_within_180_days,
        d.total_orders,d.total_spent,d.seconds_since_first_purchase,d.favorite_payment_type,
        d.item_count,d.freight_value,d.used_voucher,d.delivery_seconds,d.approval_seconds,
        d.carrier_seconds,d.after_estimated_delivery_seconds,d.review_below_average,d.has_first_order_review
)
