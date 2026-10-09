# Olist repeat-order exploration specification

Agreed with the user on 8 October 2026. This contract replaces the supplied specification and any older feature, lifetime-label, dashboard, or scheduled-training requirements. It describes the agreed design, not the current implementation status. See [implementation gaps](implementation_gap.md), [task plan](implementation_plan.md), and [acceptance matrix](test_acceptance_matrix.md).

## 1. Purpose and scope

Explore first-delivered-order features and indicators associated with repeat ordering, compare classifiers, and let the user personally select a model after reviewing evidence. This is historical exploratory classification. Retained post-purchase features and the inclusion of early positives limit prospective and probability interpretations.

Use PostgreSQL for both local and Heroku execution. Download raw Olist CSVs into `data/`, load them into PostgreSQL, build dbt staging and one ML mart, then run analysis and experiments. CSV-only transformation or training, DuckDB, Streamlit, and reference star-schema marts are outside scope.

Power BI is finished and must remain unedited. Removing AOV or renaming features may break its refresh; document that consequence and defer repair. Automated training on pushes, weekly jobs, deployment, synthetic future-customer data, fitted probability calibration, and the information-arrival audit are deferred. kNN, SVM, and Naive Bayes are optional later experiments after initial results and runtime review.

No performance claim, task acceptance, or candidate selection is automatic. The user reviews outputs, test cases, and outcomes before accepting a task.

## 2. Customer, anchor, observation, and target

- Grain is exactly one row per `customer_unique_id`, joining orders through their order-specific `customer_id`.
- Require at least one delivered order. Select the anchor by `order_purchase_ts`, then `order_id`, among delivered orders. Select it before eligibility filtering; never substitute a later complete order.
- Set `target_window_end_ts = first_delivered_purchase_ts + interval '180 days'`.
- A repeat is another distinct `order_id` purchased in the inclusive interval `[first_delivered_purchase_ts, target_window_end_ts]`. Include every status: delivered, shipped, canceled, unavailable, invoiced, processing, created, approved. Same-day and same-timestamp distinct orders count. Orders before the anchor do not count.
- Default `observation_end_ts` is the maximum purchase timestamp across all recorded orders, including non-delivered orders. An explicit override is permitted, but it must not precede recorded purchases. Record the exact timestamp and its provenance. The default assumes the extract captures ordering activity through that timestamp; it does not prove coverage.
- Complete follow-up means `target_window_end_ts <= observation_end_ts`.
- `repeat_within_180_days` is `1` whenever a qualifying repeat is observed, including early positives; it is `0` when follow-up is complete and no repeat is observed; otherwise it is null.
- Mix early positives with other labeled customers in the same random split. Do not create a separate early-positive training partition. Report their counts and the resulting selection bias.
- Keep uncertain customers for analysis and scoring; do not assign them negative labels or compute classification metrics against their unknown outcomes.
- Preserve source timestamps consistently without inventing a timezone or using the execution host's timezone. Record source timestamp interpretation.

Required descriptive/target metadata includes `first_delivered_order_id`, `first_delivered_purchase_ts`, `target_window_end_ts`, `observation_end_ts`, `has_complete_followup`, and `repeat_within_180_days`. `total_orders` retains its existing lifetime delivered-order count for descriptive use only. It is no longer the target definition.

## 3. Predictors and units

Predictors use anchor-order records only. Preserve the extract-wide review threshold and frozen-date recency definitions. Use this explicit input allowlist; identifiers, timestamps, target metadata, follow-up flags, lifetime counts, and exclusion diagnostics are not predictors.

| Predictor | Definition |
| --- | --- |
| `customer_state` | State on the anchor order's customer record. |
| `total_spent` | Sum all anchor payment values; only when payment rows are absent, recover from sum of item price plus freight. A null payment type alone does not trigger spend replacement. |
| `seconds_since_first_purchase` | Frozen `as_of_date` minus anchor purchase date, multiplied by 86,400. This remains calendar-date age, not elapsed timestamp age. |
| `favorite_payment_type` | Sum anchor payments by type, choose the largest total value, break ties alphabetically using deterministic ordering. Never invent a type when it is unknown. |
| `item_count` | Number of anchor item lines, without join fan-out. Positive integer. |
| `freight_value` | Sum anchor item freight. |
| `used_voucher` | True if any anchor payment row has type `voucher`. |
| `delivery_seconds` | Epoch seconds from purchase to customer delivery. |
| `approval_seconds` | Epoch seconds from purchase to approval. |
| `carrier_seconds` | Epoch seconds from purchase to carrier handoff. |
| `after_estimated_delivery_seconds` | `max(customer_delivery_date - estimated_delivery_date, 0) * 86400`. This preserves calendar-day lateness; same-date delivery is zero regardless of time of day. |
| `review_below_average` | True if any staged anchor review score is strictly below the average of all staged review scores. False for no review or all scores at/above average. |
| `has_first_order_review` | True if at least one staged review belongs to the anchor; false otherwise. Later-order reviews do not affect it. |

Use seconds consistently for all duration/age predictors and unit-explicit column names. Preserve fractional seconds for elapsed calculations. The 180-day business horizon does not change. `as_of_date` defaults to the date of the maximum recorded purchase timestamp; an explicit override must not yield negative recency.

Remove `average_order_value`, `days_since_last_purchase`, `delivery_days`, `approval_days`, `carrier_days`, and the four duration `*_missing` flags. Replace the old recency/duration fields with their seconds names. Do not add category, photo, or later-order predictors.

## 4. Recovery, eligibility, and validity

Preserve raw/staged records. Eligibility exclusions apply to the final feature mart, with customer counts and reasons exported for review. Count overlaps explicitly so exclusion totals do not double-count customers.

1. Require the anchor's approval, carrier, customer-delivery, and estimated-delivery timestamps. Missing timestamps cannot be recovered from delivered status or invented values.
2. Recover values only from existing anchor records. No mean/median fill, inferred payment types, absolute-valued durations, clipping of negative elapsed times, or later-order substitutions. An aggregate depending on a null constituent is unknown, not the sum of the remaining known values: propagate that null to the affected predictor and apply eligibility rules. A null payment amount does not count as absent payment rows or authorize item-spend replacement. Non-finite raw monetary values fail validation.
3. Apply the specified no-review boolean definitions. Then exclude customers with remaining null selected predictors, including an unrecoverable payment type.
4. Exclude anchors with no item records; do not manufacture zero items or freight from absent items.
5. Exclude customers with negative purchase-to-approval, purchase-to-carrier, or purchase-to-customer-delivery elapsed durations. Report original timestamps and each reason.
6. Retain other lifecycle-order violations with warnings: carrier before approval, customer delivery before carrier, or approval after customer delivery. Report overlapping and mutually exclusive patterns. Estimate-before-purchase is a warning diagnostic. Never silently repair these records.

Hard checks reject duplicates, malformed required keys, failed relationships, invalid statuses, non-finite numeric predictors, fractional/nonpositive item counts in the final mart, negative item prices, freight or payment amounts, negative model spend/freight/lateness, and invalid configuration producing negative recency. Raw monetary errors abort publication/build rather than silently excluding rows.

Legitimate zeros include freight, on-time lateness, recency on the same frozen calendar date, equal-timestamp elapsed durations, false booleans, and negative-class labels. Allow individual zero payment rows. Zero-priced items and zero aggregate spend trigger review warnings, not automatic exclusion. The payment-versus-item spend comparison remains a warning with tolerance 0.01. Missing delivered timestamps remain an order-level warning plus the agreed customer-level exclusion.

Large valid values are visible in profiling; do not add arbitrary upper cutoffs or winsorization. Test value identities against source records to detect corruption beyond sign checks.

## 5. Acquisition, upload, and staging

Provide an idempotent Kaggle downloader for the nine Olist files, with an existing-files path, required-file validation, file hashes and a dataset manifest. Tests mock acquisition and require no Kaggle credentials/network. Do not overwrite a valid dataset with an incomplete download.

Upload all required raw tables as one dataset refresh. Load and validate temporary staging tables first; publish transactionally while preserving existing table identities/dependencies. Any file, chunk, or publication failure leaves the previous dataset intact and returns a nonzero exit status. Connection and validation scripts must also fail truthfully.

Use Pandas with Arrow-backed tabular data. CSV reads must use `engine='pyarrow'` and/or `dtype_backend='pyarrow'`; SQL reads use `dtype_backend='pyarrow'`. Choose an Arrow-compatible chunk/stream strategy rather than passing unsupported chunk options to the Arrow CSV engine. `pyarrow` is required. Convert to estimator-compatible arrays/categories only at the ML boundary, with tested feature names and types.

Keep credentials in `.env` through python-dotenv using `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD`. Never log credentials or connection URLs. Local and Heroku target settings use the same contract; current runs are manual.

Required typed staging: customers, orders, items, aggregated payments, products, reviews. Select explicit columns with casts and descriptions. Payments have one row per order. Items have unique `(order_id, order_item_id)`. Reviews preserve review grain, deduplicating source `review_id` by creation timestamp then order ID. Products support relationship checks but supply no model predictors. Optional unused geolocation/sellers/translation staging may remain.

Use `_staging__models.yml` and `_marts__models.yml`, without parallel schema files. Include unique/not-null keys, full status and boolean accepted values, relationship checks, descriptions and critical-column tests. Support `dbt docs generate` and document PK/FK cardinalities, including raw split payments versus aggregated staged payments.

## 6. Profiling and EDA

Provide `scripts/generate_data_profile.py`, per-table raw and feature reports, and `reports/data_profile_report.html` as their index. Default to PostgreSQL; optional CSV profiling inspects raw files only. Use ydata-profiling and Arrow-backed ingestion. Reports cover types, uniqueness/cardinality, missingness, zero variance, sign/zero/range checks, exclusions, timeline warnings, cohort counts and class proportions.

Provide executable `notebooks/01_eda_and_profiling.ipynb` using shared loader/validation code. It fails clearly with a 'run dbt first' message when the mart is absent. Include delivered-count and new-target distributions, first-order spend by target, top-five state repeat rates with denominators, numeric correlations excluding target metadata/identifiers/lifetime counts, and no AOV. Separate known-label comparisons from uncertain-customer summaries; report early positives and selection effects.

## 7. Partitions and candidates

Split the eligible labeled cohort randomly and stratifiably into 60% training, 20% development, 20% test, seed 42. Stable customer ordering and persisted membership make reruns reproducible. Stratified, shuffled 10-fold CV with seed 42 operates inside training only. Validate enough examples of each class exist; fail clearly rather than silently reducing folds. Uncertain customers enter no labeled partition.

| Family | Initial variants |
| --- | --- |
| Baselines | All-negative; all-positive |
| Logistic regression | Unweighted; class-weighted; SMOTENC without extra weighting |
| Random forest | Unweighted; class-weighted; SMOTENC without extra weighting |
| XGBoost | Unweighted; class-weighted; SMOTENC without extra weighting; SMOTENC plus weighting |

These are separate comparison candidates, not a stacking/voting ensemble. Fit numeric scaling and categorical encoding on training-fold records only. Treat booleans as categorical for SMOTENC; keep categories valid, then encode for the estimator. Handle unseen categories consistently. No statistical predictor imputation is permitted.

Compute class weights from real training-fold labels, excluding synthetic records and dev/test labels. For the combined XGBoost variant, retain the original fold's negative/positive ratio after oversampling so the combined treatment is explicit. Oversampling only touches the fitting portion of a fold; evaluation class counts remain unchanged. Persist sampler settings and synthetic counts. Initial sampler/search details are proposed in the task plan and reviewed before full runs.

## 8. Bayesian tuning, thresholds, and metrics

Use Optuna TPE with seed 42, sequential trials, no initial pruning, 10 total configurations per non-baseline variant including an enqueued default configuration, and five startup trials. Persist studies and enforce the total budget on resume. Every successful configuration completes the same 10 training folds. Trial failures are recorded, not hidden; they consume the attempted-trial budget unless the user approves an extension.

Tune toward F2 while recording recall, MCC, standard supporting metrics and fit time. Generate training out-of-fold scores for each configuration, propose its F2-maximizing threshold using those scores, and use the resulting out-of-fold F2 as the exploratory optimization objective. CV used for configuration/threshold selection is development evidence, not an unbiased final estimate. Inspect fold variation and threshold stability instead of claiming an exact universally optimal threshold.

Report candidate results at 0.5 and its proposed threshold; show development threshold curves and let the user approve the frozen thresholds and personally choose the candidate. Recall, F2 (`beta=2`, repeat positive class), and MCC take priority. Also include accuracy, precision, F1, confusion matrix/support, balanced accuracy, specificity, ROC-AUC, average precision, PR/ROC curves, Brier score, log loss, reliability curves and score distributions. Name average precision explicitly; if trapezoidal PR-AUC is also computed, distinguish it.

Report undefined metrics explicitly with a documented policy and support counts. Baselines must not crash probability metrics. Uncertain-label rows never enter metric calculations. Raw positive-class probability outputs remain uncalibrated model scores; fitted calibration is deferred.

No numeric model-quality gate or automated winner selection replaces the user's review. Baselines, metrics, variability and feature evidence inform acceptance even if performance is weak.

## 9. Human decision gate and final evaluation

First produce CV, dev, threshold and feature-analysis evidence. Require a decision record identifying experiment/dataset/configuration fingerprints, the user's selected candidate, frozen configurations and approved thresholds for every candidate, and the user's rationale/approval. Automation must not fabricate human approval.

Partition construction may read labels to stratify and store the isolated test membership/labels. Before a matching decision record, the experiment must not evaluate test predictions, calculate test metrics, use test outcomes for tuning/selection, or publish final predictions. Evaluate the selected candidate first on test and uncertain customers, then frozen alternatives on those same cohorts. Document selection history even if an alternative tests better. No test-based retuning or silent replacement of the selected candidate.

Every saved candidate is fitted on the training partition only; use it unchanged for dev, test, and uncertain scoring. No refit on train+dev or all labeled customers in this experiment. Feature interpretation includes label-based descriptions, logistic coefficients and dev permutation importance, grouped by original feature. Describe associations, not causation. Audit information arrival after the outcome only in deferred work.

## 10. Artifacts and prediction persistence

Each experiment directory stores dataset/code/dependency fingerprints, timestamp conventions, observation end/as-of date, feature allowlist, eligibility census, partition/fold membership, studies, configurations, thresholds, fitted preprocessing/model pipelines, training OOF/dev/test/uncertain predictions, metrics, plots, runtime and decision history. Use JSON/Parquet plus an HTML comparison report. Record execution order and whether results are pre-selection or post-selection. Keep customer outputs, reports, models and SQLite study files out of Git.

PostgreSQL prediction history is keyed by `(experiment_id, candidate_id, customer_unique_id)` for test and uncertain cohorts. Store positive-class score, frozen threshold, predicted label, nullable observed label, cohort, scored-at timestamp and model/configuration fingerprint. Store experiment and selected-candidate metadata separately. Upserts are idempotent within that key and do not overwrite other experiments/candidates. A candidate's publish transaction is atomic; mark overall final-evaluation completion only after all expected candidate outputs exist. Retain previous completed runs on failure.

## 11. Verification and acceptance

Use pytest plus dbt against disposable PostgreSQL, Arrow-backed fixtures, hand-calculated feature/target examples, split/resampling isolation tests, saved-model replay, acquisition failure mocks, upload/writeback failure injection, notebook execution and report checks. Full-data validation exports actual counts and discrepancies; never use snapshot row counts as timeless test constants.

Every task includes planned cases and expected outputs before coding, then actual commands, results, artifacts, warnings and limitations for the user's review before acceptance. No subagent begins dependent work until its prerequisites are accepted. See the task plan and acceptance matrix for complete coverage.
