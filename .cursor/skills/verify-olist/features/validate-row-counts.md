# Validate row counts

Validate row counts compares each CSV in `data/` to the row count of the matching `public` table and prints `PASS` or `FAIL` per table.

## Sub-features

- `validate-pass` prints `PASS` when every CSV count equals the database count.
- `validate-fail` prints `FAIL` and exits `1` when any table is missing or the counts differ.
- `validate-empty` reports that `data/` is missing or has no CSVs and exits `1`.

## How to get to it (user POV)

- From the repo root, after upload, run `python scripts/validate_upload.py`.

## Driving it with verify_olist

Preconditions:

- Doctor reports `doctor: ok`, `connected: yes`, `csv_files: 9/9`, `raw_tables: 9/9`, and `instance_lock: clear`.
- No upload or `dbt run` is in progress. Both replace tables this command counts.

- **Count check.** Run `.venv\Scripts\python.exe .cursor\skills\verify-olist\scripts\verify_olist.py run --feature validate-row-counts -- .venv\Scripts\python.exe scripts\validate_upload.py`. The table lists all nine names: `customers`, `geolocation`, `order_items`, `order_payments`, `order_reviews`, `orders`, `product_category_name_translation`, `products`, `sellers`. Each status is `PASS`. `harness_exit_code` is `0`.
- **Mismatch.** A `FAIL` line or `harness_exit_code` `1` is the result. Do not start an upload to force a pass unless a reload was already the assigned task.
- **Proof.** Keep `artifacts/verify-olist/validate-row-counts/transcript.txt`. The proof is the nine status cells plus `harness_exit_code`, not a summary written afterward.

## Gotchas

- Pass a directory argument to check that folder. With no argument the command reads `data/`.
- Counts are exact `COUNT(*)` values, not planner estimates.
- A missing relation prints `FAIL` with the database error on that row. That is "upload has not been done", not a harness failure.
- Geolocation is large. Wait for the process to exit. Do not kill it and read a partial transcript.
