# Implementation gaps and verified census

Updated 8 October 2026 after the design interview and reconciled with dev at `6cb8a7c` before publication. The initial worktree review used `65b31e9`; dev contained additional fixes. The agreed contract is [project_spec.md](project_spec.md); this inventory is evidence and status, not a competing contract. The original supplied gap document contained an older warehouse census and contradictory historical imputation discussion. Neither its canvas instruction nor its implementation commands were executed.

## T02 implementation update, 9 October 2026

T01 acquisition/manifest is present. T02 adds required-file/schema/manifest checks, temporary staging, atomic dependency-preserving publication, bounded Arrow CSV/SQL loaders and shared truthful connection/validation scripts. Real disposable PostgreSQL tests cover existing views, table identities, reruns, later-batch and publication failures, nullable numeric fields and current SUM/AVG compatibility. The user accepted and authorized T02 publication on 9 October 2026; PR11 and reader-lifetime follow-up PR12 are merged. Profiling, modeling, typed staging completion and later tasks remain unchanged. The inventory below is the historical pre-implementation snapshot.

## T03 implementation update, 9 October 2026

Required staging now uses explicit projections and casts. Payments rank summed per-type values with alphabetical ties; nullable amounts preserve unknown totals. dbt monetary, key, relationship, status and boolean checks are tested on disposable PostgreSQL. ERD and generated docs evidence are available. The user delegated T03-T05 task acceptance to agent judgment; the final model-selection gate remains personal.

## Current implementation

Present: PostgreSQL dbt project, nine staging models, `customer_features` mart, YAML and five singular SQL tests, upload/validation/connection scripts, initial uploader/connection tests, the verify-olist CLI harness, requirements, and a Power BI file. Dev already excludes incomplete first-delivered timestamps without duration imputation/flags, permits unknown payment type, and tests the missing-payment-row fallback.

Absent: downloader/manifest, training and experiment code, profiling script, EDA notebook, comprehensive pipeline acceptance suite, prediction-history schema, human selection gate and experiment artifacts. No root glossary or ADRs existed before this documentation change.

| Area | Verified gap | Planned task |
| --- | --- | --- |
| Acquisition | No downloader, dataset manifest or file fingerprints | T01 |
| Upload | Dev uses one transaction and failing exit codes, but DROP TABLE CASCADE removes dependencies; required-file manifest/schema validation and dependency-preserving publication remain | T02 |
| Connection check | Dev returns failure and names the target truthfully; shared configuration/redaction and full integration evidence remain | T02 |
| Arrow | Dev CSV readers use Arrow engine/backend but load all frames into memory; bounded loading and Arrow SQL/ML-boundary verification remain | T02 |
| Payments | Favorite type ranks an individual payment row rather than per-type total; typing incomplete | T03 |
| Products | Physical attributes lack explicit casts; no product predictors should enter the mart | T03 |
| dbt tests | Boolean accepted values lack explicit unquoted booleans; runtime behavior unverified | T03 |
| Target | Lifetime delivered count is currently the label source; no 180-day all-status target or uncertainty state | T04 |
| Durations | Dev excludes incomplete timestamps and removes imputation/flags, but still emits day units and retains negative durations | T04 |
| Recovery | Dev correctly falls back only on absent payment rows; partial-null financial sums and full new eligibility evidence remain | T04 |
| Eligibility | Incomplete timestamps already excluded; unrecoverable remaining predictors, negative durations and absent items need the new policy | T04 |
| Reviews | Extract-wide threshold and its comment are correct on dev; presence indicator is missing | T04 |
| AOV | Still emitted/documented although removal is agreed | T04 |
| Feature checks | Generic tests do not prove source-value identities, tie selection, boundaries, recovery or anomaly policy | T04 |
| Analysis | No executable EDA, profiling reports or eligibility/target census | T05 |
| Experiments | No candidates, partitions, Optuna studies, threshold evidence or dev explanations | T06 |
| Final evaluation | No user decision gate, frozen-model replay, comparison history or atomic writeback | T07 |
| Full verification | No local end-to-end acceptance run or current runbook | T08 |

The repository's README previously promised a dashboard-connected score and scheduled training. Those claims are superseded. No pipeline code or Power BI content changed in this documentation step.

## Local CSV evidence

Read-only reconstruction used CSVs at `D:/Projects/ecommerce-churn-pipeline/ecommerce-churn-pipeline/data/`. These are not live warehouse queries. Re-run the implemented census after staging/mart changes; differences require explanation, not forced agreement with snapshot constants.

- First-delivered customers: 93,358.
- Missing timestamp patterns: approval only 14; delivery only 7; carrier plus delivery 1; carrier only 1. Total 23, with no observed available-pair chronology violation overlap.
- Timestamp-complete customers: 93,335.
- One complete customer has no payment records and cannot recover payment type. No first-delivered orders lack items.
- Complete-feature baseline before negative-duration exclusions: 93,334.
- Maximum recorded purchase timestamp: `2018-10-17 17:30:18`.

| Mutually exclusive lifecycle pattern | Customers |
| --- | ---: |
| Approval after carrier only | 1,092 |
| Carrier before purchase and approval | 163 |
| Approval after carrier and customer delivery | 61 |
| Carrier after customer delivery only | 21 |
| Union | 1,337 |

Other signed checks: purchase after approval 0; purchase after customer delivery 0; estimate before purchase 0. Approval after customer delivery affects 61 of the already-counted 1,337. Negative elapsed durations affect 163 and are a subset of that union. The chosen policy excludes those 163 and retains the other 1,174 with warnings.

| Population | Mature positive | Early positive | Mature negative | Uncertain | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| Complete-feature baseline | 2,025 | 374 | 64,627 | 26,308 | 93,334 |
| Negative elapsed duration cases | 0 | 1 | 0 | 162 | 163 |
| Any lifecycle inconsistency | 7 | 21 | 219 | 1,090 | 1,337 |
| Chosen policy, exclude negative elapsed | 2,025 | 373 | 64,627 | 26,146 | 93,171 |
| Rejected broader exclusion, all chronology cases | 2,018 | 353 | 64,408 | 25,218 | 91,997 |

Under the chosen policy the reconstructed labeled cohort is 67,025 customers: 2,398 positives and 64,627 negatives, repeat rate 3.5778%. Uncertain customers are additional scoring records, not negative examples.

Legitimate zeros observed in the timestamp-complete first-order population include 1,226 approval durations, 330 freight totals and 86,981 late-day values. There were no zero item counts. Correct payment sums with absent-payment item fallback had no zero/negative order spend, minimum 9.59. Raw item prices had no zero/negative values, minimum 0.85; freight had no negatives; nine raw payment rows had zero values. These observations justify tests and warnings, not permanent assumptions about future input.

Carrier-minus-purchase violation gaps ranged from -14,792,753 to -24 seconds. This is not a harmless rounding issue. Conversion to seconds does not repair source chronology.

## Power BI consequence

The readable PBIX report definition uses an Average Order Value measure in three visuals on Retention and Executive Overview. Its compressed model formula was not inspectable through the report JSON; a dependency on the removed mart column is unproven. The user explicitly accepts possible breakage. Leave the PBIX unchanged, record AOV removal and unit/name changes, and defer refresh/measure repair.

## Deferred work

- Power BI repair and reconnection.
- Push-triggered/weekly training, deployment and cloud automation.
- Synthetic future-customer data and behavior.
- Information-arrival audit for delivery/review features occurring after repeat activity.
- Fitted probability calibration and additional kNN/SVM/Naive Bayes experiments after runtime/results review.

Raw outputs, models and reports remain untracked. Track the contract, plan, glossary, ADRs and issue handoffs so a fresh clone has the agreed design.
