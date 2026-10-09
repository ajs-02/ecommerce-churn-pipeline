# Test transforms

Test transforms runs the dbt suite against the loaded warehouse: staging and mart YAML tests, plus singular tests for negative prices, delivered orders missing a delivery timestamp, and first-order spend versus item totals.

## Sub-features

- `test-suite` runs `dbt test` and prints the `Done.` summary.
- `test-error` fails the command when an error-severity test returns rows.
- `test-warn` records warn-severity failures without failing the command.

## How to get to it (user POV)

- From `ecommerce_transform/`, with `POSTGRES_*` and `DBT_PROFILES_DIR` set, run `dbt test`.
- From the repo root, run the same project through the virtualenv's `dbt.exe` with `--project-dir` and `--profiles-dir`.

## Driving it with verify_olist

Preconditions:

- Doctor reports `doctor: ok`, `connected: yes`, `raw_tables: 9/9`, `customer_features: present`, `dbt_exe: ok`, and `instance_lock: clear`.
- `dbt run` is not currently replacing those relations.

- **Suite.** Run `.venv\Scripts\python.exe .cursor\skills\verify-olist\scripts\verify_olist.py run --feature test-transforms -- .venv\Scripts\dbt.exe test --project-dir ecommerce_transform --profiles-dir ecommerce_transform`. Stdout contains `Done.` and `ERROR=0`. `harness_exit_code` is `0`. `WARN` may be greater than zero.
- **Warns that are expected.** The summary may warn on `assert_delivered_orders_have_delivery_date` and `assert_total_spent_matches_first_order_items`. Those warnings are the result, not a reason to change severity.
- **Hard failure.** `assert_no_negative_prices` and the YAML `unique`, `not_null`, `accepted_values`, and `relationships` tests are error severity. Any `ERROR` above zero means `harness_exit_code` is not `0`.
- **Proof.** Keep `artifacts/verify-olist/test-transforms/transcript.txt`. The proof is the `Done.` line with its `PASS`, `WARN`, `ERROR`, and `SKIP` counts.

## Gotchas

- Do not pass `--warn-error`. That turns the two intentional warns into a failed run.
- `dbt test` reads the shared warehouse. It does not need `--allow-shared-write`. Do not start `dbt run` in another process while it is open.
- `dbt` does not read `.env` by itself. Use the harness command so `POSTGRES_*` are set in the child.
- The child working directory is the repo root. Both `--project-dir ecommerce_transform` and `--profiles-dir ecommerce_transform` are required.
- A warn on delivered timestamps is a known Olist gap of about eight orders. Do not delete those rows to make `WARN=0`.
