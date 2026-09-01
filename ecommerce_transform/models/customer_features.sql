{{ config(materialized='table') }}

SELECT
    c.customer_unique_id,
    MAX(c.customer_state) AS customer_state,
    COUNT(DISTINCT o.order_id) AS total_orders,
    SUM(p.payment_value) AS total_spent,
    MAX(o.order_purchase_timestamp) AS last_purchase_date
FROM {{ ref('stg_customers') }} c
JOIN {{ ref('stg_orders') }} o
    ON c.customer_id = o.customer_id
JOIN {{ ref('stg_order_payments') }} p
    ON o.order_id = p.order_id
WHERE o.order_status = 'delivered'
GROUP BY 1