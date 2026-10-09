# Olist repeat-order exploration

Explore first-delivered-order features associated with another order of any status within 180 days. Compare classifiers using recall, F2 and MCC as priorities, report the standard metrics, and let the project owner personally choose a candidate before final test evaluation.

The agreed design is in [the specification](docs/project_spec.md). [Implementation gaps](docs/implementation_gap.md), [the task plan](docs/implementation_plan.md), and [test acceptance cases](docs/test_acceptance_matrix.md) distinguish what exists from what remains to build. The design was confirmed on 8 October 2026, and pipeline implementation is in progress.

## Current status

The repository contains PostgreSQL/dbt staging and a customer feature mart, upload/validation/connection scripts, reproducible Olist acquisition and manifest validation, a CLI verification harness, and an existing Power BI report. Current dev already excludes incomplete anchor timestamps, avoids duration imputation, and applies the missing-payment-row spend fallback. T05 adds PostgreSQL profiles and executable EDA. Experiment code, the human selection gate and prediction-history writeback remain planned. T04 implements seconds-based anchor predictors, inclusive all-status 180-day targets and a shared eligibility diagnostic census.

T03 completes required typed staging, summed payment-type shares with alphabetical ties, null-propagating totals, raw negative/non-finite monetary checks, and executable staging integrity checks. See [staging keys and cardinalities](docs/erd.md) and [execution decisions](docs/execution_log.md). T03 validation passed98 tests with0 skips and1 intentional fixture warning; staging dbt run/test/docs are verified on disposable PostgreSQL; T04 feature/target validation passed 122 tests and real-data dbt build/test/docs.

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

1. Use Python 3.12, create a virtual environment and install `requirements.txt`. This is the tested end-to-end runtime; the required ydata-profiling version rejects Python 3.14.
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

Automated cloud training, push/weekly jobs, deployment, synthetic future-customer data, information-arrival audit, fitted calibration and additional classifiers are deferred. The owner delegated task review and routine decisions for T03 through T05. Personal model selection and final test evaluation remain gated; T06 is outside that authorization.

T04 diagnostics use `python scripts/export_feature_diagnostics.py --output-dir reports/feature_diagnostics` after `dbt build`. The JSON census separates all, eligible and excluded positive/negative/uncertain customers and early positives. Reason counts overlap; exclusive pattern counts and population totals count each customer once. Bounded Parquet parts preserve original timestamps and source evidence. The mart excludes unrecoverable predictors and negative purchase-relative elapsed times, while other chronology errors and monetary discrepancies over 0.01 remain warnings. Frozen configuration uses `dbt ... --vars '{as_of_date: "2018-10-17", observation_end_ts: "2018-10-17 17:30:18"}'`; defaults derive from all recorded purchases. Neither default proves observation coverage. `T03_POSTGRES_PORT` and `T04_POSTGRES_PORT` alongside `T02_POSTGRES_PORT` enable isolated integration checks.

T04 full-data evidence exactly reconciles 93,358 anchors and 93,171 eligible customers, including 2,398 positives, 64,627 negatives and 26,146 uncertain labels. The 187 excluded customers lose one early positive, 18 negatives and 168 uncertain labels. Retained warning customers total 1,454: 1,174 chronology cases plus 289 payment/item discrepancies with nine overlaps. See the execution log and implementation-gap update for evidence paths. Export publication stages a complete directory and preserves prior valid evidence on write failure. Directory promotion can briefly leave the destination path unavailable, matching acquisition behavior.

## Profiles and executable EDA

After `dbt build`, run `python scripts/generate_data_profile.py --output-dir reports`. The default and supported source is PostgreSQL. This creates ten genuine ydata profiles under `reports/profiles/`, a linked `reports/data_profile_report.html`, `summary.json`, and six plots. The JSON includes real ydata statistics beside independent Arrow-backed counts, missingness, cardinality, constant-column indicators and numeric sign/zero/range summaries. The shared dbt census supplies eligibility, exclusion/warning overlaps, early positives and uncertain cohorts. Completed reports survive later generation/write failures; promotion briefly makes the destination unavailable, matching acquisition/export publication.

Execute `python -m nbconvert --execute --to notebook --output 01_eda_executed.ipynb --output-dir reports notebooks/01_eda_and_profiling.ipynb` in the Python 3.12 environment. Set `OLIST_EDA_OUTPUT_DIR` to choose the summary/plot directory; its default is `reports/eda`. The notebook runs the shared analysis and displays six figures. Its checked-in outputs remain empty. Use a kernel from the same environment, for example `python -m ipykernel install --prefix .venv --name olist --display-name Olist`, then append `--ExecutePreprocessor.kernel_name=olist` to the execution command. A missing mart or diagnostics fails with `run dbt first`. No model is fitted or selected.

Repeat-rate comparisons use known labels only. State plots show the five largest labeled denominators, with alphabetical ties. Uncertain spend is separate. Correlations use the eight numeric predictors across all eligible customers; target metadata, identifiers, timestamps and lifetime delivered counts are excluded. Early-positive selection and retained post-purchase features limit prospective and causal interpretation. Undefined rates are JSON null, and constant-column correlations appear blank.

Profiling uses bounded Arrow SQL batches, then assembles one complete table for ydata; ydata is not a streaming statistics engine. Empty raw or feature tables fail explicitly rather than producing a fabricated profile. All nine required raw tables must exist. The pinned ydata-profiling 4.18.4/Pandas 2.3.3/Arrow 26.0.0 boundary uses a narrow numeric summarizer adapter for unsupported Arrow kurtosis/skewness and explicit DateTime hints. Input frames retain Arrow storage. Temporary arrays are statistics/plotting inputs, not estimator preprocessing. Setuptools 80.10.2 supplies ydata's legacy `pkg_resources` import. ydata's deprecation notice is documented; the agreed tool is retained. Full resolved dependency versions are recorded with task evidence.

For the complete acceptance suite, set `T02_POSTGRES_PORT`, `T03_POSTGRES_PORT`, `T04_POSTGRES_PORT` and `T05_POSTGRES_PORT` to a disposable cluster port and run `python -m pytest -q`. T05 uses a separate disposable `t05profiles` database and isolated dbt target/log paths. These checks reset fixture schemas, execute the notebook and generate real reports; never point them at a live target. Format checks use `python -m black --check scripts/generate_data_profile.py scripts/profiling_analysis.py scripts/profiling_adapter.py tests/test_profiling_integration.py`.
