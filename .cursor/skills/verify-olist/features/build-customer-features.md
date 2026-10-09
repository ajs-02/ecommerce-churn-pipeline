# Build customer features

Build customer features runs dbt so staging views and the `customer_features` table match the models in `ecommerce_transform/`. The mart is one row per `customer_unique_id` and is what a later score and the dashboard read.

## Sub-features

- `build-all` runs `dbt run` for staging and the mart.
- `build-ready` leaves `customer_features` present in `public`.
- `build-confirmed` shows `dbt test` passing with `ERROR=0` after the build.

## How to get to it (user POV)

- From `ecommerce_transform/`, with `POSTGRES_*` and `DBT_PROFILES_DIR` set, run `dbt run`.
- From the repo root, run the same project through the virtualenv's `dbt.exe` with `--project-dir` and `--profiles-dir`.

## Driving it with verify_olist

Preconditions:

- Doctor reports `doctor: ok`, `connected: yes`, `raw_tables: 9/9`, `dbt_exe: ok`, and `instance_lock: clear`.
- A rebuild of the shared `public` mart and staging views is intended.
- `--allow-shared-write` is present. Without it the harness exits `3` and does not start dbt.

- **Build.** Run `.venv\Scripts\python.exe .cursor\skills\verify-olist\scripts\verify_olist.py run --feature build-customer-features --allow-shared-write -- .venv\Scripts\dbt.exe run --project-dir ecommerce_transform --profiles-dir ecommerce_transform`. Stdout contains `Completed successfully` and `Done.` with `ERROR=0`. `harness_exit_code` is `0`.
- **Doctor sees the table.** Run doctor again. Stdout contains `customer_features: present`.
- **Confirm with tests.** Drive [Test transforms](./test-transforms.md). `ERROR=0` is the stored-model check. `WARN` may be non-zero.
- **Proof.** Keep `artifacts/verify-olist/build-customer-features/transcript.txt` and the `test-transforms` transcript. The build log alone is not proof.

## Gotchas

- `dbt` does not read `.env` by itself. The harness injects `POSTGRES_*` into the child. Running `dbt.exe` in a bare shell fails looking for those variables.
- Profiles and the project both live in `ecommerce_transform/`. Omit either `--project-dir` or `--profiles-dir` and dbt will not see this project when the working directory is the repo root. The harness always starts the child in the repo root.
- `dbt run` replaces `customer_features`. Do not run it while validation is counting tables.
- Staging is views and the mart is a table. A successful run does not by itself prove tests. The following `dbt test` is required.
- Refusing `--allow-shared-write` is the safe outcome on this checkout. Do not report a refused build as a completed model.
