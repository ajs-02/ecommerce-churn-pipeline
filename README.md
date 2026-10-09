# Olist repeat-order exploration

Explore first-delivered-order features associated with another order of any status within 180 days. Compare classifiers using recall, F2 and MCC as priorities, report the standard metrics, and let the project owner personally choose a candidate before final test evaluation.

The agreed design is in [the specification](docs/project_spec.md). [Implementation gaps](docs/implementation_gap.md), [the task plan](docs/implementation_plan.md), and [test acceptance cases](docs/test_acceptance_matrix.md) distinguish what exists from what remains to build. The design was confirmed on 8 October 2026, and pipeline implementation is in progress.

## Current status

The repository contains PostgreSQL/dbt staging and a customer feature mart, upload/validation/connection scripts, reproducible Olist acquisition and manifest validation, a CLI verification harness, and an existing Power BI report. Current dev already excludes incomplete anchor timestamps, avoids duration imputation, and applies the missing-payment-row spend fallback. Profiling/EDA, experiment code, human selection gate and prediction-history writeback remain planned. SQL still uses day units and does not implement the new target.

T03 completes required typed staging, summed payment-type shares with alphabetical ties, null-propagating totals, raw negative/non-finite monetary checks, and executable staging integrity checks. See [staging keys and cardinalities](docs/erd.md) and [execution decisions](docs/execution_log.md). T03 validation passed98 tests with0 skips and1 intentional fixture warning; staging dbt run/test/docs are verified on disposable PostgreSQL; the feature mart still awaits T04.

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
3. To validate nine existing Olist CSVs and write `data/dataset_manifest.json`, run `python scripts/download_data.py --mode existing --data-dir data`. The manifest records source mode, file sizes, row counts, columns, SHA-256 hashes, and a dataset fingerprint.
4. To acquire the Olist archive from Kaggle, configure Kaggle CLI credentials, then run `python scripts/download_data.py --mode download --data-dir data`. The command validates the staged archive before publishing it and preserves the current dataset when download or validation fails. Tests mock the external Kaggle command and do not need credentials or network access.
5. Existing database commands are `python scripts/upload_data.py`, `python scripts/validate_upload.py`, and `python scripts/test_connection.py`.
6. From `ecommerce_transform/`, run `dbt run`, `dbt test`, and `dbt docs generate`, using the configured profile/environment.

T02 implements transactional staging of all nine required files before publication. Upload and row-count validation check schema, source types and an existing dataset manifest. Successful refreshes preserve raw-table identities and dependent views. A failed file, batch or publication rolls back the complete dataset. CSV and SQL loaders return bounded Arrow-backed frames. New raw numeric columns support existing SUM/AVG operations, while identifiers and ZIP codes preserve source text. Existing compatible target column types are retained. Upload, validation and connection failures return nonzero exits without exposing connection URLs or passwords.

T02 was accepted by the user and merged through PR11 and PR12 on 9 October 2026. Verified entry points accept an optional dataset directory: `python scripts/upload_data.py <data-dir>` and `python scripts/validate_upload.py <data-dir>`. Upload refreshes the configured target, so select that target deliberately. Connection checking uses `python scripts/test_connection.py`. No live database refresh or dbt build was performed for T02.

The real PostgreSQL acceptance tests require a disposable local cluster with user `t02`, database `postgres`, trust authentication and a dedicated port. Set `T02_POSTGRES_PORT` to that cluster port, then run `python -m pytest -q`. These tests reset its public schema. Leave the variable unset to skip database tests. The verified cluster used PostgreSQL 18.6 at `127.0.0.1:55432`. Record count/content/OID evidence by also setting `T02_EVIDENCE_DIR` to an existing artifact directory. Python syntax checks use `python -m compileall -q scripts tests`. No dedicated typechecker is configured.

Download publication stages and validates the complete candidate before swapping the data directory. A failed rename restores the prior directory; if the operating system also prevents restoration, the error reports the retained `.olist-previous-*` backup. Concurrent readers can briefly find the destination missing during a directory rename. The manifest fingerprints archive bytes when downloaded, but it cannot detect upstream changes that remove complete CSV records unless the upstream source publishes a trusted expected size or checksum.

## Existing dashboard and deferred work

Power BI remains unedited. AOV removal and feature renaming may break its refresh; the owner accepts that consequence and will repair the report later. There is no implemented probability binding or current scheduled-training requirement.

![Existing Olist dashboard recording](Power%20BI/Dashboard%20Recording.gif)

Automated cloud training, push/weekly jobs, deployment, synthetic future-customer data, information-arrival audit, fitted calibration and additional classifiers are deferred. Every coding task requires review of its outputs, test cases and outcomes before acceptance.
