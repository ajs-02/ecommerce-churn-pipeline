# Implementation gap review

<canvas_reference id="canvas:df1118076b374e3432b19ef4c88de765744344cd">Olist Implementation Gap</canvas_reference>

Open that canvas beside the chat. It is the review surface for this snapshot. This file is the copy future agents can read from the repo when the canvas is not mounted. The canvas source on this machine is `C:\Users\prince\.cursor\projects\d-Projects-ecommerce-churn-pipeline-ecommerce-churn-pipeline\canvases\olist-implementation-gap.canvas.tsx`.

This note is not the feature contract. `docs/project_spec.md` and `.cursor/rules/project.mdc` govern `customer_features`. The exclusion is now that contract. A customer whose first delivered order lacks an approval, carrier, customer-delivery, or estimated-delivery timestamp is absent from the mart, and the four `*_missing` columns are not emitted. The census SQL below names those columns and describes the table before that change. Do not put the mean fill back.

Reviewed commit `ea5de74`. Counts below were queried from `public.customer_features` on 8 Oct 2026. Re-run the census before treating a number as current.

## How to re-run

Use the project virtualenv. Load `.env` inside the process. Do not print `POSTGRES_*` values.

```sql
SELECT COUNT(*) AS mart_rows,
       COUNT(*) FILTER (WHERE total_orders > 1) AS repeat_rows,
       COUNT(*) FILTER (WHERE total_orders = 1) AS onetime_rows,
       COUNT(*) FILTER (WHERE total_orders < 1) AS zero_order_rows,
       COUNT(*) FILTER (WHERE favorite_payment_type IS NULL) AS null_payment_type,
       COUNT(*) FILTER (WHERE delivery_days_missing) AS delivery_days_missing,
       COUNT(*) FILTER (WHERE approval_days_missing) AS approval_days_missing,
       COUNT(*) FILTER (WHERE carrier_days_missing) AS carrier_days_missing,
       COUNT(*) FILTER (WHERE after_estimated_delivery_missing) AS after_estimated_delivery_missing
FROM customer_features;

SELECT delivery_days_missing::int,
       approval_days_missing::int,
       carrier_days_missing::int,
       after_estimated_delivery_missing::int,
       COUNT(*) AS n,
       COUNT(*) FILTER (WHERE total_orders > 1) AS n_repeat
FROM customer_features
GROUP BY 1, 2, 3, 4
ORDER BY n DESC;
```

Then compare the tree with the spec sections named below. Read `ecommerce_transform/models/marts/customer_features.sql` before accepting the imputation judgment.

## Snapshot counts

| Population | Rows | Repeat buyers | Repeat rate |
| --- | --- | --- | --- |
| Mart as queried | 93,358 | 2,801 | 3.0002% |
| Drop all 23 flagged rows | 93,335 | 2,800 | 2.9999% |
| Drop only the 8 delivery-null rows | 93,350 | 2,801 | 3.0005% |

`total_orders < 1` was 0. Customers with no delivered order are already absent. `favorite_payment_type` was null on 1 row. The query did not confirm that row is `830d5b7aaa3b6f1e9ad63703bec97d23`.

Flag patterns, mutually exclusive:

| Pattern | Rows | Repeat buyers |
| --- | --- | --- |
| No missing flag | 93,335 | 2,800 |
| Approval only | 14 | 1 |
| Delivery and late days | 7 | 0 |
| Carrier only | 1 | 0 |
| Delivery, carrier, and late days | 1 | 0 |

`delivery_days_missing` is 8, all one-time. `after_estimated_delivery_missing` is those same 8. `approval_days_missing` is 14 and does not overlap the delivery-null rows. `carrier_days_missing` is 2.

## What is built

Present at `ea5de74`:

- Postgres dbt project in `ecommerce_transform/`. Staging views, `customer_features` table, YAML tests, and the three singular tests.
- `scripts/upload_data.py`, `scripts/validate_upload.py`, `scripts/test_connection.py`.
- `Power BI/Olist Churn Analysis.pbix`.

Specified and not in the tree:

- A download script that writes the Kaggle CSVs into `data/`.
- `scripts/train_model.py`.
- `.github/workflows/train_model.yml`.
- `tests/test_pipeline.py`.
- `notebooks/01_eda_and_profiling.ipynb`.
- `scripts/generate_data_profile.py`.
- A `customer_repeat_predictions` upsert table.

`requirements.txt` already lists `pyarrow`, `xgboost`, `imbalanced-learn`, `ydata-profiling`, and `pytest` for code that is not in the tree. The venv used for the census did not have `pyarrow` importable.

## How the mart behaves

`customer_features.sql` keeps one row per `customer_unique_id` with at least one delivered order. `total_orders` is the lifetime delivered count and is the label source. Other columns come from the earliest delivered order (`distinct on`, ordered by purchase timestamp, then `order_id`). `average_order_value` is the same expression as first-order `total_spent`.

Null durations on that first order are mean-filled. SQL `avg` skips nulls, so the flagged rows do not move the mean. Late days use 0 for an on-time delivery and also for a null delivery or estimate timestamp. `after_estimated_delivery_missing` is the only separator. Recency uses `var('as_of_date')` or `max(order_purchase_ts)::date`, not `current_date`. `dbt_project.yml` sets `as_of_date` to null.

`score_avg` averages `review_score` over all of `stg_order_reviews`. The file header says that average is on the first-order frame. The query matches the spec. The comment does not.

The spend fallback runs when `favorite_payment_type` is null, not when the payment join is missing. With one null in the live table, those predicates currently describe the same row unless a real payment row has a null type. That split was not queried.

## Judgment on imputation

Do not treat the 23 flags as one junk population.

Drop the 8 first delivered orders whose customer delivery timestamp is null, and do not impute them. Status says delivered and the timestamp is missing. Mean-filling delivery days and storing late days as 0 manufactures an on-time order. The warn test in `assert_delivered_orders_have_delivery_date.sql` already names this quirk at order grain.

The 14 approval-null rows have a delivery time. They are a separate hole. Dropping them is a judgment, not a measured requirement. A flag that is true 14 times will not support a stable split. The 2 carrier-null rows are the same kind of rare column.

The spec requires the mean fill, the 0 fill, and the flags as model features. Deleting the rows without editing `docs/project_spec.md` and `.cursor/rules/project.mdc` will fight the next training script.

Git does not say “impute instead of drop.” Commit `ea5de74` says not to leave nulls for Python to fill, and to keep the flags as features. `scripts/train_model.py` is absent. There were no pull requests and no GitHub issues on `ajs-02/ecommerce-churn-pipeline` when this was checked.

## Defects to re-check in source

- `scripts/upload_data.py` prints per-file errors and still exits 0. The first chunk replaces the table. A later chunk failure leaves a partial table. The nine CSV counts matched the warehouse on 8 Oct 2026, so that load was complete. The bug is the failed-run path.
- `scripts/test_connection.py` exits 0 on failure and always prints a Heroku success line.
- Both CSV reads omit `engine="pyarrow"` and `dtype_backend="pyarrow"`.
- `used_voucher` `accepted_values` lists bare `true` and `false` without `quote: false`. `dbt test` was not run. dbt 1.12.3 was installed, so the `arguments:` wrapper matches that dbt. The boolean-versus-text risk is unread test output.
- README says Power BI reads scored `customer_features`, including a probability. The spec says Power BI reads an upsert predictions table. The mart has neither a probability nor `customer_repeat_predictions`. A read of the pbix report JSON found entity `customer_features_202609072318` and no probability field. Re-open the pbix before relying on that binding.

## Files a clone does not have

`.gitignore` ignores `docs/*` except `docs/project_spec.md` and this file. `docs/erd.md`, `docs/cursor-rules.mdc`, and `docs/ref/` can exist on a working copy and still be untracked. The ignored rule copy is staler than `.cursor/rules/project.mdc`. Do not treat `docs/ref/` as part of this pipeline. It still contains the reference DuckDB, Streamlit, and star-schema project.
