{{ config(severity='warn') }}
select customer_unique_id,total_spent,item_spend
from {{ ref('customer_feature_diagnostics') }}
where is_eligible and abs(total_spent-item_spend)>0.01
