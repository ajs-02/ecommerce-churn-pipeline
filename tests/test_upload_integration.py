import os
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import upload_data


@pytest.fixture
def database(monkeypatch):
    if not os.getenv("T02_POSTGRES_PORT"):
        pytest.skip("Set T02_POSTGRES_PORT for disposable PostgreSQL")
    for name, value in {
        "HOST": "127.0.0.1",
        "PORT": os.environ["T02_POSTGRES_PORT"],
        "DB": "postgres",
        "USER": "t02",
        "PASSWORD": "disposable",
    }.items():
        monkeypatch.setenv("POSTGRES_" + name, value)
    engine = upload_data.get_db_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    yield engine
    engine.dispose()


def test_refresh_preserves_table_identity_and_dependent_view(database):
    fixture = ROOT / "tests/fixtures/olist_valid"
    assert upload_data.upload_csvs_to_postgres(fixture) == 0
    with database.begin() as conn:
        conn.execute(
            text("CREATE VIEW customer_stage AS SELECT customer_id FROM customers")
        )
        oid = conn.execute(text("SELECT 'customers'::regclass::oid")).scalar()
    assert upload_data.upload_csvs_to_postgres(fixture) == 0
    with database.connect() as conn:
        assert conn.execute(text("SELECT 'customers'::regclass::oid")).scalar() == oid
        assert conn.execute(text("SELECT count(*) FROM customer_stage")).scalar() == 1


def test_malformed_key_refuses_refresh_and_keeps_previous_dataset(database, tmp_path):
    import shutil

    fixture = ROOT / "tests/fixtures/olist_valid"
    assert upload_data.upload_csvs_to_postgres(fixture) == 0
    shutil.copytree(fixture, tmp_path / "data")
    path = tmp_path / "data/olist_customers_dataset.csv"
    path.write_text(path.read_text().replace("a" * 32, "invalid-key"))
    assert upload_data.upload_csvs_to_postgres(path.parent) == 1
    with database.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM customers")).scalar() == 1


def test_csv_loader_preserves_identifier_nulls_and_bounds_frames(tmp_path):
    from arrow_loaders import iter_csv_frames

    path = tmp_path / "values.csv"
    path.write_text("id,amount\n001,1\n002,\n003,3\n")
    frames = list(iter_csv_frames(path, chunksize=2))
    assert [len(frame) for frame in frames] == [2, 1]
    assert [str(dtype) for frame in frames for dtype in frame.dtypes] == [
        "string",
        "string",
        "string",
        "string",
    ]
    assert frames[0]["id"].tolist() == ["001", "002"]
    assert frames[0]["amount"].isna().tolist() == [False, True]
    assert all(dtype.storage == "pyarrow" for frame in frames for dtype in frame.dtypes)


def test_sql_loader_bounds_frames_and_retains_arrow_types(database):
    from arrow_loaders import iter_sql_frames

    with database.connect() as conn:
        frames = list(
            iter_sql_frames(
                text("SELECT n FROM generate_series(1,3) n"), conn, chunksize=2
            )
        )
    assert [len(frame) for frame in frames] == [2, 1]
    assert [value for frame in frames for value in frame["n"]] == [1, 2, 3]
    assert all(str(frame["n"].dtype) == "int64[pyarrow]" for frame in frames)


def test_upload_preserves_source_leading_zero_zip(database):
    assert upload_data.upload_csvs_to_postgres(ROOT / "tests/fixtures/olist_valid") == 0
    with database.connect() as conn:
        assert (
            conn.execute(
                text("SELECT customer_zip_code_prefix FROM customers")
            ).scalar()
            == "01234"
        )


def test_stale_manifest_refuses_refresh(database, tmp_path):
    import shutil, json
    from dataset_manifest import validate_dataset

    data = tmp_path / "data"
    shutil.copytree(ROOT / "tests/fixtures/olist_valid", data)
    manifest = validate_dataset(data, source={"mode": "existing"})
    (data / "dataset_manifest.json").write_text(json.dumps(manifest))
    path = data / "olist_customers_dataset.csv"
    path.write_text(path.read_text().replace("sao paulo", "campinas"))
    assert upload_data.upload_csvs_to_postgres(data) == 1


def test_refresh_preserves_compatible_existing_numeric_columns(database):
    with database.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE customers (customer_state text, customer_city text, customer_zip_code_prefix bigint, customer_unique_id text, customer_id text)"
            )
        )
        conn.execute(
            text(
                "CREATE VIEW customer_stage AS SELECT customer_zip_code_prefix FROM customers"
            )
        )
    assert upload_data.upload_csvs_to_postgres(ROOT / "tests/fixtures/olist_valid") == 0
    with database.connect() as conn:
        assert (
            conn.execute(
                text("SELECT customer_zip_code_prefix FROM customer_stage")
            ).scalar()
            == 1234
        )
        assert (
            conn.execute(text("SELECT customer_state FROM customers")).scalar() == "SP"
        )


def test_validation_connection_failure_returns_false_without_secrets(
    tmp_path, monkeypatch, capsys
):
    import shutil
    import validate_upload

    data = tmp_path / "data"
    shutil.copytree(ROOT / "tests/fixtures/olist_valid", data)
    for name, value in {
        "HOST": "127.0.0.1",
        "PORT": "1",
        "DB": "unused",
        "USER": "unused",
        "PASSWORD": "do-not-print",
    }.items():
        monkeypatch.setenv("POSTGRES_" + name, value)
    assert validate_upload.validate_row_counts(data) is False
    output = capsys.readouterr().out
    assert "do-not-print" not in output
    assert "FAIL" in output


def snapshot(engine):
    import json
    from dataset_manifest import SCHEMAS

    hashes = {}
    tables = {}
    with engine.connect() as conn:
        for file in SCHEMAS:
            table = upload_data.table_name_for(file)
            hashes[table] = conn.execute(
                text(
                    "SELECT md5(string_agg(row_to_json(t)::text, chr(10) ORDER BY row_to_json(t)::text)) FROM "
                    + table
                    + " t"
                )
            ).scalar()
            tables[table] = {
                "count": conn.execute(text("SELECT count(*) FROM " + table)).scalar(),
                "oid": conn.execute(
                    text("SELECT CAST(:table AS regclass)::oid"), {"table": table}
                ).scalar(),
                "content_md5": hashes[table],
            }
    if os.getenv("T02_EVIDENCE_DIR"):
        path = Path(os.environ["T02_EVIDENCE_DIR"]) / "database_snapshots.json"
        records = json.loads(path.read_text()) if path.exists() else []
        records.append({"test": os.getenv("PYTEST_CURRENT_TEST"), "tables": tables})
        path.write_text(json.dumps(records, indent=2))
    return hashes


def test_publication_failure_rolls_back_every_table_and_redacts_database_detail(
    database, tmp_path, capsys
):
    import shutil

    fixture = ROOT / "tests/fixtures/olist_valid"
    assert upload_data.upload_csvs_to_postgres(fixture) == 0
    before = snapshot(database)
    with database.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION reject_refresh() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'postgresql://other:unrelated-secret@host/db'; END $$"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER reject_refresh BEFORE INSERT ON sellers FOR EACH ROW EXECUTE FUNCTION reject_refresh()"
            )
        )
        conn.execute(
            text("CREATE VIEW customer_stage AS SELECT customer_city FROM customers")
        )
    data = tmp_path / "data"
    shutil.copytree(fixture, data)
    path = data / "olist_customers_dataset.csv"
    path.write_text(path.read_text().replace("sao paulo", "campinas"))
    assert upload_data.upload_csvs_to_postgres(data) == 1
    assert snapshot(database) == before
    with database.connect() as conn:
        assert (
            conn.execute(text("SELECT customer_city FROM customer_stage")).scalar()
            == "sao paulo"
        )
    output = capsys.readouterr().out
    assert "unrelated-secret" not in output
    assert "postgresql://" not in output


def test_later_stage_batch_failure_keeps_previous_dataset(database, tmp_path):
    import shutil

    fixture = ROOT / "tests/fixtures/olist_valid"
    assert upload_data.upload_csvs_to_postgres(fixture) == 0
    before = snapshot(database)
    with database.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION reject_batch() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.geolocation_city = 'reject-later-batch' THEN RAISE EXCEPTION 'injected later batch failure'; END IF; RETURN NEW; END $$"
            )
        )
        conn.execute(
            text(
                """CREATE FUNCTION install_batch_fault() RETURNS event_trigger LANGUAGE plpgsql AS $$
        DECLARE command record;
        BEGIN
          FOR command IN SELECT * FROM pg_event_trigger_ddl_commands() LOOP
            IF command.command_tag = 'CREATE TABLE' AND EXISTS
              (SELECT 1 FROM pg_attribute a JOIN pg_class c ON c.oid=a.attrelid
               WHERE a.attrelid=command.objid AND c.relpersistence='t' AND a.attname='geolocation_city') THEN
              EXECUTE format('CREATE TRIGGER batch_fault BEFORE INSERT ON %s FOR EACH ROW EXECUTE FUNCTION reject_batch()', command.object_identity);
            END IF;
          END LOOP;
        END $$"""
            )
        )
        conn.execute(
            text(
                "CREATE EVENT TRIGGER batch_fault_installer ON ddl_command_end EXECUTE FUNCTION install_batch_fault()"
            )
        )
    data = tmp_path / "data"
    shutil.copytree(fixture, data)
    path = data / "olist_geolocation_dataset.csv"
    header, row = path.read_text().splitlines()
    path.write_text(
        header
        + "\n"
        + (row + "\n") * 50000
        + row.replace("sao paulo", "reject-later-batch")
        + "\n"
    )
    try:
        assert upload_data.upload_csvs_to_postgres(data) == 1
        assert snapshot(database) == before
    finally:
        with database.begin() as conn:
            conn.execute(text("DROP EVENT TRIGGER batch_fault_installer"))


def test_upload_and_validation_cli_fail_truthfully_without_connection_urls(tmp_path):
    import subprocess, shutil

    data = tmp_path / "data"
    shutil.copytree(ROOT / "tests/fixtures/olist_valid", data)
    env = os.environ.copy()
    for name, value in {
        "HOST": "127.0.0.1",
        "PORT": "1",
        "DB": "unused",
        "USER": "unused",
        "PASSWORD": "do-not-print",
    }.items():
        env["POSTGRES_" + name] = value
    for script in ["upload_data.py", "validate_upload.py", "test_connection.py"]:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), str(data)],
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "do-not-print" not in result.stdout + result.stderr
        assert "postgresql://" not in result.stdout + result.stderr
        assert "Traceback" not in result.stdout + result.stderr


def test_successful_changed_refresh_is_repeatable_and_validation_detects_mismatch(
    database, tmp_path
):
    import shutil
    import validate_upload

    fixture = ROOT / "tests/fixtures/olist_valid"
    assert upload_data.upload_csvs_to_postgres(fixture) == 0
    before = snapshot(database)
    data = tmp_path / "data"
    shutil.copytree(fixture, data)
    path = data / "olist_customers_dataset.csv"
    path.write_text(path.read_text().replace("sao paulo", "campinas"))
    assert upload_data.upload_csvs_to_postgres(data) == 0
    after = snapshot(database)
    assert after["customers"] != before["customers"]
    assert upload_data.upload_csvs_to_postgres(data) == 0
    assert snapshot(database) == after
    assert validate_upload.validate_row_counts(data) is True
    with database.begin() as conn:
        conn.execute(text("DELETE FROM customers"))
    assert validate_upload.validate_row_counts(data) is False


def test_csv_loader_only_treats_empty_fields_as_null(tmp_path):
    from arrow_loaders import iter_csv_frames

    path = tmp_path / "values.csv"
    path.write_text("title,amount\nNA,\nNULL,0\n")
    frame = next(iter_csv_frames(path))
    assert frame["title"].tolist() == ["NA", "NULL"]
    assert frame["amount"].isna().tolist() == [True, False]


def test_validation_refuses_stale_manifest(database, tmp_path):
    import shutil, json
    import validate_upload
    from dataset_manifest import validate_dataset

    fixture = ROOT / "tests/fixtures/olist_valid"
    assert upload_data.upload_csvs_to_postgres(fixture) == 0
    data = tmp_path / "data"
    shutil.copytree(fixture, data)
    (data / "dataset_manifest.json").write_text(
        json.dumps(validate_dataset(data, source={"mode": "existing"}))
    )
    path = data / "olist_customers_dataset.csv"
    path.write_text(path.read_text().replace("sao paulo", "campinas"))
    assert validate_upload.validate_row_counts(data) is False


def test_new_raw_payment_table_supports_existing_numeric_aggregation(database):
    assert upload_data.upload_csvs_to_postgres(ROOT / "tests/fixtures/olist_valid") == 0
    with database.connect() as conn:
        assert (
            conn.execute(text("SELECT sum(payment_value) FROM order_payments")).scalar()
            == 12
        )


def test_nullable_all_null_money_columns_remain_numeric_across_refresh(
    database, tmp_path
):
    import shutil, csv

    data = tmp_path / "data"
    shutil.copytree(ROOT / "tests/fixtures/olist_valid", data)
    for filename, fields in [
        ("olist_order_items_dataset.csv", ["price", "freight_value"]),
        ("olist_order_payments_dataset.csv", ["payment_value"]),
    ]:
        path = data / filename
        rows = list(csv.reader(path.read_text().splitlines()))
        for field in fields:
            rows[1][rows[0].index(field)] = ""
        with path.open("w", newline="") as stream:
            csv.writer(stream).writerows(rows)
    assert upload_data.upload_csvs_to_postgres(data) == 0
    with database.connect() as conn:
        assert (
            conn.execute(text("SELECT sum(payment_value) FROM order_payments")).scalar()
            is None
        )
        assert conn.execute(
            text("SELECT price,freight_value FROM order_items")
        ).one() == (None, None)
        assert (
            conn.execute(text("SELECT avg(review_score) FROM order_reviews")).scalar()
            == 5
        )
    assert upload_data.upload_csvs_to_postgres(ROOT / "tests/fixtures/olist_valid") == 0
    with database.connect() as conn:
        assert (
            conn.execute(text("SELECT sum(payment_value) FROM order_payments")).scalar()
            == 12
        )
        assert (
            conn.execute(
                text("SELECT sum(price + freight_value) FROM order_items")
            ).scalar()
            == 12
        )


def test_current_dbt_payment_view_survives_success_rerun_and_rollback(
    database, tmp_path
):
    import shutil

    fixture = ROOT / "tests/fixtures/olist_valid"
    assert upload_data.upload_csvs_to_postgres(fixture) == 0
    model = (
        ROOT / "ecommerce_transform/models/staging/stg_order_payments.sql"
    ).read_text()
    model = model.replace("{{ source('olist', 'order_payments') }}", "order_payments")
    with database.begin() as conn:
        conn.execute(text("CREATE VIEW payment_stage AS " + model))
        oid = conn.execute(text("SELECT 'payment_stage'::regclass::oid")).scalar()
        assert (
            conn.execute(text("SELECT total_payment_value FROM payment_stage")).scalar()
            == 12
        )
    data = tmp_path / "data"
    shutil.copytree(fixture, data)
    path = data / "olist_order_payments_dataset.csv"
    path.write_text(path.read_text().replace("12.00", "17.00"))
    for _ in range(2):
        assert upload_data.upload_csvs_to_postgres(data) == 0
        with database.connect() as conn:
            assert (
                conn.execute(
                    text("SELECT total_payment_value FROM payment_stage")
                ).scalar()
                == 17
            )
            assert (
                conn.execute(text("SELECT 'payment_stage'::regclass::oid")).scalar()
                == oid
            )
    with database.begin() as conn:
        conn.execute(
            text(
                "CREATE FUNCTION reject_publication() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected publication failure'; END $$"
            )
        )
        conn.execute(
            text(
                "CREATE TRIGGER reject_publication BEFORE INSERT ON sellers FOR EACH ROW EXECUTE FUNCTION reject_publication()"
            )
        )
    assert upload_data.upload_csvs_to_postgres(fixture) == 1
    with database.connect() as conn:
        assert (
            conn.execute(text("SELECT total_payment_value FROM payment_stage")).scalar()
            == 17
        )
        assert (
            conn.execute(text("SELECT 'payment_stage'::regclass::oid")).scalar() == oid
        )

    if os.getenv("T02_EVIDENCE_DIR"):
        import json

        with database.connect() as conn:
            record = {
                "model_path": "ecommerce_transform/models/staging/stg_order_payments.sql",
                "substitution": "source('olist', 'order_payments') -> order_payments",
                "original_view_oid": oid,
                "final_view_oid": conn.execute(
                    text("SELECT 'payment_stage'::regclass::oid")
                ).scalar(),
                "final_preserved_total": str(
                    conn.execute(
                        text("SELECT total_payment_value FROM payment_stage")
                    ).scalar()
                ),
                "expected_initial_changed_rerun_rollback_totals": [12, 17, 17, 17],
                "executed_sql": model,
            }
        (Path(os.environ["T02_EVIDENCE_DIR"]) / "dbt_payment_view.json").write_text(
            json.dumps(record, indent=2)
        )
