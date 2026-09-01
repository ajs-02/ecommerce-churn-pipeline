import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

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

def upload_csvs_to_postgres(data_dir: Path | str | None = None):
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    engine = get_db_engine()

    if not data_dir.is_dir():
        print(f"Directory {data_dir} not found. Please ensure your CSVs are in the 'data' folder.")
        return

    csv_files = sorted(f.name for f in data_dir.glob("*.csv"))
    
    if not csv_files:
        print("No CSV files found in the data directory.")
        return

    print(f"Found {len(csv_files)} files. Starting upload...\n")

    for file in csv_files:
        file_path = data_dir / file
        
        # Clean up table name (e.g., 'olist_customers_dataset.csv' -> 'olist_customers_dataset')
        table_name = file.replace('.csv', '').replace("olist_", "").replace("_dataset", "").lower()
        
        print(f"Reading {file}...")
        
        # Chunking is used to prevent memory overload on large files
        chunksize = 10000 
        
        try:
            total_rows = 0
            for chunk_index, chunk in enumerate(
                pd.read_csv(file_path, chunksize=chunksize, low_memory=False)
            ):
                chunk.to_sql(
                    name=table_name,
                    con=engine,
                    if_exists="replace" if chunk_index == 0 else "append",  #idempotent
                    index=False,
                    method="multi",
                )
                total_rows += len(chunk)
            print(f" Successfully uploaded {file} to table '{table_name}' ({total_rows:,} rows).\n")
        except Exception as e:
            print(f" Failed to upload {file}. Error: {e}\n")

if __name__ == "__main__":
    import sys

    custom_data_dir = sys.argv[1] if len(sys.argv) > 1 else None
    upload_csvs_to_postgres(custom_data_dir)