{{ config(materialized='table') }}
-- Exactly one eligible row per customer. Diagnostics owns the anchor and census.
select customer_unique_id,customer_state,first_delivered_order_id,
    first_delivered_purchase_ts,target_window_end_ts,observation_end_ts,
    observation_end_provenance,as_of_date,has_complete_followup,repeat_within_180_days,
    total_orders,total_spent,seconds_since_first_purchase,favorite_payment_type,
    item_count,freight_value,used_voucher,delivery_seconds,approval_seconds,
    carrier_seconds,after_estimated_delivery_seconds,review_below_average,has_first_order_review
from {{ ref('customer_feature_diagnostics') }} where is_eligible
