import os
import sys
import pandas as pd
from sqlalchemy import text
from upload_data import get_db_engine

def validate_row_counts():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    engine = get_db_engine()

    if not os.path.isdir(data_dir):
        print(f"Directory {data_dir} not found.")
        return False

    csv_files = sorted(f for f in os.listdir(data_dir) if f.endswith('.csv'))

    if not csv_files:
        print(f"No CSV files found in {data_dir}.")
        return False

    print(f"{'Table Name':<25} | {'CSV Rows':<12} | {'DB Rows':<12} | {'Status'}")
    print("-" * 70)

    all_passed = True

    with engine.connect() as conn:
        for file in csv_files:
            file_path = os.path.join(data_dir, file)
            table_name = file.replace('.csv', '').replace("olist_", "").replace("_dataset", "").lower()

            try:
                csv_rows = sum(len(chunk) for chunk in pd.read_csv(file_path, chunksize=10000, low_memory=False))
                query = text(f"SELECT COUNT(*) FROM {table_name}")
                db_rows = conn.execute(query).scalar()

                status = "PASS" if csv_rows == db_rows else "FAIL"
                if status == "FAIL":
                    all_passed = False

                print(f"{table_name:<25} | {csv_rows:<12} | {db_rows:<12} | {status}")

            except Exception as e:
                all_passed = False
                print(f"{table_name:<25} | {'N/A':<12} | {'N/A':<12} | FAIL ({e})")

    return all_passed

if __name__ == "__main__":
    success = validate_row_counts()
    sys.exit(0 if success else 1)
