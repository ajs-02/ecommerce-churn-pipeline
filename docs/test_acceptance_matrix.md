# Test and acceptance matrix

Use with [project_spec.md](project_spec.md). These cases specify expected behavior; add cases only for meaningful new risks. Small relational fixtures must use Arrow-backed Pandas where applicable and real disposable PostgreSQL for SQL, transactions and dependency behavior. No tests require production credentials, Kaggle network access, Power BI edits or GitHub Actions.

Every task provides test-case IDs, fixture inputs, independently calculated expected outputs, commands, actual outcomes and artifact paths. The user reviews them before accepting the task. Snapshot counts are comparison evidence, never permanent pass/fail constants.

## Acquisition and publication

| ID | Case | Expected outcome |
| --- | --- | --- |
| ING-01 | Valid local dataset / mocked download | Nine required files validated, hashes and manifest recorded; second run preserves contents. |
| ING-02 | Missing/truncated file, unsafe archive path, failed download | Clear failing exit; valid prior dataset survives; no extraction outside intended directory. |
| ING-03 | Malformed key/type/schema | Validation reports file/field without secrets; no partial dataset publication. |
| ING-04 | Failure after a later batch/file or during publication | All previous raw tables remain unchanged; transaction rollback; failure exit. |
| ING-05 | Successful refresh with staging views already present | Counts/content match manifest; table dependencies survive; rerun creates no duplicates. |
| ING-06 | Connection or validation failure | Nonzero exit and truthful target/result; no credential/URL exposure. |
| ING-07 | CSV chunks and SQL loaders | Arrow-backed dtypes; bounded load strategy; estimator conversion only at ML boundary. |

## Staging and first-order identity

| ID | Case | Expected outcome |
| --- | --- | --- |
| STG-01 | Key duplicates/nulls, orphan FKs, unknown status, invalid booleans | Required dbt checks fail; full known Olist statuses pass. |
| STG-02 | Typed customers/orders/items/products/reviews/payments | Explicit expected casts, column sets and grain; item composite key unique. |
| STG-03 | Duplicate review ID across orders | Earliest creation then order ID wins; one staged row per review ID. |
| STG-04 | Split tender: voucher 30+30, card 50 | Favorite is voucher; total is 110; used_voucher true; one staged payment row per order. |
| STG-05 | Equal per-type totals and reordered rows | Alphabetical deterministic winner; results unchanged by source row order. |
| STG-06 | Negative item price/freight/payment | Hard failure; old published dataset survives where relevant. Zero freight/payment rows pass. |
| FEAT-01 | Multiple customer IDs, delivered and canceled orders, purchase ties | One customer row; earliest delivered anchor then order ID. Non-delivered earlier orders do not become anchor. |
| FEAT-02 | Earliest delivered anchor incomplete, later delivered order complete | Customer excluded with reason; later order is not substituted. |
| FEAT-03 | Later orders/reviews/spend differ | Anchor state/spend/items/freight/voucher/durations/review presence stay unchanged. Global review-average sensitivity is tested separately. |

## Predictor values and eligibility

| ID | Case | Expected outcome |
| --- | --- | --- |
| FEAT-04 | Payment rows absent, items available | Item-plus-freight spend recovered; payment type remains unknown and customer excluded if unrecoverable. Diagnostic shows recovered spend. |
| FEAT-05 | Payment rows exist but payment type null | Recorded payment total is not replaced by item sum; type is not invented; eligibility reports null. |
| FEAT-06 | Multiple item/payment/review rows | Exact spend/freight/line counts without fan-out; no item records cause exclusion rather than zeros. |
| FEAT-07 | Known timestamp intervals, fractional interval and equal timestamps | Exact seconds, including fractional values; zero duration passes. No day-named output predictors. |
| FEAT-08 | Early/on-estimate-date/next-date delivery | Lateness 0/0/86,400, independent of time within the same date. Null estimate/delivery causes exclusion, not zero fill. |
| FEAT-09 | Frozen date equals anchor date; next date; invalid earlier date | Recency 0/86,400; invalid earlier configuration fails; rerun does not depend on current date. |
| FEAT-10 | No reviews; all at/above average; any strictly below | `(below,present)` is `(false,false)`, `(false,true)`, `(true,true)`. Score equal to threshold is not below. |
| FEAT-11 | Global staged average versus first-order-only average | Threshold uses all deduplicated staged reviews exactly, matching existing definition. |
| FEAT-12 | Each unrecoverable null input independently | Customer excluded with explicit reason, overlap totals reconcile. Unused-field null alone does not exclude. |
| FEAT-13 | Each negative purchase-to-event duration | Excluded without clipping/absolute value/imputation; raw timestamps preserved. |
| FEAT-14 | Approval after carrier/delivery or carrier after delivery, all purchase-relative durations nonnegative | Retained with warning(s); mutually exclusive and overlap counts reconcile. Estimate-before-purchase diagnostic warns. |
| FEAT-15 | Negative spend/freight/lateness, non-finite numbers, fractional/nonpositive item count | Final-mart checks fail. Boolean false and label zero remain valid. |
| FEAT-16 | Zero order spend, zero item price, payment/item discrepancy | Warning with source evidence; no automatic exclusion/replacement; discrepancy tolerance 0.01. |
| FEAT-17 | Source-to-feature identity checks | Recomputed anchor sums, seconds, dates and review booleans match every tested feature; sign checks alone are insufficient. |
| FEAT-18 | Schema and predictor allowlist | No AOV, old day columns, duration missingness flags, category/photo fields or unintended predictors. |
| FEAT-19 | Mix valid and null payment/item-price/freight constituents | Affected sums remain unknown rather than silently skipping nulls; no payment-present fallback; exclude when the selected predictor is unrecoverable. A null unused source value alone does not exclude. Non-finite raw amounts fail validation. |

## Target and partition integrity

| ID | Case | Expected outcome |
| --- | --- | --- |
| TGT-01 | Repeat order in each of all eight statuses | Positive if within window; status does not alter target. |
| TGT-02 | Same timestamp, exactly 180 days, immediately after, before anchor | Distinct same-time and exact-boundary orders count; later/outside and earlier orders do not. Anchor never counts itself. |
| TGT-03 | Duplicate joined rows / multiple customer IDs | Distinct order counting and unique customer output; no false repeat from fan-out. |
| TGT-04 | Mature repeat, early repeat, mature no repeat, unfinished no repeat | Labels 1/1/0/null; early positive remains in labeled cohort. |
| TGT-05 | Latest recorded order not delivered, exact maturity boundary, override earlier than records | All-status max defines cutoff; equality is complete follow-up; invalid override fails. |
| SPL-01 | Stratified 60/20/20 seed 42, reordered input | Stable membership after canonical ordering; proportions subject only to integer rounding; disjoint customers. |
| SPL-02 | Training-only shuffled stratified 10 folds | Same persisted fold IDs across candidates/trials; each training row has one OOF prediction; no dev/test/uncertain membership. |
| SPL-03 | Too few examples for 10 folds | Clear failure; no silent fold reduction. |
| SPL-04 | Predictor exclusions | Customer/order IDs, target/follow-up fields, lifetime counts and diagnostics never enter model matrix. |

## Modeling and explanations

| ID | Case | Expected outcome |
| --- | --- | --- |
| ML-01 | All 12 candidate configurations | Two baselines, three logistic, three forest, four XGBoost variants; weighting/resampling matches contract. |
| ML-02 | Fit spies or distribution-shift fixture | Scaling, encoding, weights and SMOTENC fit only fitting-fold records; evaluation class counts unchanged. |
| ML-03 | SMOTENC mixed inputs and unseen categories | Synthetic categorical/boolean values valid; feature names/types stable; scoring unseen category does not refit. |
| ML-04 | XGBoost combined weighting | Original real fold class ratio retained after oversampling; no dev/test labels used. |
| ML-05 | Optuna settings and interrupted study | Seeded TPE, five startup trials, ten total configurations including default, sequential full-fold trials; resume respects budget and experiment fingerprint. |
| ML-06 | Threshold sweep with known OOF scores | F2-maximizing proposal derived solely from training OOF; equal/zero/one scores handled; dev shows stability and 0.5 comparison. |
| ML-07 | Hand-calculated confusion matrix and degenerate baselines | Recall, F2 beta=2, MCC, accuracy, precision, F1/support and auxiliary metrics correct; undefined results documented. |
| ML-08 | Probability outputs | Positive-class mapping correct; finite scores in [0,1]; AP/ROC/PR/Brier/log loss/reliability calculated on known labels only. |
| ML-09 | Coefficients/permutation feature mapping | Names map to original features, categorical groups are handled together, known-signal fixture produces expected evidence. No test data used for explanations. |
| ML-10 | Saved preprocessing/model replay | Same predictions within justified numeric tolerance; versions, feature ordering and dataset fingerprint checked. |

## Human gate, writeback, and reports

| ID | Case | Expected outcome |
| --- | --- | --- |
| RUN-01 | No/mismatched decision record | Final test predictions/metrics, test-based tuning/selection and publication refused. Label access solely for stratified partition creation/storage is permitted. |
| RUN-02 | Valid human decision | Selected candidate evaluated first, alternatives afterward; all candidate configurations/thresholds frozen; history records original choice. |
| RUN-03 | Evaluate/test/uncertain commands | No fit calls; saved training-only candidates score identical customer sets; unknown labels remain null. |
| DB-01 | Same experiment/candidate/customer rerun | Idempotent upsert; no duplicates. Different candidates/experiments preserve separate rows. |
| DB-02 | Failure midway through candidate write | Transaction rollback; no partial candidate publication; prior completed runs preserved. |
| DB-03 | Failure between candidates | Partial run marked incomplete, not globally completed; resume recognizes completed candidate outputs. |
| REP-01 | Small fixture profiles/census | Independently verified summaries, all required table links, exclusion/cohort/sign/zero warnings present. |
| REP-02 | Notebook execution and absent mart | Notebook executes using shared code; absent mart gives 'run dbt first'; no secret output. |
| REP-03 | Full raw-to-results smoke run | Download bypass, upload, dbt run/test/docs, profiles, small-budget experiment, mocked decision gate and writeback all exercised on disposable database. No production/test outcomes used for smoke fixtures. |
| REP-04 | Real full-data review | Counts reconcile at every stage; differences from local snapshot explained; warnings and selection bias disclosed; actual user selection unlocks final evaluation. |

## Review packet

Provide: task ID and linked issue; changed-file list; case IDs and expected results; actual commands and outcomes; artifact paths; warning/exclusion census; known limitations; and remaining blockers. Passing tests means ready for review, not accepted. Record user acceptance before closing an issue or starting dependent work.
