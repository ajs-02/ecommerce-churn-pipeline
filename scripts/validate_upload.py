"""Validate required dataset fingerprints and published row counts."""

import sys
from pathlib import Path
from psycopg2 import sql as psql
from dataset_manifest import validate_dataset, validate_saved_manifest
from upload_data import DATA_DIR, get_db_engine, table_name_for, public_error


def validate_row_counts(data_dir: Path | str | None = None) -> bool:
    data_dir = Path(data_dir) if data_dir else DATA_DIR
    engine = None
    try:
        manifest = validate_dataset(data_dir, source={"mode": "validation"})
        validate_saved_manifest(data_dir, manifest)
        engine = get_db_engine()
        all_passed = True
        with engine.connect() as conn:
            cursor = conn.connection.cursor()
            try:
                for file, metadata in manifest["files"].items():
                    table_name = table_name_for(file)
                    cursor.execute(
                        psql.SQL("SELECT COUNT(*) FROM {}").format(
                            psql.Identifier(table_name)
                        )
                    )
                    actual = cursor.fetchone()[0]
                    expected = metadata["row_count"]
                    passed = actual == expected
                    all_passed &= passed
                    print(
                        f"{table_name}: CSV {expected}; DB {actual}; {'PASS' if passed else 'FAIL'}"
                    )
            finally:
                cursor.close()
        return all_passed
    except Exception as exc:
        print(f"FAIL validation: {public_error(exc)}")
        return False
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    sys.exit(
        0 if validate_row_counts(sys.argv[1] if len(sys.argv) > 1 else None) else 1
    )
