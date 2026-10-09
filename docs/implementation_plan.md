# Implementation plan

Draft for the user's review, 8 October 2026. The design interview is confirmed; this document does not authorize coding or certify implementation. The authoritative behavior contract is [project_spec.md](project_spec.md), the evidence inventory is [implementation_gap.md](implementation_gap.md), and required cases are in [test_acceptance_matrix.md](test_acceptance_matrix.md).

## Execution and review

Track implementation work in the repository's GitHub map and child issues. The user authorized publication to dev and GitHub Issues. Exact issue bodies are linked below. Initial status is `needs-triage`, unassigned, pending plan review. Do not self-start implementation because the design/publication was confirmed.

After the user approves execution, a coordinator gives each coding subagent one bounded task and its accepted prerequisites. Independent work may run in parallel only when it does not share files or depend on unaccepted outputs. Agents provide their test cases, expected outputs, actual outcomes and artifacts for human review. Mark a task accepted/close its issue only after explicit user acceptance. Model and threshold selection is a separate human gate; acceptance of the training code does not select a candidate.

| Task | Scope | Accepted prerequisites | Review output |
| --- | --- | --- | --- |
| T01 | Download and dataset manifest | Plan review | Local/mocked download, hashes and failure tests |
| T02 | Atomic upload and truthful validation | T01 | Dataset publication/rollback and loader evidence |
| T03 | Typed staging and payment semantics | T02 | dbt staging tests/docs and exact grain checks |
| T04 | Features, target, eligibility and census | T03 | Fixture outputs, exclusion counts and target reconciliation |
| T05 | Profiles and executable EDA | T04 | Reports, executed notebook and verified summaries |
| T06 | Candidates, Bayesian studies and dev evidence | T05 | CV/dev report, models, explanations and runtime |
| T07 | Human gate, final-evaluation tooling and history | T06 | Fixture-tested gate and atomic persistence; no real test evaluation yet |
| T08 | Full integration, personal selection and final review | T07 and user selection | Selected-first test results, alternative comparisons, uncertain scores and runbook |

The sequence prioritizes correctness and inspectable evidence over parallel throughput. T07 schema/fixture work may be prepared independently after T04 is accepted, but its integration depends on T06. Avoid concurrent edits to shared SQL/YAML, loaders or experiment interfaces.

## T01: acquisition and manifest

Deliver `scripts/download_data.py` with explicit existing-file/download paths and a shared manifest/validation module. Validate the nine expected Kaggle filenames and required schemas, write SHA-256 hashes and source metadata, and atomically promote a completed download. Keep credentials/logs safe. Add needed acquisition dependencies deliberately and capture compatible dependency versions for later replay.

Acceptance: ING-01 through ING-03; mocked valid/missing/truncated/unsafe archives; rerun identity; clear CLI help and nonzero failures. Human reviews manifest example and test outcomes. No normal test downloads real Kaggle data.

## T02: atomic upload, Arrow loaders and validation

Dev already uses a transaction, Arrow CSV readers and truthful failing exit codes. Extend that implementation to stage/validate every required raw file before publishing while preserving tables used by dbt views; remove dependency-destructive DROP TABLE CASCADE publication. Share schema/manifest validation and connection creation, retain existing truthful messages, and improve full integration coverage. Arrow-backed reads are required; use bounded loading where appropriate rather than loading all frames simultaneously or passing unsupported Arrow engine options.

Acceptance: ING-03 through ING-07, including later-file/batch/publication fault injection with existing dbt dependencies. Provide before/after hashes/counts and database rollback evidence. Disposable PostgreSQL only for failure tests; refresh a live target only when explicitly requested.

## T03: typed staging, payment aggregation and dbt documentation

Finish explicit casts/columns in required staging models. Aggregate payment values by order/type before deterministic favorite selection; keep total across every payment row and any-voucher boolean. Preserve review-grain deduplication. Fix boolean test configuration, required keys, composite uniqueness and relationships. Document raw/staged cardinalities in `docs/erd.md`; allowlist this file in Git when created. Support `dbt docs generate`.

Acceptance: STG-01 through STG-06, fixture-executed dbt staging models, schema assertions and generated-doc checks. No mart category/photo predictors or reference KPI marts. Raw negative monetary values fail rather than being silently dropped.

## T04: customer features, 180-day target and eligibility diagnostics

Dev already excludes incomplete anchors without imputation/flags and has the correct missing-payment-row fallback predicate. Preserve those fixes, migrate day-unit SQL to the seconds contract, add review presence and remove AOV. Preserve first-delivered anchor selection before exclusion, frozen calendar recency and extract-wide review average. Add target/observation metadata, separate lifetime descriptive count, partial-null sum handling and the additional eligibility rules.

Build a diagnostic query/export explaining all candidate exclusions and retained chronology warnings. Use distinct-customer unions and mutually exclusive patterns. Reject malformed values with tests; preserve legitimate zeros and warning-only monetary cases. Parameterize observation end and as-of date without inventing coverage. Do not edit the Power BI file.

Acceptance: FEAT-01 through FEAT-19 and TGT-01 through TGT-05; source-value identities including partial-null sums; dbt mart tests; full-data census compared with the local evidence. Expect differences to be investigated, not patched to match counts. User reviews losses of positives/negatives/uncertain records and retained warnings.

## T05: profiles and EDA

Create `scripts/generate_data_profile.py` with per-table HTML and index, and `notebooks/01_eda_and_profiling.ipynb` using shared loaders/validations. Include cohort eligibility, target prevalence, early-positive counts, uncertain cases, sign/zero/range checks, feature comparisons and numeric correlations excluding target metadata/counts/IDs. No duplicate analysis implementations or dashboard edits.

Acceptance: REP-01/REP-02; notebook executed end-to-end; raw and final table links; fixture-exact summaries; clear absent-mart error. User reviews plots/denominators and exclusion reporting before modeling starts.

## T06: training, Bayesian optimization and dev reports

Provide `scripts/train_model.py` as a thin entry point over modular loading/validation, partitioning, preprocessing/candidate construction, Optuna study execution, metrics/threshold evidence, explanations and artifact serialization. Persist 60/20/20 membership and training 10-fold IDs with seed 42. Train all 12 agreed candidate variants with a strict predictor allowlist and no imputation.

Use seeded sequential TPE, ten total configurations per non-baseline variant, including an enqueued default, and five startup trials. Use training OOF F2 at the proposed threshold as the exploratory objective, retaining other metrics and per-fold variability. No pruning initially. Study fingerprints/budgets protect resume. Compute original real-fold class weights, including the explicitly combined XGBoost variant. Treat categorical/boolean predictors properly with SMOTENC before final one-hot encoding.

Proposed bounded search settings, reviewed before expensive runs:

| Component | Initial search space |
| --- | --- |
| Logistic regression | C from 0.01 to 100 on a log scale; compatible fixed solver/penalty; convergence checked |
| Random forest | 100/200/400 trees; depth 4/8/16/unlimited; leaf minimum 1 to 10; max features sqrt or all |
| XGBoost | 100/200/400 trees; depth 3 to 8; learning rate 0.03 to 0.3 log scale; row/column subsampling 0.6 to 1; child weight 1 to 10 |
| SMOTENC variants | Minority/majority ratio 0.1/0.25/0.5/1.0 where valid; neighbors 3 or 5; seed 42 |
| Threshold evidence | Fixed grid 0.00 through 1.00 in steps of 0.01; classify score >= threshold; show plateaus/fold variation and 0.5 reference |

These are implementation proposals rather than settled domain requirements. Validate the enqueued default is compatible with the final search space and dependency versions. If minority counts make a sampler setting invalid, report it rather than silently altering data or the budget. Avoid unrestricted combinations/parallel trial scheduling; measure a representative trial before full search. Small smoke fixtures may exercise fewer trials but real-run settings must remain intact.

Deliver CV/dev reports, threshold curves, all standard metrics plus recall/F2/MCC emphasis and calibration diagnostics, descriptive associations, grouped dev permutation importance and logistic coefficients. Save fitted training-only pipelines and JSON/Parquet/HTML artifacts. No final test evaluation or user-choice fabrication; label access for stratified partition construction/storage is allowed.

Acceptance: SPL-01 through SPL-04 and ML-01 through ML-10. User reviews real runtime, studies/configurations, thresholds, explanations and dev outcomes. Runtime/results review determines whether later classifiers warrant a separate task, not automatic scope expansion.

## T07: manual decision gate and prediction history

Create a decision-record schema and final-evaluation command that validates human approval, experiment/dataset/model fingerprints and all frozen thresholds before evaluating test predictions/metrics or publishing final predictions. Stratified partition creation may read labels solely for membership/storage. Score selected candidate first, then alternatives with the same saved training-only models. Do not refit or tune based on test results.

Create database experiment/candidate metadata and test/uncertain prediction history keyed by experiment/candidate/customer. Publish one candidate transactionally; mark the whole run complete only after expected outputs exist. Resume/idempotency must preserve previous experiments and candidates. Include nullable true labels and an explicit cohort. Save a complete comparison report with the original dev selection and rationale.

Acceptance: RUN-01 through RUN-03 and DB-01 through DB-03 on fixtures. Actual final test evaluation stays locked until the user selects a model and approves every candidate's frozen threshold. Human acceptance of tooling is distinct from approval of a real model decision record.

## T08: full verification and final personal review

Run the complete raw-to-report workflow against disposable PostgreSQL with small synthetic fixtures and fault-injection checks. Then run the approved full-data workflow on the user's chosen manual target, record package versions/commands/runtime, and reconcile raw/staged/mart/cohort counts. Update READMEs/runbook to actual tested commands and provide schema documentation outputs.

The user reviews CV/dev evidence and chooses a candidate before the real final command. Run selected-first test evaluation and uncertain scoring, then frozen alternatives. Record results even if they challenge the original selection. Explain remaining warnings, selection bias and uncalibrated score interpretation without changing the agreed model afterward.

Acceptance: REP-03/REP-04 plus replay of relevant integration cases; artifact/SQL reconciliation; unchanged PBIX; no scheduled workflow added. The user accepts the project only after reviewing the final reports, test evidence, uncertain predictions and decision history.

## Definition of a reviewable task

Each packet contains the task/issue, requirement links, changed files, case IDs, concrete fixtures and expected outputs, actual commands/results, artifact paths, census/warnings, limitations and blockers. Agents may mark work ready for review, but the user alone accepts it. Use the five configured triage labels; defer future work explicitly rather than leaving unimplemented automation in the current contract.

## Deferred backlog

Power BI repair; information-arrival audit; fitted calibration; kNN/SVM/Naive Bayes after timing/results review; synthetic future-customer data; automated cloud training, weekly jobs and deployment. Separate future issues require their own scope, data provenance, evaluation and acceptance decisions.

## GitHub issue map

The user explicitly authorized publication after the initial approval-review block. The reviewed handoff bodies are:

| Record | Local body |
| --- | --- |
| Map | [Planning map](issues/00-map.md) |
| T01 | [Acquisition](issues/t01.md) |
| T02 | [Atomic upload](issues/t02.md) |
| T03 | [Staging](issues/t03.md) |
| T04 | [Features and target](issues/t04.md) |
| T05 | [Profiles and EDA](issues/t05.md) |
| T06 | [Experiments](issues/t06.md) |
| T07 | [Decision gate and prediction history](issues/t07.md) |
| T08 | [Full verification](issues/t08.md) |

Published map: [#1](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/1). All tasks are open, unassigned and labelled `needs-triage` plus `wayfinder:task`. The map uses `wayfinder:map`. Native sub-issue links and blockers match the sequence below; textual references are also present in the child bodies.

| Task | Issue | Blocked by |
| --- | --- | --- |
| T01 | [#2](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/2) | User plan approval |
| T02 | [#3](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/3) | #2 |
| T03 | [#4](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/4) | #3 |
| T04 | [#5](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/5) | #4 |
| T05 | [#6](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/6) | #5 |
| T06 | [#7](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/7) | #6 |
| T07 | [#8](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/8) | #7 |
| T08 | [#9](https://github.com/ajs-02/ecommerce-churn-pipeline/issues/9) | #8 |

Created labels: `wayfinder:map`, `wayfinder:task`, `wayfinder:research`, `wayfinder:prototype`, and `wayfinder:grilling`. No coding task was started, assigned or accepted by publication.
