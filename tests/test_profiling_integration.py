import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import upload_data


@pytest.fixture
def profile_database(monkeypatch):
    port = os.getenv("T05_POSTGRES_PORT")
    if not port:
        pytest.skip("Set T05_POSTGRES_PORT for disposable PostgreSQL")
    admin = create_engine(
        f"postgresql+psycopg2://t02@127.0.0.1:{port}/postgres",
        isolation_level="AUTOCOMMIT",
    )
    with admin.connect() as conn:
        if not conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname='t05profiles'")
        ).scalar():
            conn.execute(text("CREATE DATABASE t05profiles"))
    admin.dispose()
    for key, value in {
        "HOST": "127.0.0.1",
        "PORT": port,
        "DB": "t05profiles",
        "USER": "t02",
        "PASSWORD": "disposable-secret",
    }.items():
        monkeypatch.setenv("POSTGRES_" + key, value)
    engine = upload_data.get_db_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    assert upload_data.upload_csvs_to_postgres(ROOT / "tests/fixtures/olist_valid") == 0
    yield engine
    engine.dispose()


def profile_cli(path):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/generate_data_profile.py"),
            "--output-dir",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_absent_mart_cli_requests_dbt_without_secrets(profile_database, tmp_path):
    result = profile_cli(tmp_path / "reports")
    assert result.returncode != 0
    assert "run dbt first" in result.stdout + result.stderr
    assert "disposable-secret" not in result.stdout + result.stderr
    assert "postgresql://" not in result.stdout + result.stderr


def build_mart():
    result = subprocess.run(
        [
            str(Path(sys.executable).with_name("dbt.exe")),
            "run",
            "--target-path",
            str(ROOT / "artifacts/t05-dbt-target"),
            "--log-path",
            str(ROOT / "artifacts/t05-dbt-logs"),
            "--select",
            "+customer_features",
            "--project-dir",
            str(ROOT / "ecommerce_transform"),
            "--profiles-dir",
            str(ROOT / "ecommerce_transform"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_profiles_publish_real_table_reports_and_exact_fixture_summary(
    profile_database, tmp_path
):
    build_mart()
    result = profile_cli(tmp_path / "reports")
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((tmp_path / "reports/summary.json").read_text())
    assert summary["census"]["populations"]["eligible"] == {
        "total": 1,
        "positive": 0,
        "mature_positive": 0,
        "early_positive": 0,
        "negative": 0,
        "uncertain": 1,
    }
    assert summary["census"]["excluded"] == 0
    assert summary["tables"]["customer_features"]["rows"] == 1
    spend = summary["tables"]["customer_features"]["columns"]["total_spent"]
    assert (
        spend["missing"] == 0
        and spend["zero"] == 0
        and spend["negative"] == 0
        and spend["min"] == 12
        and spend["max"] == 12
    )
    assert (
        summary["tables"]["order_reviews"]["columns"]["review_comment_title"]["missing"]
        == 1
    )
    assert (
        summary["tables"]["customers"]["columns"]["customer_zip_code_prefix"]["dtype"]
        == "string[pyarrow]"
    )
    index = (tmp_path / "reports/data_profile_report.html").read_text(encoding="utf-8")
    tables = {
        "customers",
        "geolocation",
        "orders",
        "order_items",
        "order_payments",
        "order_reviews",
        "products",
        "sellers",
        "product_category_name_translation",
        "customer_features",
    }
    assert set(summary["tables"]) == tables
    for table in tables:
        assert f"profiles/{table}.html" in index
        report = (tmp_path / "reports/profiles" / f"{table}.html").read_text(
            encoding="utf-8"
        )
        assert "ydata" in report.lower() and len(report) > 1000
    assert (
        "early" in index.lower()
        and "uncertain" in index.lower()
        and "exclusion" in index.lower()
    )
    assert "disposable-secret" not in index


def test_cohort_charts_use_literal_labels_denominators_and_predictor_allowlist(
    profile_database, tmp_path
):
    from test_features_integration import add_order

    with profile_database.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM order_reviews; DELETE FROM order_payments; DELETE FROM order_items; DELETE FROM orders; DELETE FROM customers"
            )
        )
        cases = [
            (1, "SP", "2018-01-01", 12),
            (2, "SP", "2018-01-01", 22),
            (3, "RJ", "2018-08-01", 32),
            (4, "RJ", "2018-08-01", 42),
            (5, "MG", "2018-01-01", 52),
            (6, "BA", "2018-01-01", 62),
            (7, "PR", "2018-01-01", 0),
            (8, "AM", "2018-08-01", 82),
            (9, "SC", "2018-01-01", 92),
        ]
        for person, state, purchase, spend in cases:
            oid = add_order(
                conn, person, person, purchase, state=state, complete=person != 9
            )
            conn.execute(
                text(
                    "UPDATE order_payments SET payment_value=:amount WHERE order_id=:oid"
                ),
                {"amount": spend, "oid": oid},
            )
        add_order(conn, 20, 2, "2018-02-01")
        add_order(conn, 21, 3, "2018-08-02", "canceled")
        last = add_order(conn, 22, 22, "2018-09-01", "canceled")
        conn.execute(
            text(
                "INSERT INTO order_reviews VALUES (:rid,:oid,5,NULL,NULL,'2018-09-01','2018-09-02')"
            ),
            {"rid": "f" * 32, "oid": last},
        )
    build_mart()
    result = profile_cli(tmp_path / "reports")
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((tmp_path / "reports/summary.json").read_text())
    eda = summary["eda"]
    assert eda["target_distribution"] == {"0": 4, "1": 2, "uncertain": 2}
    assert eda["labeled_denominator"] == 6 and eda["repeat_rate"] == pytest.approx(
        1 / 3
    )
    assert eda["early_positive"] == 1
    assert eda["delivered_count_distribution"] == {"1": 7, "2": 1}
    assert (
        eda["spend_by_target"]["0"]["count"] == 4
        and eda["spend_by_target"]["0"]["mean"] == 31.5
    )
    assert (
        eda["spend_by_target"]["1"]["count"] == 2
        and eda["spend_by_target"]["1"]["mean"] == 27
    )
    assert (
        eda["uncertain"]["count"] == 2
        and eda["uncertain"]["mean_first_order_spend"] == 62
    )
    assert eda["top_five_states"] == [
        {"state": "SP", "labeled": 2, "positive": 1, "repeat_rate": 0.5},
        {"state": "BA", "labeled": 1, "positive": 0, "repeat_rate": 0},
        {"state": "MG", "labeled": 1, "positive": 0, "repeat_rate": 0},
        {"state": "PR", "labeled": 1, "positive": 0, "repeat_rate": 0},
        {"state": "RJ", "labeled": 1, "positive": 1, "repeat_rate": 1},
    ]
    assert eda["correlation_columns"] == [
        "total_spent",
        "seconds_since_first_purchase",
        "item_count",
        "freight_value",
        "delivery_seconds",
        "approval_seconds",
        "carrier_seconds",
        "after_estimated_delivery_seconds",
    ]
    assert summary["census"]["exclusion_reasons"] == {"missing_approval_timestamp": 1}
    assert summary["census"]["retained_warning_reasons"]["zero_order_spend"] == 1
    assert (
        summary["tables"]["customer_features"]["profile_statistics"]["total_spent"][
            "zero"
        ]
        == 1
    )
    assert (
        summary["tables"]["order_reviews"]["profile_statistics"]["review_score"][
            "missing"
        ]
        == 0
    )
    for name in [
        "delivered_counts",
        "target_distribution",
        "spend_by_target",
        "state_repeat_rates",
        "numeric_correlations",
        "uncertain_spend",
    ]:
        assert (
            (tmp_path / "reports/plots" / f"{name}.png")
            .read_bytes()
            .startswith(b"\x89PNG")
        )
        assert f"plots/{name}.png" in (
            tmp_path / "reports/data_profile_report.html"
        ).read_text(encoding="utf-8")


def execute_notebook(output):
    environment = os.environ.copy()
    environment["OLIST_EDA_OUTPUT_DIR"] = str(output / "reports")
    environment["PATH"] = (
        str(Path(sys.executable).parent) + os.pathsep + environment["PATH"]
    )
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "nbconvert",
            "--execute",
            "--to",
            "notebook",
            "--ExecutePreprocessor.kernel_name=python3",
            "--ExecutePreprocessor.timeout=120",
            "--output",
            "executed.ipynb",
            "--output-dir",
            str(output),
            str(ROOT / "notebooks/01_eda_and_profiling.ipynb"),
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_absent_mart_notebook_requests_dbt_without_secrets(profile_database, tmp_path):
    result = execute_notebook(tmp_path)
    assert result.returncode != 0
    assert "run dbt first" in result.stdout + result.stderr
    assert "disposable-secret" not in result.stdout + result.stderr
    assert "postgresql://" not in result.stdout + result.stderr


def test_notebook_executes_shared_analysis_and_six_visible_plots(
    profile_database, tmp_path
):
    import nbformat

    build_mart()
    result = execute_notebook(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    notebook = nbformat.read(tmp_path / "executed.ipynb", as_version=4)
    outputs = [
        output
        for cell in notebook.cells
        if cell.cell_type == "code"
        for output in cell.outputs
    ]
    assert sum("image/png" in output.get("data", {}) for output in outputs) == 6
    text_output = "".join(output.get("text", "") for output in outputs)
    assert '"uncertain": 1' in text_output
    assert "disposable-secret" not in text_output and "postgresql://" not in text_output
    summary = json.loads((tmp_path / "reports/eda_summary.json").read_text())
    assert (
        summary["eda"]["labeled_denominator"] == 0
        and summary["eda"]["repeat_rate"] is None
    )
    assert summary["eda"]["uncertain"]["count"] == 1
    source = nbformat.read(ROOT / "notebooks/01_eda_and_profiling.ipynb", as_version=4)
    assert all(not cell.get("outputs") for cell in source.cells)


def test_profile_write_failure_preserves_previous_complete_reports(
    profile_database, tmp_path, monkeypatch
):
    import hashlib
    from profiling_analysis import generate_profiles
    from ydata_profiling import ProfileReport

    build_mart()
    output = tmp_path / "reports"
    generate_profiles(output)
    before = {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in output.rglob("*")
        if path.is_file()
    }
    with profile_database.begin() as conn:
        conn.execute(text("UPDATE customers SET customer_state='RJ'"))
    build_mart()
    original = ProfileReport.to_file
    calls = 0

    def fail_later(report, path, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Injected report write failure")
        return original(report, path, *args, **kwargs)

    monkeypatch.setattr(ProfileReport, "to_file", fail_later)
    with pytest.raises(OSError):
        generate_profiles(output)
    after = {
        str(path.relative_to(output)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in output.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_empty_raw_table_fails_truthfully_instead_of_publishing_fake_profile(
    profile_database, tmp_path
):
    build_mart()
    with profile_database.begin() as conn:
        conn.execute(text("DELETE FROM order_reviews"))
    result = profile_cli(tmp_path / "reports")
    assert result.returncode != 0
    assert "empty table order_reviews" in result.stdout
    assert not (tmp_path / "reports/data_profile_report.html").exists()


def test_successful_profile_rerun_preserves_artifacts_owned_by_other_commands(
    profile_database, tmp_path
):
    build_mart()
    output = tmp_path / "reports"
    first = profile_cli(output)
    assert first.returncode == 0, first.stdout + first.stderr
    unrelated = {
        "feature_diagnostics/census.json": b'{"eligible": 1}',
        "eda/eda_summary.json": b'{"uncertain": 1}',
        "01_eda_executed.ipynb": b'{"cells": []}',
        "notes.txt": b"Keep reviewed notes",
        "plots/manual_plot.txt": b"Other chart evidence",
        "profiles/manual.html": b"Other profile evidence",
    }
    for relative, content in unrelated.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    second = profile_cli(output)
    assert second.returncode == 0, second.stdout + second.stderr
    for relative, content in unrelated.items():
        assert (output / relative).read_bytes() == content
