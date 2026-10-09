---
name: verify-olist
description: Drive the Olist repeat-buyer pipeline CLI (Postgres connection check, CSV upload, row-count validation, dbt run, and dbt test) and save transcripts as proof. Use when a change to scripts/, ecommerce_transform/, or warehouse loading needs a real end-to-end check.
---

# Verify the Olist pipeline

The user-facing surface is a short-lived CLI, not a server. Python scripts in `scripts/` load CSVs and talk to Postgres. dbt in `ecommerce_transform/` builds `customer_features`. Power BI (`Power BI/Olist Churn Analysis.pbix`) is a second surface with no scriptable harness; do not claim it was verified. `scripts/train_model.py` is specified and not in the tree; do not invent a scoring drive.

There is one shared warehouse: the database named by `.env`. That login cannot `CREATE DATABASE`. Local PostgreSQL 18 may be installed, but it is not the `.env` target and this skill has no password for it. Do not retarget `POSTGRES_HOST` to localhost. Two drives must not run at once. Writes (`upload_data.py`, `dbt run`, `dbt build`, `dbt seed`) replace objects in `public`. The harness refuses them unless `--allow-shared-write` is passed, and that flag is only for an intentional reload.

## Launch

From the repo root, with the existing virtualenv (do not create another, and do not `pip install` for this surface):

```
.venv\Scripts\python.exe .cursor\skills\verify-olist\scripts\verify_olist.py doctor
```

Ready when stdout contains `doctor: ok` and `connected: yes`. The same lines are saved to `artifacts/verify-olist/doctor/transcript.txt`.

There is no process to leave running. `doctor` loads `.env` for its own connection and does not export secrets into the shell. Each drive below starts its own child with those variables set in the child only.

`doctor: busy` means a live lock is held. Run Cleanup, then doctor again. Do not start a second drive.

## Doctor

Run the launch command again whenever a drive looks wrong. It is read-only.

Worth driving when all of these are true:

- `interpreter: venv`
- `modules: ok` (pandas, psycopg2, sqlalchemy, python-dotenv)
- `dbt_exe: ok`
- `env_keys: ok`
- `csv_files: 9/9`
- `connected: yes`
- `database_matches_env: yes`
- `instance_lock: clear` or `instance_lock: stale`

`raw_tables: 9/9` and `customer_features: present` mean upload and `dbt run` have already been done on this warehouse. Connection check does not need them. Row-count validation needs `raw_tables: 9/9`. dbt test and a rebuild need both.

`rolcreatedb: no` and `write_isolation: unavailable` are expected on this checkout. They mean a disposable second database cannot be created. Do not "fix" that by uploading into `public` as a trial.

`doctor: fail` or `connected: no`: stop. Do not point the scripts at a different host.

## Drive

Harness: `verify_olist.py`. Feature recipes live in `features/`. Read `features/README.md` first, then the feature file. A proof that uses one entry point is incomplete when that file lists others; say which entry points were not driven.

Start the child from the repo root through the harness so `.env` is applied without printing it and so the run takes the instance lock:

```
.venv\Scripts\python.exe .cursor\skills\verify-olist\scripts\verify_olist.py run --feature <feature-id> -- <command>
```

Commands the recipes use:

- `.venv\Scripts\python.exe scripts\test_connection.py`
- `.venv\Scripts\python.exe scripts\upload_data.py`
- `.venv\Scripts\python.exe scripts\validate_upload.py`
- `.venv\Scripts\dbt.exe run --project-dir ecommerce_transform --profiles-dir ecommerce_transform`
- `.venv\Scripts\dbt.exe test --project-dir ecommerce_transform --profiles-dir ecommerce_transform`

Upload and `dbt run` need `--allow-shared-write` before `--`, and only when a reload of the shared warehouse is intended. The harness exits `3` and writes no transcript when that flag is missing.

`test_connection.py` exits `1` when the connection fails. The success line names the host from the environment and does not hardcode Heroku. The harness passes only when the script exits `0` and stdout contains `Successfully connected`.

Stable handles are those command lines, the stdout tokens `Successfully connected`, `PASS`, `FAIL`, `Completed successfully`, and `Done.`, and the doctor keys above. Do not drive by clicking the Power BI file.

## Evidence

Write proof under `artifacts/verify-olist/<feature-id>/transcript.txt`. Doctor writes `artifacts/verify-olist/doctor/transcript.txt`. The harness prints `evidence: <relative path>` as the last line.

Proof standards:

- Drive the CLI the user runs. Do not satisfy a check by inserting rows, calling an internal function, or querying through a one-off client when a script or `dbt` command is the user path.
- The transcript must contain the command, both exit codes, stdout, and stderr. A final status line with no command is not proof.
- For a write (`upload`, `dbt run`), follow it with a read-only second view: `validate_upload.py` after upload, or `dbt test` after `dbt run`. The second transcript has to show the stored result.
- `dbt test` warnings are part of the observed result. Two singular tests are `severity: warn` by design. `ERROR=0` is the pass bar. Do not pass `--warn-error` and do not treat `WARN` as a skip.
- Do not treat `--allow-shared-write` as a dry run. It replaces `public` tables and views. If you did not pass it, the absence of a new transcript is the observation that the write did not start.

## Cleanup

```
.venv\Scripts\python.exe .cursor\skills\verify-olist\scripts\verify_olist.py cleanup
```

Cleanup deletes `artifacts/verify-olist/instance.lock` only. If that lock still names a process this harness started (matching pid and process creation time), cleanup kills that process tree. It does not kill by process name, does not stop PostgreSQL, and does not drop or rewrite warehouse objects.

After cleanup, the transcript files must still be on disk. A cleanup that removes `artifacts/verify-olist/<feature-id>/` is wrong.

Run cleanup after a failed or interrupted drive so the lock cannot block the next one.
