# Check warehouse connection

Check warehouse connection tells the user whether `.env` can open the configured Postgres database and prints the server version.

## Sub-features

- `connect-ok` opens the database and prints the success line.
- `connect-fail` prints the failure line when the host, credentials, or network reject the session.
- `connect-doctor` reports the same reachability. A failed script exits `1`.

## How to get to it (user POV)

- From the repo root, run `python scripts/test_connection.py` with the project virtualenv.
- Run doctor, which opens the same database and prints `connected: yes` or `connected: no`.

## Driving it with verify_olist

Preconditions:

- Doctor has been run in this session.
- `interpreter: venv`, `env_keys: ok`, and `instance_lock: clear`.
- `csv_files` and `raw_tables` may be incomplete; this feature does not read them.

- **Script entry.** Run the connection script. Run `.venv\Scripts\python.exe .cursor\skills\verify-olist\scripts\verify_olist.py run --feature check-connection -- .venv\Scripts\python.exe scripts\test_connection.py`. Stdout contains `Successfully connected` and a `Database version:` line. `harness_exit_code` is `0`.
- **Doctor entry.** Run `.venv\Scripts\python.exe .cursor\skills\verify-olist\scripts\verify_olist.py doctor`. Stdout contains `connected: yes` and `database_matches_env: yes`.
- **Failure observation.** If the script prints `Failed to connect to the database.`, both `child_exit_code` and `harness_exit_code` are `1`. Stop. Do not edit `.env` from the harness.
- **Proof.** Keep `artifacts/verify-olist/check-connection/transcript.txt` and `artifacts/verify-olist/doctor/transcript.txt`. Both must show a successful open of the configured database.

## Gotchas

- The script exits `1` on failure. The harness passes only when that exit code is `0` and stdout contains `Successfully connected`.
- The success sentence names the configured host. Do not treat the word Heroku as proof of which server answered. Use doctor `database_matches_env: yes`.
- Doctor and the script both use `.env`. A shell with empty `POSTGRES_*` variables is fine; a shell that already exports different `POSTGRES_*` values wins over `.env`, and `database_matches_env: no` means the child hit the wrong database.
