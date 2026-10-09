-- The shared candidate census determines eligibility; no duplicate exclusion policy.
select coalesce(d.customer_unique_id,m.customer_unique_id) as customer_unique_id
from {{ ref('customer_feature_diagnostics') }} d
full join {{ ref('customer_features') }} m using(customer_unique_id)
where (d.is_eligible and m.customer_unique_id is null)
    or (m.customer_unique_id is not null and not coalesce(d.is_eligible,false))
