# Olist repeat-order exploration

This project studies associations between first-delivered-order features and repeat ordering within a defined observation window.

## Language

**Customer**: A person identified across order-specific customer records by `customer_unique_id`.

**Anchor order**: The customer's first delivered order, selected by earliest purchase timestamp and then order ID. Its purchase timestamp starts the target window.

**Repeat activity**: A distinct order other than the anchor, of any recorded status, purchased within the inclusive interval from the anchor purchase timestamp through 180 days afterward. Orders purchased before the anchor do not count.

**Complete follow-up**: The extract's observation end reaches or exceeds the customer's target-window end.

**Early positive**: A customer with observed repeat activity whose 180-day follow-up is incomplete.

**Uncertain label**: No repeat activity has been observed and the full target window has not been observed. This is not a negative outcome.

**Recoverable value**: A value deterministically established from existing records of the anchor order. Statistical estimates and later-order substitutions are not recoveries.

**Eligible feature population**: Customers whose anchor-order predictors satisfy the agreed completeness and validity rules.

**Labeled cohort**: Eligible customers with an observed positive or a complete-follow-up negative, including early positives.

**Uncertain cohort**: Eligible customers with an uncertain label, retained for scoring and descriptive analysis.

**Model score**: The uncalibrated positive-class probability output of a fitted classifier. It is not an established real-world repeat probability.

**Selected candidate**: The frozen model and threshold the user chooses after reviewing development results.

**Accepted task**: Work whose outputs, test cases, and outcomes the user has reviewed and explicitly accepted.
