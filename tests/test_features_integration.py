import os
import sys
from pathlib import Path
from decimal import Decimal
import pytest
from sqlalchemy import text
from test_staging_integration import staging, dbt

ROOT = Path(__file__).resolve().parents[1]


def run_features(*extra):
    result = dbt("run", "--select", "+customer_features", *extra)
    assert result.returncode == 0, result.stdout + result.stderr


def test_seconds_preserve_fraction_and_calendar_dates(staging):
    with staging.begin() as conn:
        conn.execute(
            text(
                "UPDATE orders SET order_purchase_timestamp='2018-01-01 23:59:59.5',order_approved_at='2018-01-02 00:00:00',order_delivered_carrier_date='2018-01-02 00:00:01',order_delivered_customer_date='2018-01-03 23:59:59.5',order_estimated_delivery_date='2018-01-02 23:59:59'"
            )
        )
    run_features("--vars", '{as_of_date: "2018-01-02"}')
    with staging.connect() as conn:
        row = conn.execute(
            text(
                "SELECT approval_seconds,carrier_seconds,delivery_seconds,after_estimated_delivery_seconds,seconds_since_first_purchase FROM customer_features"
            )
        ).one()
        assert row == (Decimal("0.5"), Decimal("1.5"), Decimal("172800"), 86400, 86400)
        columns = (
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name='customer_features'"
                )
            )
            .scalars()
            .all()
        )
        assert not any(
            col
            in [
                "delivery_days",
                "approval_days",
                "carrier_days",
                "days_since_last_purchase",
                "after_estimated_delivery",
            ]
            or col.endswith("_missing")
            or col in ["average_order_value", "category_english", "product_photos_qty"]
            for col in columns
        )


def add_order(
    conn,
    index,
    person,
    purchase,
    status="delivered",
    *,
    complete=True,
    state="SP",
    items=True,
    payments=True,
):
    cid, oid = f"{index:032x}", f"{index+1000:032x}"
    conn.execute(
        text("INSERT INTO customers VALUES (:cid,:person,1234,'city',:state)"),
        {"cid": cid, "person": f"{person:032x}", "state": state},
    )
    conn.execute(
        text(
            "INSERT INTO orders VALUES (:oid,:cid,:status,:purchase,CASE WHEN :complete THEN cast(:purchase as timestamp)+interval '1 second' END,cast(:purchase as timestamp)+interval '2 seconds',cast(:purchase as timestamp)+interval '3 seconds',cast(:purchase as timestamp)+interval '4 seconds')"
        ),
        {
            "oid": oid,
            "cid": cid,
            "status": status,
            "purchase": purchase,
            "complete": complete,
        },
    )
    if items:
        conn.execute(
            text(
                "INSERT INTO order_items VALUES (:oid,1,:product,:seller,:purchase,10,2)"
            ),
            {"oid": oid, "product": "d" * 32, "seller": "e" * 32, "purchase": purchase},
        )
    if payments:
        conn.execute(
            text("INSERT INTO order_payments VALUES (:oid,1,'credit_card',1,12)"),
            {"oid": oid},
        )
    return oid


def test_anchors_and_inclusive_all_status_target(staging):
    with staging.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM order_reviews; DELETE FROM order_payments; DELETE FROM order_items; DELETE FROM orders; DELETE FROM customers"
            )
        )
        # Jan1 plus180days = June30 in non-leap2018. No host clock involved.
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
            add_order(conn, index, index, "2018-01-01")
            add_order(conn, index + 20, index, "2018-06-30", status)
        add_order(conn, 50, 50, "2018-01-01")  # mature no repeat
        add_order(conn, 51, 51, "2018-07-01")  # early positive
        add_order(conn, 52, 51, "2018-07-01", "canceled")
        add_order(conn, 53, 53, "2018-07-01")  # uncertain
        add_order(conn, 54, 54, "2018-01-01")  # outside inclusive boundary
        add_order(conn, 55, 54, "2018-06-30 00:00:00.000001", "canceled")
        add_order(conn, 56, 56, "2018-01-01")  # earlier order doesn't count
        add_order(conn, 57, 56, "2017-12-31", "canceled")
        anchor = add_order(conn, 60, 60, "2018-01-01", state="SP")
        add_order(
            conn, 61, 60, "2018-01-01", state="RJ"
        )  # tied delivered later id; counts repeat
        add_order(conn, 62, 60, "2017-01-01", "canceled", state="MG")
        incomplete = add_order(conn, 63, 63, "2018-01-01", complete=False)
        add_order(conn, 64, 63, "2018-02-01")  # never substitute this anchor
        add_order(conn, 70, 70, "2018-06-30", "canceled")  # no delivered anchor
    run_features()
    with staging.connect() as conn:
        labels = dict(
            conn.execute(
                text(
                    "SELECT customer_unique_id,repeat_within_180_days FROM customer_features"
                )
            ).all()
        )
        assert labels == {
            **{f"{i:032x}": 1 for i in range(1, 9)},
            f"{50:032x}": 0,
            f"{51:032x}": 1,
            f"{53:032x}": None,
            f"{54:032x}": 0,
            f"{56:032x}": 0,
            f"{60:032x}": 1,
        }
        assert conn.execute(
            text(
                "SELECT first_delivered_order_id,customer_state,total_orders FROM customer_features WHERE customer_unique_id=:p"
            ),
            {"p": f"{60:032x}"},
        ).one() == (anchor, "SP", 2)
        assert conn.execute(
            text(
                "SELECT first_delivered_order_id,is_eligible FROM customer_feature_diagnostics WHERE customer_unique_id=:p"
            ),
            {"p": f"{63:032x}"},
        ).one() == (incomplete, False)
        assert (
            conn.execute(
                text("SELECT distinct observation_end_ts FROM customer_features")
            )
            .scalar()
            .isoformat()
            == "2018-07-01T00:00:00"
        )
        assert (
            conn.execute(
                text(
                    "SELECT has_complete_followup FROM customer_features WHERE customer_unique_id=:p"
                ),
                {"p": f"{51:032x}"},
            ).scalar()
            is False
        )


def test_anchor_sums_null_constituents_and_recovery(staging):
    with staging.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM order_reviews; DELETE FROM order_payments; DELETE FROM order_items; DELETE FROM orders; DELETE FROM customers"
            )
        )
        anchors = {i: add_order(conn, i, i, "2018-01-01") for i in range(1, 9)}
        for oid in anchors.values():
            conn.execute(
                text(
                    "INSERT INTO order_items SELECT order_id,2,product_id,seller_id,shipping_limit_date,20,3 FROM order_items WHERE order_id=:o"
                ),
                {"o": oid},
            )
        conn.execute(
            text("DELETE FROM order_payments WHERE order_id=:o"), {"o": anchors[1]}
        )
        conn.execute(
            text(
                "INSERT INTO order_payments VALUES (:o,1,'voucher',1,30),(:o,2,'voucher',1,30),(:o,3,'credit_card',1,50)"
            ),
            {"o": anchors[1]},
        )
        conn.execute(
            text("DELETE FROM order_payments WHERE order_id=:o"), {"o": anchors[2]}
        )
        conn.execute(
            text(
                "UPDATE order_payments SET payment_type=NULL,payment_value=110 WHERE order_id=:o"
            ),
            {"o": anchors[3]},
        )
        conn.execute(
            text("UPDATE order_payments SET payment_value=NULL WHERE order_id=:o"),
            {"o": anchors[4]},
        )
        conn.execute(
            text(
                "UPDATE order_items SET freight_value=NULL WHERE order_id=:o AND order_item_id=2"
            ),
            {"o": anchors[5]},
        )
        conn.execute(
            text("DELETE FROM order_items WHERE order_id=:o"), {"o": anchors[6]}
        )
        # Null item price is unused when valid payment spend exists, so keep customer7.
        conn.execute(
            text(
                "UPDATE order_items SET price=NULL WHERE order_id=:o AND order_item_id=2"
            ),
            {"o": anchors[7]},
        )
        conn.execute(
            text("DELETE FROM order_payments WHERE order_id=:o"), {"o": anchors[8]}
        )
        conn.execute(
            text(
                "UPDATE order_items SET price=NULL WHERE order_id=:o AND order_item_id=2"
            ),
            {"o": anchors[8]},
        )
        later = add_order(conn, 20, 1, "2018-02-01", state="RJ")
        for index, oid, score in [
            (1, anchors[1], 2),
            (2, anchors[1], 4),
            (3, later, 5),
        ]:
            conn.execute(
                text(
                    "INSERT INTO order_reviews VALUES (:rid,:o,:score,NULL,NULL,'2018-02-01','2018-02-02')"
                ),
                {"rid": f"{index+500:032x}", "o": oid, "score": score},
            )
    run_features()
    with staging.connect() as conn:
        assert conn.execute(
            text(
                "SELECT total_spent,item_count,freight_value,favorite_payment_type,used_voucher,review_below_average,has_first_order_review,customer_state FROM customer_features WHERE customer_unique_id=:p"
            ),
            {"p": f"{1:032x}"},
        ).one() == (110, 2, 5, "voucher", True, True, True, "SP")
        rows = {
            int(row.customer_unique_id, 16): row
            for row in conn.execute(
                text(
                    "SELECT customer_unique_id,total_spent,item_spend,freight_value,item_count,is_eligible FROM customer_feature_diagnostics"
                )
            )
        }
        assert rows[2].total_spent == 35 and rows[2].is_eligible is False
        assert rows[3].total_spent == 110 and rows[3].is_eligible is False
        assert rows[4].total_spent is None and rows[4].is_eligible is False
        assert rows[5].freight_value is None and rows[5].is_eligible is False
        assert rows[6].item_count is None and rows[6].is_eligible is False
        assert rows[7].item_spend is None and rows[7].is_eligible is True
        assert rows[8].total_spent is None and rows[8].is_eligible is False
        assert conn.execute(
            text(
                "SELECT review_below_average,has_first_order_review FROM customer_features WHERE customer_unique_id=:p"
            ),
            {"p": f"{7:032x}"},
        ).one() == (False, False)


def test_exclusions_and_retained_chronology_warning_patterns(staging):
    with staging.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM order_reviews; DELETE FROM order_payments; DELETE FROM order_items; DELETE FROM orders; DELETE FROM customers"
            )
        )
        ids = {i: add_order(conn, i, i, "2018-01-01") for i in range(1, 13)}
        for index, mutation in {
            1: "order_approved_at='2017-12-31 23:59:59'",
            2: "order_delivered_carrier_date='2017-12-31 23:59:59'",
            3: "order_delivered_customer_date='2017-12-31 23:59:59'",
            4: "order_approved_at='2018-01-01 00:00:02',order_delivered_carrier_date='2018-01-01 00:00:01'",
            5: "order_delivered_carrier_date='2018-01-01 00:00:04'",
            6: "order_approved_at='2018-01-01 00:00:04'",
            7: "order_estimated_delivery_date='2017-12-31'",
            8: "order_approved_at=NULL",
            9: "order_delivered_carrier_date=NULL",
            10: "order_delivered_customer_date=NULL",
            11: "order_estimated_delivery_date=NULL",
        }.items():
            conn.execute(
                text("UPDATE orders SET " + mutation + " WHERE order_id=:o"),
                {"o": ids[index]},
            )
        conn.execute(
            text(
                "UPDATE customers SET customer_state=NULL WHERE customer_unique_id=:p"
            ),
            {"p": f"{12:032x}"},
        )
    run_features()
    with staging.connect() as conn:
        rows = {
            int(row.customer_unique_id, 16): row
            for row in conn.execute(
                text(
                    "SELECT customer_unique_id,is_eligible,exclusion_reasons,warning_reasons,order_approved_ts FROM customer_feature_diagnostics"
                )
            )
        }
        assert sorted(i for i in rows if rows[i].is_eligible) == [4, 5, 6, 7]
        assert rows[1].exclusion_reasons == ["negative_approval_seconds"]
        assert rows[2].exclusion_reasons == ["negative_carrier_seconds"]
        assert rows[3].exclusion_reasons == ["negative_delivery_seconds"]
        assert rows[1].order_approved_ts.isoformat() == "2017-12-31T23:59:59"
        assert rows[4].warning_reasons == ["carrier_before_approval"]
        assert rows[5].warning_reasons == ["delivery_before_carrier"]
        assert rows[6].warning_reasons == [
            "carrier_before_approval",
            "approval_after_delivery",
        ]
        assert rows[7].warning_reasons == ["estimate_before_purchase"]
        assert rows[8].exclusion_reasons == ["missing_approval_timestamp"]
        assert rows[9].exclusion_reasons == ["missing_carrier_timestamp"]
        assert rows[10].exclusion_reasons == ["missing_delivery_timestamp"]
        assert rows[11].exclusion_reasons == ["missing_estimate_timestamp"]
        assert rows[12].exclusion_reasons == ["null_customer_state"]


@pytest.mark.parametrize(
    "variables", ['{as_of_date: "2017-12-31"}', '{observation_end_ts: "2017-12-31"}']
)
def test_invalid_configuration_fails_before_replacing_mart(staging, variables):
    run_features()
    result = dbt("run", "--select", "+customer_features", "--vars", variables)
    assert result.returncode != 0, result.stdout + result.stderr
    with staging.connect() as conn:
        assert (
            conn.execute(text("SELECT count(*) FROM customer_features")).scalar() == 1
        )


@pytest.mark.parametrize(
    "table,column,value",
    [
        ("order_payments", "payment_value", "-1"),
        ("order_payments", "payment_value", "NaN"),
        ("order_items", "price", "Infinity"),
        ("order_items", "freight_value", "-Infinity"),
        ("order_items", "price", "-1"),
        ("order_items", "freight_value", "-1"),
    ],
)
def test_raw_negative_money_aborts_run_without_replacing_mart(
    staging, table, column, value
):
    run_features()
    with staging.begin() as conn:
        conn.execute(text(f"UPDATE {table} SET {column}=:value"), {"value": value})
    result = dbt("run", "--select", "+customer_features")
    assert result.returncode != 0, result.stdout + result.stderr
    with staging.connect() as conn:
        assert (
            conn.execute(text("SELECT total_spent FROM customer_features")).scalar()
            == 12
        )


def test_global_review_threshold_presence_and_equality(staging):
    with staging.begin() as conn:
        conn.execute(text("UPDATE order_reviews SET review_score=3"))
        later = add_order(conn, 20, 0, "2018-02-01")
        conn.execute(
            text("UPDATE customers SET customer_unique_id=:p WHERE customer_id=:cid"),
            {"p": "b" * 32, "cid": f"{20:032x}"},
        )
        conn.execute(
            text(
                "INSERT INTO order_reviews VALUES (:rid,:o,5,NULL,NULL,'2018-02-02','2018-02-03')"
            ),
            {"rid": "f" * 32, "o": later},
        )
    run_features()
    with staging.connect() as conn:
        assert conn.execute(
            text(
                "SELECT review_below_average,has_first_order_review FROM customer_features"
            )
        ).one() == (
            True,
            True,
        )  # global4;anchor-only3 would yieldfalse
    with staging.begin() as conn:
        conn.execute(text("UPDATE order_reviews SET review_score=3"))
    run_features()
    with staging.connect() as conn:
        assert conn.execute(
            text(
                "SELECT review_below_average,has_first_order_review FROM customer_features"
            )
        ).one() == (
            False,
            True,
        )  # equality3
    with staging.begin() as conn:
        conn.execute(
            text("DELETE FROM order_reviews WHERE order_id=:o"), {"o": "c" * 32}
        )
    run_features()
    with staging.connect() as conn:
        assert conn.execute(
            text(
                "SELECT review_below_average,has_first_order_review FROM customer_features"
            )
        ).one() == (False, False)


def test_legitimate_zeros_and_strict_discrepancy_warning(staging):
    with staging.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM order_reviews; DELETE FROM order_payments; DELETE FROM order_items; DELETE FROM orders; DELETE FROM customers"
            )
        )
        ids = {i: add_order(conn, i, i, "2018-01-01") for i in range(1, 4)}
        conn.execute(
            text("UPDATE order_payments SET payment_value=12.01 WHERE order_id=:o"),
            {"o": ids[1]},
        )
        conn.execute(
            text("UPDATE order_payments SET payment_value=12.02 WHERE order_id=:o"),
            {"o": ids[2]},
        )
        conn.execute(
            text("UPDATE order_items SET price=0,freight_value=0 WHERE order_id=:o"),
            {"o": ids[3]},
        )
        conn.execute(
            text("UPDATE order_payments SET payment_value=0 WHERE order_id=:o"),
            {"o": ids[3]},
        )
        conn.execute(
            text(
                "UPDATE orders SET order_approved_at=order_purchase_timestamp,order_delivered_carrier_date=order_purchase_timestamp,order_delivered_customer_date=order_purchase_timestamp,order_estimated_delivery_date=order_purchase_timestamp WHERE order_id=:o"
            ),
            {"o": ids[3]},
        )
    run_features()
    with staging.connect() as conn:
        rows = dict(
            conn.execute(
                text(
                    "SELECT customer_unique_id,warning_reasons FROM customer_feature_diagnostics"
                )
            ).all()
        )
        assert rows[f"{1:032x}"] == []
        assert rows[f"{2:032x}"] == ["payment_item_discrepancy"]
        assert rows[f"{3:032x}"] == ["zero_item_price", "zero_order_spend"]
        assert conn.execute(
            text(
                "SELECT total_spent,freight_value,item_count,delivery_seconds,approval_seconds,carrier_seconds,after_estimated_delivery_seconds,seconds_since_first_purchase,used_voucher,review_below_average FROM customer_features WHERE customer_unique_id=:p"
            ),
            {"p": f"{3:032x}"},
        ).one() == (0, 0, 1, 0, 0, 0, 0, 0, False, False)


def test_overrides_use_anchor_recency_and_exact_observation_boundary(staging):
    with staging.begin() as conn:
        conn.execute(text("UPDATE orders SET order_purchase_timestamp='2018-01-01'"))
        later = add_order(conn, 20, 20, "2018-02-01")
        conn.execute(
            text("UPDATE customers SET customer_unique_id=:p WHERE customer_id=:c"),
            {"p": "b" * 32, "c": f"{20:032x}"},
        )
        add_order(
            conn, 30, 30, "2018-06-30", "canceled"
        )  # latest record is not delivered
    run_features(
        "--vars", '{as_of_date: "2018-01-01", observation_end_ts: "2018-06-30"}'
    )
    with staging.connect() as conn:
        assert conn.execute(
            text(
                "SELECT seconds_since_first_purchase,has_complete_followup,repeat_within_180_days,observation_end_provenance FROM customer_features"
            )
        ).one() == (0, True, 1, "explicit_override")
    run_features()
    with staging.connect() as conn:
        assert (
            conn.execute(
                text(
                    "SELECT has_complete_followup,observation_end_ts FROM customer_features"
                )
            ).one()[0]
            is True
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE customer_features SET total_spent=-1",
        "UPDATE customer_features SET freight_value='NaN'",
        "UPDATE customer_features SET after_estimated_delivery_seconds=-1",
        "ALTER TABLE customer_features ALTER COLUMN item_count TYPE numeric; UPDATE customer_features SET item_count=1.5",
        "UPDATE customer_features SET item_count=0",
    ],
)
def test_final_mart_rejects_invalid_numeric_values(staging, mutation):
    run_features()
    with staging.begin() as conn:
        conn.execute(text(mutation))
    result = dbt("test", "--select", "assert_customer_feature_values")
    assert result.returncode != 0, result.stdout + result.stderr


def test_diagnostic_export_reconciles_exclusions_and_cohorts(staging, tmp_path):
    import json
    import subprocess

    with staging.begin() as conn:
        add_order(conn, 20, 20, "2018-01-02", payments=False)
    run_features()
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/export_feature_diagnostics.py"),
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    census = json.loads((tmp_path / "census.json").read_text())
    assert (
        census["candidates"] == 2
        and census["eligible"] == 1
        and census["excluded"] == 1
    )
    assert census["populations"]["eligible"]["uncertain"] == 1
    assert census["populations"]["excluded"]["uncertain"] == 1
    assert census["exclusion_reasons"] == {"null_favorite_payment_type": 1}
    assert census["exclusion_patterns"] == {"null_favorite_payment_type": 1}
    assert census["recovered_spend_candidates"] == 1
    import pandas as pd

    frames = [
        pd.read_parquet(p, dtype_backend="pyarrow")
        for p in tmp_path.glob("candidates-*.parquet")
    ]
    assert sum(len(f) for f in frames) == 2


def test_source_identity_checks_detect_plausible_but_wrong_mart_value(staging):
    run_features()
    with staging.begin() as conn:
        conn.execute(text("UPDATE customer_features SET total_spent=13"))
    result = dbt("test", "--select", "assert_anchor_feature_identities")
    assert result.returncode != 0, result.stdout + result.stderr


def test_diagnostic_export_absent_mart_is_truthful(staging, tmp_path):
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/export_feature_diagnostics.py"),
            "--output-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "run dbt first" in result.stdout
