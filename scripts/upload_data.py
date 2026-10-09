import os
import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
from dataset_manifest import (
    SCHEMAS,
    NUMBERS,
    validate_dataset,
    DatasetValidationError,
    validate_saved_manifest,
)
from arrow_loaders import iter_csv_frames
from dotenv import load_dotenv
from psycopg2 import sql as psql
from psycopg2.extras import execute_values
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

    missing = [
        name
        for name, val in [
            ("POSTGRES_USER", user),
            ("POSTGRES_PASSWORD", password),
            ("POSTGRES_HOST", host),
            ("POSTGRES_DB", db),
        ]
        if not val
    ]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

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


def public_error(exc: Exception) -> str:
    if isinstance(exc, DatasetValidationError):
        return str(exc)
    return f"{type(exc).__name__}: operation failed; check configuration and dataset."


def _insert_page_size(column_count: int) -> int:
    return max(1, 60000 // max(column_count, 1))


def upload_csvs_to_postgres(data_dir: Path | str | None = None) -> int:
    data_dir = Path(data_dir) if data_dir else DATA_DIR

    if not data_dir.is_dir():
        print(
            f"Directory {data_dir} not found. Please ensure your CSVs are in the 'data' folder."
        )
        return 1

    csv_files = sorted(path.name for path in data_dir.glob("*.csv"))
    if not csv_files:
        print("No CSV files found in the data directory.")
        return 1

    try:
        manifest = validate_dataset(data_dir, source={"mode": "upload"})
        validate_saved_manifest(data_dir, manifest)
        csv_files = list(SCHEMAS)
    except Exception as exc:
        print(f" Failed to validate dataset. Error: {public_error(exc)}")
        return 1

    print(f"Found {len(csv_files)} files. Starting upload...\n")
    uploaded = []
    engine = None
    try:
        engine = get_db_engine()
        with engine.begin() as conn:
            cursor = conn.connection.cursor()
            try:
                for file in csv_files:
                    table_name = table_name_for(file)
                    stage_name = "_upload_" + table_name
                    columns = manifest["files"][file]["columns"]
                    cursor.execute(
                        psql.SQL("CREATE TEMP TABLE {} ({}) ON COMMIT DROP").format(
                            psql.Identifier(stage_name),
                            psql.SQL(", ").join(
                                psql.SQL("{} TEXT").format(psql.Identifier(column))
                                for column in columns
                            ),
                        )
                    )
                    count = 0
                    for frame in iter_csv_frames(data_dir / file):
                        statement = psql.SQL("INSERT INTO {} VALUES %s").format(
                            psql.Identifier(stage_name)
                        )
                        rows = [
                            tuple(None if pd.isna(value) else value for value in row)
                            for row in frame.itertuples(index=False, name=None)
                        ]
                        execute_values(
                            cursor,
                            statement,
                            rows,
                            page_size=_insert_page_size(len(columns)),
                        )
                        count += len(frame)
                    with (data_dir / file).open("rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    if digest != manifest["files"][file]["sha256"]:
                        raise ValueError(f"{file}: content changed while loading")
                    if count != manifest["files"][file]["row_count"]:
                        raise ValueError(f"{file}: row count changed while loading")
                    uploaded.append((file, table_name, count))
                for file, table_name, _ in uploaded:
                    target = psql.Identifier(table_name)
                    stage = psql.Identifier("_upload_" + table_name)
                    columns = psql.SQL(", ").join(
                        psql.Identifier(column)
                        for column in manifest["files"][file]["columns"]
                    )
                    cursor.execute(
                        psql.SQL("CREATE TABLE IF NOT EXISTS {} ({})").format(
                            target,
                            psql.SQL(", ").join(
                                psql.SQL("{} {}").format(
                                    psql.Identifier(column),
                                    psql.SQL(
                                        "NUMERIC"
                                        if column in NUMBERS
                                        and not column.endswith("zip_code_prefix")
                                        else "TEXT"
                                    ),
                                )
                                for column in manifest["files"][file]["columns"]
                            ),
                        )
                    )
                    cursor.execute(psql.SQL("DELETE FROM {}").format(target))
                    cursor.execute(
                        "SELECT attname, format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = %s::regclass AND attnum > 0 AND NOT attisdropped",
                        (table_name,),
                    )
                    types = dict(cursor.fetchall())
                    selected = psql.SQL(", ").join(
                        psql.SQL("CAST({} AS {})").format(
                            psql.Identifier(column), psql.SQL(types[column])
                        )
                        for column in manifest["files"][file]["columns"]
                    )
                    cursor.execute(
                        psql.SQL("INSERT INTO {} ({}) SELECT {} FROM {}").format(
                            target, columns, selected, stage
                        )
                    )
            finally:
                cursor.close()
    except Exception as exc:
        print(f" Failed to upload CSV. Error: {public_error(exc)}\n")
        return 1

    finally:
        if engine is not None:
            engine.dispose()

    for file, table_name, row_count in uploaded:
        print(
            f" Successfully uploaded {file} to table '{table_name}' "
            f"({row_count:,} rows).\n"
        )
    return 0


if __name__ == "__main__":
    custom_data_dir = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(upload_csvs_to_postgres(custom_data_dir))
