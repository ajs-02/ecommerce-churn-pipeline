# Olist pipeline verification map

This directory is the maintained source for verifying the user-facing behavior of the Olist repeat-buyer pipeline. Read the index before driving the CLI, then use the matching feature file as the recipe.

## Baseline preconditions

- Repo root is the working directory for every harness command.
- `.venv` exists and doctor reports `interpreter: venv`.
- `.env` is present. The harness loads it into the child process. Do not print it.
- The nine Olist CSVs are in `data/`.
- Doctor reports `connected: yes`, `database_matches_env: yes`, and `instance_lock: clear`.
- The warehouse is the single shared database from `.env`. Do not start a second drive, and do not retarget the host at local Postgres.

## Driving conventions

- Start every recipe from the baseline unless its preconditions say otherwise.
- Treat every command as literal. Keep flags and paths unchanged.
- Run every drive through `verify_olist.py run`, not by calling the script in a shell that has no `POSTGRES_*` variables.
- Writes need `--allow-shared-write` and an intentional reload. Without the flag the harness exits `3` and does not start the command.
- Restore nothing in the warehouse during cleanup. Cleanup removes the instance lock only. Do not remove proof transcripts.

## Proof and skip reporting

- Capture the command and the resulting stdout, not only a pass/fail summary.
- CLI proof is the transcript: command, `child_exit_code`, `harness_exit_code`, stdout, and stderr.
- A write is proved only with a later read-only command that shows the stored rows or dbt test result.
- Record the feature ID and the entry point used with every artifact.
- Report an unreachable path with the attempted command and the unmet precondition.
- Do not report a skipped entry point as verified through a different path.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with verify_olist` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands, and observable proof.

## Features

- [Check warehouse connection](./check-connection.md) covers the connection script and the doctor connection lines.
- [Upload CSVs](./upload-csvs.md) covers a full reload of `data/` into the shared warehouse.
- [Validate row counts](./validate-row-counts.md) covers the CSV-versus-database count check.
- [Build customer features](./build-customer-features.md) covers `dbt run` for staging views and the `customer_features` table.
- [Test transforms](./test-transforms.md) covers `dbt test`, including the two warn-level singular tests.
