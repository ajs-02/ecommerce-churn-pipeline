import sys
from pathlib import Path

import pandas as pd
from psycopg2 import sql as psql

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from upload_data import DATA_DIR, get_db_engine, table_name_for


def validate_row_counts(data_dir: Path | str | None = None) -> bool:
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    if not data_dir.is_dir():
        print(f"Directory {data_dir} not found.")
        return False

    csv_files = sorted(path.name for path in data_dir.glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {data_dir}.")
        return False

    print(f"{'Table Name':<40} | {'CSV Rows':<12} | {'DB Rows':<12} | {'Status'}")
    print("-" * 80)

    all_passed = True
    engine = get_db_engine()
    with engine.connect() as conn:
        for file in csv_files:
            file_path = data_dir / file
            try:
                table_name = table_name_for(file)
                frame = pd.read_csv(file_path, engine="pyarrow", dtype_backend="pyarrow")
                csv_rows = len(frame)
                cursor = conn.connection.cursor()
                try:
                    cursor.execute(
                        psql.SQL("SELECT COUNT(*) FROM {}").format(psql.Identifier(table_name))
                    )
                    db_rows = cursor.fetchone()[0]
                finally:
                    cursor.close()
                status = "PASS" if csv_rows == db_rows else "FAIL"
                if status == "FAIL":
                    all_passed = False
                print(f"{table_name:<40} | {csv_rows:<12} | {db_rows:<12} | {status}")
            except Exception as exc:
                all_passed = False
                print(f"{file:<40} | {'N/A':<12} | {'N/A':<12} | FAIL ({type(exc).__name__})")

    return all_passed


if __name__ == "__main__":
    custom_data_dir = sys.argv[1] if len(sys.argv) > 1 else None
    success = validate_row_counts(custom_data_dir)
    sys.exit(0 if success else 1)
