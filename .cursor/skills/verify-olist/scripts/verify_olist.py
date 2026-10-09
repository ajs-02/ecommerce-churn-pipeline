#!/usr/bin/env python
"""Harness for the Olist pipeline CLI.

Loads .env into the child process without printing it, refuses a second
concurrent drive, and refuses warehouse writes unless explicitly allowed.
Proof transcripts are written under artifacts/verify-olist/ and are never
deleted by cleanup.
"""

from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve()
REPO_ROOT = SCRIPT_PATH.parents[4]
EVIDENCE_ROOT = REPO_ROOT / "artifacts" / "verify-olist"
LOCK_PATH = EVIDENCE_ROOT / "instance.lock"
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
DBT_EXE = REPO_ROOT / ".venv" / "Scripts" / "dbt.exe"

REQUIRED_ENV = (
    "POSTGRES_HOST",
    "POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
)
CSV_FILES = (
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
)
RAW_TABLES = (
    "customers",
    "geolocation",
    "order_items",
    "order_payments",
    "order_reviews",
    "orders",
    "products",
    "sellers",
    "product_category_name_translation",
)
WRITE_VERBS = {"run", "build", "seed", "snapshot", "run-operation"}
FEATURE_RE = re.compile(r"[a-z0-9-]+")

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", ctypes.c_uint32),
        ("dwHighDateTime", ctypes.c_uint32),
    ]


def _kernel32():
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetProcessTimes.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
        ctypes.POINTER(FILETIME),
    ]
    kernel.GetProcessTimes.restype = ctypes.c_bool
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.restype = ctypes.c_bool
    return kernel


def process_create_time(pid: int | None) -> int | None:
    if not pid or pid <= 0:
        return None
    kernel = _kernel32()
    handle = kernel.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        created = FILETIME()
        exited = FILETIME()
        kernel_time = FILETIME()
        user_time = FILETIME()
        ok = kernel.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        )
        if not ok:
            return None
        return (created.dwHighDateTime << 32) | created.dwLowDateTime
    finally:
        kernel.CloseHandle(handle)


def pid_alive(pid: int | None) -> bool:
    return process_create_time(pid) is not None


def load_env_file() -> dict[str, str]:
    from dotenv import dotenv_values

    values = dotenv_values(REPO_ROOT / ".env")
    return {key: value for key, value in values.items() if value}


def child_env(file_values: dict[str, str]) -> dict[str, str]:
    env = os.environ.copy()
    for key, value in file_values.items():
        if not env.get(key):
            env[key] = value
    return env


def scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text


def secrets_from(file_values: dict[str, str]) -> list[str]:
    password = file_values.get("POSTGRES_PASSWORD", "")
    return [password] if password else []


def read_lock() -> dict | None:
    if not LOCK_PATH.exists():
        return None
    try:
        return json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"corrupt": True}


def lock_holder_alive(info: dict | None) -> int | None:
    if not info or info.get("corrupt"):
        return None
    for key in ("child_pid", "helper_pid"):
        pid = info.get(key)
        expected = info.get(f"{key}_created")
        actual = process_create_time(pid)
        if actual is not None and (expected is None or actual == expected):
            return pid
    return None


def acquire_lock(feature: str) -> None:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    payload = {
        "helper_pid": os.getpid(),
        "helper_pid_created": process_create_time(os.getpid()),
        "child_pid": None,
        "child_pid_created": None,
        "feature": feature,
    }
    for _ in range(3):
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            info = read_lock()
            holder = lock_holder_alive(info)
            if holder:
                raise SystemExit(f"refused: instance lock held by pid {holder}")
            try:
                LOCK_PATH.unlink()
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        return
    raise SystemExit("refused: could not acquire instance lock")


def update_lock(**fields: object) -> None:
    info = read_lock() or {}
    info.update(fields)
    LOCK_PATH.write_text(json.dumps(info), encoding="utf-8")


def release_lock_if_ours() -> None:
    info = read_lock()
    if not info:
        return
    if info.get("helper_pid") != os.getpid():
        return
    try:
        LOCK_PATH.unlink()
    except FileNotFoundError:
        pass


def is_shared_write(command: list[str]) -> bool:
    executable = Path(command[0]).name.lower()
    joined = " ".join(command).replace("\\", "/").lower()
    if "upload_data.py" in joined:
        return True
    if executable in {"dbt", "dbt.exe"}:
        return any(part.lower() in WRITE_VERBS for part in command[1:])
    return False


def connect(file_values: dict[str, str]):
    import psycopg2

    missing = [key for key in REQUIRED_ENV if not file_values.get(key) and not os.environ.get(key)]
    if missing:
        return None, missing
    env = child_env(file_values)
    connection = psycopg2.connect(
        host=env["POSTGRES_HOST"],
        port=env["POSTGRES_PORT"],
        dbname=env["POSTGRES_DB"],
        user=env["POSTGRES_USER"],
        password=env["POSTGRES_PASSWORD"],
        connect_timeout=10,
    )
    return connection, []


def doctor() -> int:
    lines: list[str] = []
    ok = True

    if Path(sys.executable).resolve() != VENV_PYTHON.resolve():
        lines.append("interpreter: wrong")
        ok = False
    elif not VENV_PYTHON.is_file():
        lines.append("interpreter: missing")
        ok = False
    else:
        lines.append("interpreter: venv")

    missing_modules = []
    for name in ("pandas", "psycopg2", "sqlalchemy", "dotenv"):
        try:
            __import__(name)
        except ImportError:
            missing_modules.append(name)
    if missing_modules:
        lines.append("modules: missing " + ",".join(missing_modules))
        ok = False
    else:
        lines.append("modules: ok")

    lines.append("dbt_exe: ok" if DBT_EXE.is_file() else "dbt_exe: missing")
    if not DBT_EXE.is_file():
        ok = False

    file_values: dict[str, str] = {}
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        lines.append("env_keys: missing .env")
        ok = False
    else:
        file_values = load_env_file()
        missing_keys = [
            key for key in REQUIRED_ENV if not file_values.get(key) and not os.environ.get(key)
        ]
        if missing_keys:
            lines.append("env_keys: missing " + ",".join(missing_keys))
            ok = False
        else:
            lines.append("env_keys: ok")

    data_dir = REPO_ROOT / "data"
    present_csvs = [name for name in CSV_FILES if (data_dir / name).is_file()]
    lines.append(f"csv_files: {len(present_csvs)}/{len(CSV_FILES)}")
    if len(present_csvs) != len(CSV_FILES):
        ok = False

    if ok:
        try:
            connection, missing = connect(file_values)
            if missing or connection is None:
                lines.append("connected: no")
                ok = False
            else:
                env = child_env(file_values)
                cursor = connection.cursor()
                cursor.execute("SELECT current_database(), version(), current_user")
                current_db, version, _user = cursor.fetchone()
                lines.append("connected: yes")
                lines.append(
                    "database_matches_env: "
                    + ("yes" if current_db == env["POSTGRES_DB"] else "no")
                )
                if current_db != env["POSTGRES_DB"]:
                    ok = False
                lines.append("server_version: " + version.split(",")[0])
                cursor.execute(
                    "SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user"
                )
                can_create = bool(cursor.fetchone()[0])
                lines.append("rolcreatedb: " + ("yes" if can_create else "no"))
                lines.append(
                    "write_isolation: "
                    + ("available" if can_create else "unavailable")
                )
                cursor.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                    """
                )
                tables = {row[0] for row in cursor.fetchall()}
                raw_present = [name for name in RAW_TABLES if name in tables]
                lines.append(f"raw_tables: {len(raw_present)}/{len(RAW_TABLES)}")
                lines.append(
                    "customer_features: "
                    + ("present" if "customer_features" in tables else "absent")
                )
                cursor.close()
                connection.close()
        except Exception as error:
            message = scrub(str(error), secrets_from(file_values))
            lines.append("connected: no")
            lines.append("connect_error: " + message.splitlines()[0])
            ok = False

    info = read_lock()
    holder = lock_holder_alive(info)
    if holder:
        lines.append(f"instance_lock: held pid {holder}")
        lines.append("doctor: busy")
        status = 2
    elif info:
        lines.append("instance_lock: stale")
        lines.append("doctor: ok" if ok else "doctor: fail")
        status = 0 if ok else 1
    else:
        lines.append("instance_lock: clear")
        lines.append("doctor: ok" if ok else "doctor: fail")
        status = 0 if ok else 1

    lines.insert(0, "shared_instance: yes")
    text = "\n".join(lines) + "\n"
    text = scrub(text, secrets_from(file_values))
    target = EVIDENCE_ROOT / "doctor" / "transcript.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    sys.stdout.write(text)
    print(f"evidence: {target.relative_to(REPO_ROOT).as_posix()}")
    return status


def harness_exit(command: list[str], child_exit: int, stdout: str) -> int:
    joined = " ".join(command).replace("\\", "/").lower()
    if "test_connection.py" in joined:
        if child_exit == 0 and "Successfully connected" in stdout:
            return 0
        return 1
    return child_exit


def run(argv: list[str]) -> int:
    if "--" not in argv:
        raise SystemExit(
            "usage: verify_olist.py run --feature <id> [--allow-shared-write] -- <command>"
        )
    split = argv.index("--")
    flags = argv[:split]
    command = argv[split + 1 :]
    feature = None
    allow_write = False
    index = 0
    while index < len(flags):
        flag = flags[index]
        if flag == "--feature" and index + 1 < len(flags):
            feature = flags[index + 1]
            index += 2
        elif flag == "--allow-shared-write":
            allow_write = True
            index += 1
        else:
            raise SystemExit(f"unknown flag: {flag}")
    if not feature or not FEATURE_RE.fullmatch(feature):
        raise SystemExit("feature id must match [a-z0-9-]+")
    if not command:
        raise SystemExit("missing command after --")

    file_values = load_env_file()
    if is_shared_write(command) and not allow_write:
        print(
            "refused: this command replaces objects in the shared public schema, "
            "and the database role cannot CREATE DATABASE. Re-run with "
            "--allow-shared-write only when a warehouse reload is intended."
        )
        return 3

    acquire_lock(feature)
    child_pid = None
    try:
        env = child_env(file_values)
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        child_pid = process.pid
        update_lock(
            child_pid=child_pid,
            child_pid_created=process_create_time(child_pid),
        )
        stdout, stderr = process.communicate()
        child_exit = process.returncode if process.returncode is not None else 1
        secrets = secrets_from(file_values)
        stdout = scrub(stdout or "", secrets)
        stderr = scrub(stderr or "", secrets)
        exit_code = harness_exit(command, child_exit, stdout)
        rendered = "\n".join(
            [
                "command: " + subprocess.list2cmdline(command),
                "cwd: " + str(REPO_ROOT),
                f"child_exit_code: {child_exit}",
                f"harness_exit_code: {exit_code}",
                "--- stdout ---",
                stdout.rstrip("\n"),
                "--- stderr ---",
                stderr.rstrip("\n"),
                "",
            ]
        )
        target = EVIDENCE_ROOT / feature / "transcript.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
        sys.stdout.write(rendered)
        print(f"evidence: {target.relative_to(REPO_ROOT).as_posix()}")
        return exit_code
    finally:
        release_lock_if_ours()


def kill_started(pid: int | None, expected_created: int | None) -> None:
    if not pid or pid == os.getpid():
        return
    actual = process_create_time(pid)
    if actual is None or expected_created is None or actual != expected_created:
        return
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def cleanup() -> int:
    info = read_lock()
    if not info:
        print("cleanup: no instance")
        print(f"evidence_root: {EVIDENCE_ROOT.relative_to(REPO_ROOT).as_posix()}")
        return 0
    kill_started(info.get("child_pid"), info.get("child_pid_created"))
    kill_started(info.get("helper_pid"), info.get("helper_pid_created"))
    try:
        LOCK_PATH.unlink()
        print("cleanup: lock removed")
    except FileNotFoundError:
        print("cleanup: no instance")
    print(f"evidence_root: {EVIDENCE_ROOT.relative_to(REPO_ROOT).as_posix()}")
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in {"doctor", "run", "cleanup"}:
        print(
            "usage: verify_olist.py doctor | cleanup | "
            "run --feature <id> [--allow-shared-write] -- <command>"
        )
        return 2
    action = sys.argv[1]
    if action == "doctor":
        return doctor()
    if action == "cleanup":
        return cleanup()
    return run(sys.argv[2:])


if __name__ == "__main__":
    sys.exit(main())
