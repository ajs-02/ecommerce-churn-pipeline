# Olist repeat-order exploration

Explore first-delivered-order features associated with another order of any status within 180 days. Compare classifiers using recall, F2 and MCC as priorities, report the standard metrics, and let the project owner personally choose a candidate before final test evaluation.

The agreed design is in [the specification](docs/project_spec.md). [Implementation gaps](docs/implementation_gap.md), [the task plan](docs/implementation_plan.md), and [test acceptance cases](docs/test_acceptance_matrix.md) distinguish what exists from what remains to build. The design was confirmed on 8 October 2026; pipeline implementation has not yet been updated to match it.

## Current status

The repository contains PostgreSQL/dbt staging and a customer feature mart, upload/validation/connection scripts, initial uploader/connection tests, a CLI verification harness, and an existing Power BI report. Current dev already excludes incomplete anchor timestamps, avoids duration imputation, and applies the missing-payment-row spend fallback. The downloader, profiling/EDA, experiment code, comprehensive acceptance tests, human selection gate and prediction-history writeback remain planned. SQL still uses day units and does not implement the new target.

## Agreed experiment

- Anchor at the first delivered order's purchase timestamp; count any distinct other order placed within the inclusive 180-day window.
- Include early observed positives; unfinished customers without a repeat have uncertain labels and are scored separately.
- Preserve first-delivered-order features, recover values only from that order's existing records, exclude unrecoverable inputs/negative elapsed durations, and report other chronology warnings.
- Express duration features in seconds, preserve calendar-based lateness/recency, add review presence, and remove average order value.
- Use stratified random 60/20/20 train/dev/test partitions, seed 42, with stratified ten-fold CV inside training only.
- Compare baselines, logistic regression, random forest and XGBoost variants. Use bounded Bayesian tuning and training out-of-fold threshold proposals.
- The owner reviews dev evidence, approves frozen thresholds and chooses the model. Evaluate that candidate first, then frozen alternatives, without test-based retuning or refitting.

This is historical exploratory classification. Post-purchase features, early-positive selection and uncalibrated scores limit prospective/probability claims. See the spec for exact definitions and evidence requirements.

## Data and tools

Both local and Heroku execution use PostgreSQL. CSVs are acquisition inputs; dbt owns the feature/target definitions. Pandas uses Arrow-backed data; planned experiments use scikit-learn, XGBoost, imbalanced-learn and Optuna. Customer outputs, reports and model artifacts remain outside Git.

## Existing local commands

1. Create a virtual environment and install `requirements.txt`.
2. Copy `.env.example` to `.env` and configure the chosen PostgreSQL target.
3. Place the nine Olist CSVs in `data/`.
4. Existing commands are `python scripts/upload_data.py`, `python scripts/validate_upload.py`, and `python scripts/test_connection.py`.
5. From `ecommerce_transform/`, run `dbt run`, `dbt test`, and `dbt docs generate`, using the configured profile/environment.

Dev has transactional uploads and failing exit codes, but uploads still drop tables with CASCADE and do not validate the complete dataset manifest. Do not treat these commands as proof of the planned dependency-preserving refresh or new feature contract. Each task will update this runbook to the commands actually verified during implementation.

## Existing dashboard and deferred work

Power BI remains unedited. AOV removal and feature renaming may break its refresh; the owner accepts that consequence and will repair the report later. There is no implemented probability binding or current scheduled-training requirement.

![Existing Olist dashboard recording](Power%20BI/Dashboard%20Recording.gif)

Automated cloud training, push/weekly jobs, deployment, synthetic future-customer data, information-arrival audit, fitted calibration and additional classifiers are deferred. Every coding task requires review of its outputs, test cases and outcomes before acceptance.
