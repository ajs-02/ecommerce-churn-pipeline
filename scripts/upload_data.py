import os
import re
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from psycopg2 import sql as psql
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
_TABLE_NAME = re.compile(r"^[a-z][a-z0-9_]*$")

load_dotenv(PROJECT_ROOT / ".env")


def get_db_engine():
    """Creates a SQLAlchemy engine using credentials from .env"""
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB")

    missing = [name for name, val in [
        ("POSTGRES_USER", user),
        ("POSTGRES_PASSWORD", password),
        ("POSTGRES_HOST", host),
        ("POSTGRES_DB", db),
    ] if not val]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    db_url = URL.create(
        drivername="postgresql+psycopg2",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=db,
    )
    return create_engine(db_url)


def table_name_for(filename: str) -> str:
    name = (
        filename.removesuffix(".csv")
        .removeprefix("olist_")
        .removesuffix("_dataset")
        .lower()
    )
    if not _TABLE_NAME.fullmatch(name):
        raise ValueError(f"Refusing table name derived from {filename}")
    return name


def _public_error(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    secret = os.getenv("POSTGRES_PASSWORD")
    if secret:
        message = message.replace(secret, "***")
    return message


def _insert_page_size(column_count: int) -> int:
    return max(1, 60000 // max(column_count, 1))


def _drop_table(conn, table_name: str) -> None:
    raw = conn.connection
    cursor = raw.cursor()
    try:
        cursor.execute(
            psql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(psql.Identifier(table_name))
        )
    finally:
        cursor.close()


def upload_csvs_to_postgres(data_dir: Path | str | None = None) -> int:
    data_dir = Path(data_dir) if data_dir else DATA_DIR

    if not data_dir.is_dir():
        print(f"Directory {data_dir} not found. Please ensure your CSVs are in the 'data' folder.")
        return 1

    csv_files = sorted(path.name for path in data_dir.glob("*.csv"))
    if not csv_files:
        print("No CSV files found in the data directory.")
        return 1

    print(f"Found {len(csv_files)} files. Starting upload...\n")
    frames: list[tuple[str, pd.DataFrame, str]] = []
    try:
        for file in csv_files:
            file_path = data_dir / file
            print(f"Reading {file}...")
            frame = pd.read_csv(file_path, engine="pyarrow", dtype_backend="pyarrow")
            frames.append((table_name_for(file), frame, file))
    except Exception as exc:
        print(f" Failed to read CSV. Error: {_public_error(exc)}\n")
        return 1

    uploaded: list[tuple[str, str, int]] = []
    try:
        engine = get_db_engine()
        with engine.begin() as conn:
            for table_name, frame, file in frames:
                _drop_table(conn, table_name)
                frame.to_sql(
                    name=table_name,
                    con=conn,
                    if_exists="replace",
                    index=False,
                    method="multi",
                    chunksize=_insert_page_size(len(frame.columns)),
                )
                uploaded.append((file, table_name, len(frame)))
    except Exception as exc:
        print(f" Failed to upload CSV. Error: {_public_error(exc)}\n")
        return 1

    for file, table_name, row_count in uploaded:
        print(
            f" Successfully uploaded {file} to table '{table_name}' "
            f"({row_count:,} rows).\n"
        )
    return 0


if __name__ == "__main__":
    custom_data_dir = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(upload_csvs_to_postgres(custom_data_dir))
