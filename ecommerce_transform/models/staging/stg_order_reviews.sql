-- One row per review_id. Do not collapse to order grain.
-- The extract repeats some review_ids on different order_ids; those extras
-- are source errors. Keep the first occurrence (earliest creation, then
-- order_id) so review_id is unique.

with source as (
    select * from {{ source('olist', 'order_reviews') }}
),

typed as (
    select
        review_id,
        order_id,
        cast(review_score as integer) as review_score,
        review_comment_title,
        review_comment_message,
        cast(review_creation_date as timestamp) as review_creation_ts,
        cast(review_answer_timestamp as timestamp) as review_answer_ts
    from source
)

select distinct on (review_id)
    review_id,
    order_id,
    review_score,
    review_comment_title,
    review_comment_message,
    review_creation_ts,
    review_answer_ts
from typed
order by review_id, review_creation_ts, order_id
