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
def staging(monkeypatch):
    port = os.getenv("T03_POSTGRES_PORT")
    if not port:
        pytest.skip("Set T03_POSTGRES_PORT for disposable PostgreSQL")
    for key, value in {
        "HOST": "127.0.0.1",
        "PORT": port,
        "DB": "postgres",
        "USER": "t02",
        "PASSWORD": "disposable",
    }.items():
        monkeypatch.setenv("POSTGRES_" + key, value)
    engine = upload_data.get_db_engine()
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    assert upload_data.upload_csvs_to_postgres(ROOT / "tests/fixtures/olist_valid") == 0
    yield engine
    engine.dispose()


def dbt(*args):
    if args[0] == "test":
        args = (*args, "--indirect-selection", "cautious")
    result = subprocess.run(
        [
            str(Path(sys.executable).with_name("dbt.exe")),
            *args,
            "--project-dir",
            str(ROOT / "ecommerce_transform"),
            "--profiles-dir",
            str(ROOT / "ecommerce_transform"),
        ],
        capture_output=True,
        text=True,
    )
    evidence = os.getenv("T03_EVIDENCE_DIR")
    if evidence:
        path = Path(evidence)
        path.mkdir(parents=True, exist_ok=True)
        with (path / "dbt_commands.log").open("a", encoding="utf-8") as stream:
            stream.write(
                "\nCOMMAND: dbt "
                + " ".join(args)
                + "\nEXIT: "
                + str(result.returncode)
                + "\n"
                + result.stdout
                + result.stderr
            )
    return result


def build():
    result = dbt("run", "--select", "path:models/staging")
    assert result.returncode == 0, result.stdout + result.stderr


def test_split_tender_uses_summed_type_values(staging):
    with staging.begin() as conn:
        conn.execute(text("DELETE FROM order_payments"))
        conn.execute(
            text(
                "INSERT INTO order_payments VALUES (:order,1,'voucher',1,30),(:order,2,'voucher',1,30),(:order,3,'credit_card',1,50)"
            ),
            {"order": "c" * 32},
        )
    build()
    with staging.connect() as conn:
        assert conn.execute(
            text(
                "SELECT total_payment_value, favorite_payment_type, used_voucher, payment_row_count FROM stg_order_payments"
            )
        ).one() == (110, "voucher", True, 3)


def test_payment_tie_is_alphabetical_and_source_order_independent(staging):
    with staging.begin() as conn:
        conn.execute(text("DELETE FROM order_payments"))
        conn.execute(
            text(
                "INSERT INTO order_payments VALUES (:order,1,'voucher',1,60),(:order,2,'credit_card',1,60)"
            ),
            {"order": "c" * 32},
        )
    build()
    with staging.connect() as conn:
        assert conn.execute(
            text(
                "SELECT total_payment_value, favorite_payment_type FROM stg_order_payments"
            )
        ).one() == (120, "credit_card")
    with staging.begin() as conn:
        conn.execute(
            text("UPDATE order_payments SET payment_sequential = 3-payment_sequential")
        )
    with staging.connect() as conn:
        assert conn.execute(
            text(
                "SELECT total_payment_value, favorite_payment_type FROM stg_order_payments"
            )
        ).one() == (120, "credit_card")


def test_required_staging_column_types_and_grains(staging):
    with staging.begin() as conn:
        conn.execute(
            text(
                "ALTER TABLE products ALTER COLUMN product_weight_g TYPE text, ALTER COLUMN product_length_cm TYPE text, ALTER COLUMN product_height_cm TYPE text, ALTER COLUMN product_width_cm TYPE text"
            )
        )
    build()
    expected = {
        "stg_customers": [
            ("customer_id", "text"),
            ("customer_unique_id", "text"),
            ("customer_zip_code_prefix", "integer"),
            ("customer_city", "text"),
            ("customer_state", "text"),
        ],
        "stg_orders": [
            ("order_id", "text"),
            ("customer_id", "text"),
            ("order_status", "text"),
            ("order_purchase_ts", "timestamp without time zone"),
            ("order_approved_ts", "timestamp without time zone"),
            ("order_delivered_carrier_ts", "timestamp without time zone"),
            ("order_delivered_customer_ts", "timestamp without time zone"),
            ("order_estimated_delivery_ts", "timestamp without time zone"),
        ],
        "stg_order_items": [
            ("order_id", "text"),
            ("order_item_id", "integer"),
            ("product_id", "text"),
            ("seller_id", "text"),
            ("shipping_limit_ts", "timestamp without time zone"),
            ("item_price", "numeric"),
            ("freight_value", "numeric"),
        ],
        "stg_order_payments": [
            ("order_id", "text"),
            ("total_payment_value", "numeric"),
            ("max_installments", "integer"),
            ("payment_row_count", "bigint"),
            ("used_voucher", "boolean"),
            ("favorite_payment_type", "text"),
        ],
        "stg_order_reviews": [
            ("review_id", "text"),
            ("order_id", "text"),
            ("review_score", "integer"),
            ("review_comment_title", "text"),
            ("review_comment_message", "text"),
            ("review_creation_ts", "timestamp without time zone"),
            ("review_answer_ts", "timestamp without time zone"),
        ],
        "stg_products": [
            ("product_id", "text"),
            ("product_category_name", "text"),
            ("category_english", "text"),
            ("product_weight_g", "numeric"),
            ("product_length_cm", "numeric"),
            ("product_height_cm", "numeric"),
            ("product_width_cm", "numeric"),
        ],
    }
    with staging.connect() as conn:
        for relation, columns in expected.items():
            actual = conn.execute(
                text(
                    "SELECT column_name,data_type FROM information_schema.columns WHERE table_schema='public' AND table_name=:relation ORDER BY ordinal_position"
                ),
                {"relation": relation},
            ).all()
            assert actual == columns


def test_negative_payment_cannot_hide_inside_positive_aggregate(staging):
    with staging.begin() as conn:
        conn.execute(text("UPDATE order_payments SET payment_value=-1"))
        conn.execute(
            text("INSERT INTO order_payments VALUES (:order,2,'voucher',1,20)"),
            {"order": "c" * 32},
        )
    build()
    result = dbt("test", "--select", "assert_nonnegative_raw_payments")
    assert result.returncode != 0, result.stdout + result.stderr


def test_staging_accepts_all_statuses_zeros_and_review_dedup(staging):
    with staging.begin() as conn:
        for index, status in enumerate(
            [
                "delivered",
                "shipped",
                "canceled",
                "unavailable",
                "invoiced",
                "processing",
                "created",
                "approved",
            ],
            1,
        ):
            conn.execute(
                text(
                    "INSERT INTO orders SELECT :id,customer_id,:status,order_purchase_timestamp,order_approved_at,order_delivered_carrier_date,order_delivered_customer_date,order_estimated_delivery_date FROM orders LIMIT 1"
                ),
                {"id": f"{index:032x}", "status": status},
            )
        conn.execute(text("UPDATE order_items SET price=0,freight_value=0"))
        conn.execute(text("UPDATE order_payments SET payment_value=0"))
        conn.execute(
            text(
                "INSERT INTO order_reviews SELECT review_id,:id,1,'earliest','kept','2017-01-01','2017-01-02' FROM order_reviews LIMIT 1"
            ),
            {"id": f"{2:032x}"},
        )
        conn.execute(
            text(
                "INSERT INTO order_reviews SELECT review_id,:id,2,'tie','lost','2017-01-01','2017-01-02' FROM order_reviews LIMIT 1"
            ),
            {"id": f"{3:032x}"},
        )
    build()
    with staging.connect() as conn:
        assert conn.execute(
            text(
                "SELECT order_id,review_score,review_comment_title FROM stg_order_reviews"
            )
        ).one() == (f"{2:032x}", 1, "earliest")
        assert conn.execute(
            text("SELECT item_price,freight_value FROM stg_order_items")
        ).one() == (0, 0)
    result = dbt("test", "--select", "path:models/staging", "tag:staging")
    assert result.returncode == 0, result.stdout + result.stderr
    result = dbt("docs", "generate")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (ROOT / "ecommerce_transform/target/catalog.json").exists()


@pytest.mark.parametrize(
    "mutation,selector",
    [
        ("INSERT INTO customers SELECT * FROM customers", "stg_customers"),
        ("UPDATE customers SET customer_id=NULL", "stg_customers"),
        ("UPDATE orders SET customer_id='orphan'", "stg_orders"),
        ("UPDATE orders SET order_status='unknown'", "stg_orders"),
        ("UPDATE orders SET order_purchase_timestamp=NULL", "stg_orders"),
        ("INSERT INTO order_items SELECT * FROM order_items", "stg_order_items"),
        ("UPDATE order_items SET product_id='orphan'", "stg_order_items"),
        ("UPDATE order_items SET order_item_id=NULL", "stg_order_items"),
        ("UPDATE order_reviews SET review_id=NULL", "stg_order_reviews"),
        ("UPDATE order_reviews SET order_id='orphan'", "stg_order_reviews"),
        ("UPDATE order_items SET price=-1", "assert_no_negative_prices"),
        ("UPDATE order_items SET freight_value=-1", "assert_no_negative_prices"),
    ],
)
def test_required_dbt_checks_reject_invalid_source(staging, mutation, selector):
    build()
    with staging.begin() as conn:
        conn.execute(text(mutation))
    result = dbt("test", "--select", "path:models/staging", "tag:staging")
    assert result.returncode != 0, result.stdout + result.stderr
    import json

    outcomes = json.loads(
        (ROOT / "ecommerce_transform/target/run_results.json").read_text()
    )["results"]
    assert any(row["status"] == "fail" for row in outcomes)
    assert not any(row["status"] == "error" for row in outcomes)


def test_null_constituent_preserved_and_unknown_type_not_invented(staging):
    with staging.begin() as conn:
        conn.execute(
            text("UPDATE order_payments SET payment_type=NULL,payment_value=NULL")
        )
        conn.execute(
            text("INSERT INTO order_payments VALUES (:order,2,NULL,1,12)"),
            {"order": "c" * 32},
        )
        conn.execute(text("UPDATE order_items SET price=NULL,freight_value=NULL"))
    build()
    with staging.connect() as conn:
        assert conn.execute(
            text(
                "SELECT total_payment_value,favorite_payment_type,used_voucher FROM stg_order_payments"
            )
        ).one() == (None, None, False)
        assert conn.execute(
            text("SELECT item_price,freight_value FROM stg_order_items")
        ).one() == (None, None)
    result = dbt("test", "--select", "path:models/staging", "tag:staging")
    assert result.returncode == 0, result.stdout + result.stderr


def test_valid_large_fractional_item_amounts_are_preserved(staging):
    with staging.begin() as conn:
        conn.execute(
            text("UPDATE order_items SET price=123456789.123,freight_value=0.001")
        )
    build()
    with staging.connect() as conn:
        from decimal import Decimal

        assert conn.execute(
            text("SELECT item_price,freight_value FROM stg_order_items")
        ).one() == (Decimal("123456789.123"), Decimal("0.001"))
