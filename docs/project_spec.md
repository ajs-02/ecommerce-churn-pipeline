# Project Specification: Olist Repeat Buyer Propensity Pipeline

## 1. Business Objectives

- **Goal:** Predict Repeat Purchase Probability for each customer on an e-commerce platform (who is likely to buy more than once).
- **Use Case:** Enable the marketing team to allocate acquisition and retention budgets toward one-time buyers with a high propensity to become repeat customers, especially high-spend customers in that group.
- **Deliverable:** An executive dashboard (Power BI/Tableau) showing Repeat Purchase Probability and segmenting customers into actionable cohorts (one-time vs likely repeat).

## 2. Data Objectives & Architecture

This is a repeat-buyer propensity pipeline on **PostgreSQL**. Local vs cloud is *where* the data lives, not a second warehouse. Do not add DuckDB, Streamlit, or star-schema KPI marts from `docs/ref/`.

```
Download CSVs → data/
  ├─ Local path: Pandas/PyArrow and/or load into local Postgres → dbt → train locally
  └─ Cloud path: upload to Heroku Postgres → dbt → train_model.py upserts scores
GitHub Actions (push to main + weekly cron): train against Heroku via GitHub Secrets
Power BI/Tableau reads the predictions table
```

- **Acquire:** A download script writes the Kaggle Olist CSVs into `data/` (same role as the reference ingest, adapted to this repo).
- **Local path:** Work from those CSVs with Pandas + PyArrow, and/or load them into local Postgres with `scripts/upload_data.py`, then run dbt and training locally.
- **Cloud path:** Upload CSVs to Heroku Postgres, run dbt there, train, and upsert predictions so Power BI can refresh.
- **Warehouse:** PostgreSQL only (local and/or Heroku). `profiles.yml` selects the target. DuckDB-only SQL (`arg_max`, etc.) must be rewritten for Postgres.
- **Transformation (dbt):** Reference-style staging (typed, renamed, tested) in `ecommerce_transform/`, then one ML mart: `customer_features`.
- **Machine Learning (Python):** Ingest `customer_features`, label repeat buyers (`total_orders` > 1), train XGBoost with SMOTE + `scale_pos_weight`, and **INSERT/UPDATE** predictions in Postgres. Add `xgboost` and `imbalanced-learn` to `requirements.txt`.
- **Pandas:** Every `read_csv` / `read_sql` / tabular DataFrame load uses the PyArrow engine (`engine="pyarrow"` and/or `dtype_backend="pyarrow"`). `pyarrow` must be in `requirements.txt`.
- **Secrets:** Local credentials live in `.env` (python-dotenv). CI maps GitHub Secrets onto the same `POSTGRES_*` names as `.env.example`. Never commit, log, or print secrets.
- **Automation:** Code must be modular, reproducible, and fully tested.

---

## 3. Data Dictionary, Schema & Automated Profiling

Cursor must ensure the project is fully documented and profiled to accelerate feature engineering and maintain a single source of truth for the data architecture.

### A. Schema Documentation (dbt docs)

- **Files:** Use the reference convention: `models/staging/_staging__models.yml` and `models/marts/_marts__models.yml` (do not also maintain parallel `schema.yml` files).
- **Descriptions:** Every model must include `description:` fields for both the table and its critical columns.
- **Relationships:** Foreign keys (e.g., `customer_id` connecting orders and customers) must be defined with dbt `tests:` (e.g., `relationships`). The reference YAML does not include these; this project still requires them.
- **Generation:** The pipeline must support running `dbt docs generate` to create a live data dictionary.

### B. Entity-Relationship Visualization

- Document the primary keys (PK) and foreign keys (FK) for the `customers`, `orders`, `order_items`, and `payments` tables.
- Keep a record of the cardinality (e.g., 1-to-many between orders and payments **in raw data**).
- Staging grain must match the tests: after staging, **payments are one row per `order_id`**, so `favorite_payment_type` and `total_spent` do not fan out.

### C. Automated Data Profiling

Cursor must generate a profiling script (`scripts/generate_data_profile.py`) that performs the following:

- Ingest the raw tables and the finalized `customer_features` table into Pandas using the **PyArrow** engine.
- Support the same dual path as §2: local CSVs or Postgres.
- Use the `ydata-profiling` library to export an interactive HTML report (`reports/data_profile_report.html`).
- This report will automatically calculate and document:
  - Data types (Boolean, Categorical, Numeric).
  - Number of distinct/unique values per column.
  - Percentage of missing/null values.
  - High-cardinality warnings (e.g., too many unique zip codes to one-hot encode).
  - Zero-variance warnings (columns that provide no predictive value).

---

## 4. dbt Transformation & Testing Requirements

Adopt the **scaffolding and tests** from `docs/ref/` (typed staging, YAML tests, singular tests), adapted to Postgres and this project's mart. Do **not** copy the reference star schema (`dim_*`, `fct_order_items`, monthly/category/delivery KPI marts).

### A. Staging Layer (`ecommerce_transform/models/staging/`)

Each staging model must select explicit columns, cast types, and do light cleaning — **not** `SELECT *`. Use existing file names in this repo.

Required models (typed columns, casts, YAML descriptions + unique/not_null + `relationships`; not `SELECT *`):

- `stg_customers.sql` — includes an integer cast of `customer_zip_code_prefix`.
- `stg_orders.sql`
- `stg_order_items.sql` — one row per line; integer `order_item_id`.
- `stg_order_payments.sql` — aggregate to **one row per `order_id`**, including a primary/favorite payment type (Postgres equivalent of the reference `arg_max`) and `used_voucher` (true if any payment row is `voucher`).
- `stg_products.sql` — typed product attributes; required for item → product relationship tests. The mart does not join products or translation and must not add photo or category predictors.
- `stg_order_reviews.sql` — typed review grain (`review_id`, `order_id`, integer `review_score`, comments, timestamps). Do not collapse to order in staging. Duplicate `review_id`s in the extract (same review on multiple `order_id`s) are source errors; keep the first occurrence (`distinct on (review_id)` ordered by `review_creation_ts`, then `order_id`) so `review_id` is unique.

Optional extra staging already in the repo (`stg_geolocation`, `stg_sellers`, `stg_product_category_name_translation`) may remain as unused `SELECT *`. They are not required for `customer_features`. Required staging stays typed and tested.

### B. Staging Tests (`models/staging/_staging__models.yml` plus singular tests)

YAML tests (reference coverage):

- **Uniqueness & Not Null:** `customer_id` unique + not_null; `customer_unique_id` not_null; `order_id` unique + not_null on orders; `order_id` unique + not_null on aggregated payments; `review_id` unique + not_null (after staging drops duplicate `review_id` source errors); `review_score` not_null; composite unique on items `(order_id, order_item_id)`.
- **Accepted Values:** `order_status` must be one of the full Olist set: `delivered`, `shipped`, `canceled`, `unavailable`, `invoiced`, `processing`, `created`, `approved`. `used_voucher` is true or false.
- **Referential Integrity:** `customer_id` in orders must exist in customers; `order_id` in payments, items, and reviews must exist in orders; `product_id` in items must exist in products (`relationships`).

Singular tests (ported from the reference, Postgres SQL):

- No negative item price or freight (`stg_order_items`).
- Delivered orders missing a delivery timestamp: `severity: warn` (known Olist quirk, ~8 rows).
- `customer_features.total_spent` vs first-order `sum(item_price + freight_value)` (tolerance 0.01): `severity: warn` until we decide whether to keep the test.

### C. Mart Layer (`models/marts/customer_features.sql`)

Join staging tables to create **one row per `customer_unique_id`**. Predictors come from the **first delivered order** only so they match scoring one-time buyers. `total_orders` is the lifetime count of delivered orders and is **label-only** (repeat = `total_orders` > 1). Do not use it as a predictor.

Delivered-only is intentional: timing features need delivery timestamps (completed purchases), not a silent extra-spec filter. Payments are **left joined**. If the first delivered order has no payment rows, `total_spent` and `average_order_value` use `sum(item_price + freight_value)` on that order instead of 0 (one known Olist gap: `830d5b7aaa3b6f1e9ad63703bec97d23` / `bfbd0f9bdef84302105ad712db648a6c`). `favorite_payment_type` stays null when payments are missing. Do not join products or translation. Do not emit `category_english` or `product_photos_qty`.

Recency uses a frozen `as_of_date`: dbt `var('as_of_date')` coalesced with `max(stg_orders.order_purchase_ts)::date`. `days_since_last_purchase` is as-of minus the **first** purchase date (name kept; meaning is first/only purchase). Do not use `current_date` or last-order recency.

Required column **names** stay (`customer_state`, `total_orders`, `total_spent`, `average_order_value`, `days_since_last_purchase`, `favorite_payment_type`) but **definitions** are first-order except `total_orders`:

- `customer_state` — state on the first order’s `customer_id` (not `mode()` across lifetime orders).
- `total_orders` — lifetime delivered count (label source only).
- `total_spent` — first-order payment total, or `sum(item_price + freight_value)` when that order has no payment rows. A singular test (`severity: warn`) compares it to the first-order item total (tolerance 0.01) so we can count payment-vs-item mismatches before deciding whether to keep the test.
- `average_order_value` — equals `total_spent` under the first-order definition (kept for the dashboard; do not pass both into XGBoost).
- `days_since_last_purchase` — as-of minus first purchase date.
- `favorite_payment_type` — first-order staged favorite type.

Extensions on the same first-order window:

- `item_count` — line items on the first order (no products join).
- `freight_value` — sum of item freight on the first order.
- `used_voucher` — true if any payment row on the first order has `payment_type = 'voucher'` (split tenders still count).
- `delivery_days`, `approval_days`, `carrier_days` — `extract(epoch from (end_ts - purchase_ts)) / 86400.0` when both timestamps exist. A few delivered orders have null lifecycle timestamps; impute those rows with the **mean of the observed first-order values** for that column and set a matching `*_missing` boolean true. Observed rows keep the raw value and `*_missing` false.
- `after_estimated_delivery` — compare first-order `order_delivered_customer_ts::date` to `order_estimated_delivery_ts::date`. On or before estimate → `0`. After estimate → calendar days late. If either timestamp is missing → impute `0` and set `after_estimated_delivery_missing` true.
- `review_below_average` — true if any first-order `review_score` is strictly below the extract-wide `avg(review_score)` on `stg_order_reviews`; false if the customer left no review or every score is at or above the average. Never null.

Imputation lives in the mart (mean + flag for the three durations; 0 + flag for late-days). Duration means are extract-wide averages of observed first-order raw values. The review-score threshold is extract-wide `avg(review_score)` on `stg_order_reviews` (all staged reviews, not first-order-only). A later train/test split will see those global scalars, not train-fold-only statistics. All columns except raw intermediates and `favorite_payment_type` are non-null after imputation; `favorite_payment_type` stays null when the first delivered order has no payment rows.

Document the mart in `models/marts/_marts__models.yml` with descriptions, unique/not_null on `customer_unique_id`, and not_null on recency, spend, durations, late-days, missing flags, `used_voucher`, `review_below_average`, `item_count`, and `freight_value`. Do not add `not_null` on `favorite_payment_type` (the known no-payments order is null).

---

## 5. Exploratory Data Analysis (EDA) & Feature Discovery

Cursor must generate an EDA notebook (`notebooks/01_eda_and_profiling.ipynb`) that discovers patterns and validates the repeat-buyer target (including the ~3% class imbalance) before machine learning begins.

### A. Connection & Ingestion

- **Database path:** Use `SQLAlchemy` and `python-dotenv` to connect to Postgres (local or Heroku).
- **Local CSV path:** Load from `data/` with Pandas + PyArrow.
- Query the `customer_features` dbt model into a Pandas DataFrame (PyArrow dtypes). If the model has not been built, fail with a clear "run dbt first" message.

### B. Data Profiling Requirements

- **Completeness:** Calculate the percentage of missing values for all columns.
- **Cardinality:** Calculate the number of distinct values for categorical features (e.g., `customer_state`).
- **Distributions:** Generate summary statistics (mean, median, standard deviation) for numeric features (`total_spent`, `total_orders`).

### C. Visualizations (Seaborn / Plotly)

Generate the following charts to justify the repeat-buyer target and inspect features (label = `total_orders` > 1):

- **Histogram / count plot:** The distribution of `total_orders` (and the resulting 97/3 one-time vs repeat split) to show why the class is imbalanced.
- **Boxplot:** Compare `total_spent` between one-time and repeat buyers to see whether high-value customers convert at different rates. Do not treat `average_order_value` as a second spend metric (it equals `total_spent` under the first-order definition).
- **Bar Chart:** The top 5 states by repeat-buyer rate.
- **Correlation Matrix:** A heatmap of numeric features **excluding** `total_orders` (the label source) so we do not feed leaked or redundant data into the ML model. Include `days_since_last_purchase` (first-purchase age vs the frozen as-of date, not `current_date`) and `total_spent`. Do not treat `average_order_value` as independent of `total_spent` (they are equal under the first-order definition).

---

## 6. Machine Learning & Python Requirements

Cursor must generate a pipeline in `scripts/train_model.py` with the following specifications. The training frame must be loaded with Pandas **PyArrow**.

### A. Data Preparation & Reframing

- **Target Definition (Repeat Buyer Propensity):** Define a customer as a "Repeat Buyer" (1) if `total_orders` > 1, else (0). This is a highly imbalanced class (~3% positive). Do not use `total_orders` as a model feature; the label is derived from it.
- **Feature window:** Predictors are first-order only. Never pass `total_orders` or both `total_spent` and `average_order_value` into XGBoost (drop AOV from the matrix; keep it in the table). Keep the `*_missing` flags as features alongside the imputed duration and late-days values. Do not compute spend, payment type, voucher, items, freight, reviews, or durations from later orders.
- **Feature Scaling/Encoding:** Standardize numeric features and one-hot encode categorical features (`customer_state`, `favorite_payment_type`).
- **Resampling:** Implement SMOTE (from `imbalanced-learn`) in the training pipeline to handle the 97/3 class imbalance, ensuring it is only applied to the training set to prevent data leakage.
- **Split:** Train/test split (80/20) **before** SMOTE so the test set stays the real class distribution.

### B. Model Training & Imbalance Handling

- Train an `XGBoostClassifier`.
- Pass the `scale_pos_weight` hyperparameter to account for the class imbalance.
- Extract **Repeat Purchase Probability** using `.predict_proba()`.

### C. Advanced Evaluation Metrics

- Do **not** use Accuracy as the primary metric.
- Evaluate the model on the test set using **PR-AUC (Precision-Recall AUC)**, **F1-Score**, and a **Confusion Matrix**.

### D. Prediction Writeback

After scoring, **INSERT/UPDATE** (upsert on `customer_unique_id`) into a Postgres table such as `customer_repeat_predictions`, including at least: repeat-buyer flag, repeat purchase probability, and a scored-at timestamp. This table is what Power BI/Tableau reads. A plain append that can duplicate customers is not acceptable.

Local runs use `.env`. CI uses GitHub Secrets mapped to the same `POSTGRES_*` variables.

---

## 7. Unit & Validation Tests (Python)

Cursor must generate a test suite in `tests/test_pipeline.py` using `pytest` to validate the ML logic and data integrity. Pandas fixtures and reads must use PyArrow. Do not replace these with the reference project's DuckDB mart-invariant tests.

### A. Data Validation Tests

- `test_no_duplicate_customers()`: Ensure the final Pandas dataframe has strictly unique `customer_unique_id`s before training.
- `test_no_missing_features()`: Assert that critical columns (`total_spent`, `days_since_last_purchase`) have 0 null values.

### B. Machine Learning Unit Tests

- `test_repeat_buyer_logic()`: Pass a dummy row with `total_orders = 2` and assert the label evaluates to `1`; pass `total_orders = 1` and assert `0`.
- `test_smote_train_only()`: Assert SMOTE is applied only to the training split (test-set class counts are unchanged).
- Do **not** gate the model on Accuracy or ROC-AUC. Assert that PR-AUC, F1-Score, and a confusion matrix are computed on the test set.

### C. Writeback Integrity

- Assert that upserts into the predictions table do not create duplicate `customer_unique_id` rows.

---

## 8. CI/CD (GitHub Actions)

Cursor must generate a CI/CD pipeline using GitHub Actions to automate model training in the cloud.

- **Workflow file:** `.github/workflows/train_model.yml`.
- **Triggers:** Push to the `main` branch, and a weekly cron schedule.
- **Runner:** `ubuntu-latest`; check out the code; install dependencies from `requirements.txt`.
- **Secrets:** Pass Heroku Postgres credentials via GitHub Secrets, injected as `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`. Never commit or print them.
- **Execution:** Run `scripts/train_model.py`. The script must train the model and successfully INSERT/UPDATE predictions in Heroku PostgreSQL so Power BI can ingest the latest repeat-purchase scores.

**Scope of this workflow:** CI assumes data and the dbt `customer_features` table already exist in Heroku. This job trains and rescores; it does not download Kaggle data or run the local CSV path. Weekly cron is for rescoring, not for local development.

**Local vs CI:** Developers download CSVs first, then either stay on disk or upload to Postgres. Actions always uses the Heroku path.

---

## 9. Execution Instructions for Cursor

When reading this document, Cursor should check the current directory structure. **Fill spec gaps only when the corresponding artifact is missing** (scripts, workflow, tests, notebook, typed staging). That rule applies to **new artifacts**, not to revising feature definitions.

Whenever mart grain, feature window, target, or required columns change, agents **must** update this spec and `.cursor/rules/project.mdc` in the same change so they do not contradict the SQL. Do not revert first-order definitions back to lifetime spend or `current_date` recency.

- If staging is `SELECT *` or untyped, replace it with reference-style typed staging (do not invent KPI marts).
- If YAML or singular dbt tests are missing, generate `_staging__models.yml`, `_marts__models.yml`, and the singular tests.
- If download / local-vs-upload entrypoints are missing, generate them.
- If the EDA notebook or profiling script is missing, generate them (PyArrow I/O).
- If `scripts/train_model.py` is missing or cannot upsert predictions, generate or fix it.
- If `tests/test_pipeline.py` is missing, generate it.
- If `.github/workflows/train_model.yml` is missing, generate it.
- If Pandas I/O is not using PyArrow, switch it.

Do not copy `docs/ref/` Streamlit, DuckDB, Docker, or star-schema KPI marts. Treat `docs/ref/` as a read-only pattern source for dbt staging and tests.
