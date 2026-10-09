# Upload CSVs

Upload CSVs reloads every CSV in a data directory into the shared Postgres `public` schema, replacing each existing table on the first chunk of that file.

## Sub-features

- `upload-data-dir` loads the nine files in `data/`.
- `upload-custom-dir` loads CSVs from a directory passed on the command line.
- `upload-confirmed` shows the stored row counts from the validation command after the reload.

## How to get to it (user POV)

- From the repo root, run `python scripts/upload_data.py` to load `data/`.
- Run `python scripts/upload_data.py <directory>` to load a different folder of CSVs into the same database.

## Driving it with verify_olist

Preconditions:

- Doctor reports `doctor: ok`, `connected: yes`, `csv_files: 9/9`, and `instance_lock: clear`.
- A reload of the shared warehouse is intended. This login cannot create a second database.
- `--allow-shared-write` is present. Without it the harness exits `3` and does not start the upload.

- **Default directory.** Load `data/`. Run `.venv\Scripts\python.exe .cursor\skills\verify-olist\scripts\verify_olist.py run --feature upload-csvs --allow-shared-write -- .venv\Scripts\python.exe scripts\upload_data.py`. Stdout contains `Found 9 files. Starting upload...` and one `Successfully uploaded` line per file. `harness_exit_code` is `0`.
- **Custom directory.** Load another folder. Run `.venv\Scripts\python.exe .cursor\skills\verify-olist\scripts\verify_olist.py run --feature upload-csvs --allow-shared-write -- .venv\Scripts\python.exe scripts\upload_data.py <directory>`. Stdout names that directory's files. The tables still land in the shared `public` schema.
- **Confirm stored rows.** Run the row-count check in [Validate row counts](./validate-row-counts.md) on the same directory. Every printed status is `PASS` for the files that were uploaded.
- **Proof.** Keep `artifacts/verify-olist/upload-csvs/transcript.txt` and the validation transcript. The upload log alone is not proof.

## Gotchas

- The load reads each CSV with PyArrow, then replaces every table inside one transaction. A failure rolls that transaction back and the process exits `1`. A missing directory or an empty directory also exits `1`.
- Table names drop a leading `olist_` and a trailing `_dataset`. `product_category_name_translation.csv` keeps that name.
- Do not point a custom directory at a tiny fixture and then expect validation of `data/` to pass.
- Refusing `--allow-shared-write` is the safe outcome on this checkout. Do not report a refused upload as a successful reload.
