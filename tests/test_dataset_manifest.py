import json
import shutil
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "olist_valid"
EXPECTED = json.loads((FIXTURE.parent / "olist_expected.json").read_text())
SOURCE = {"mode": "existing", "dataset": "olist/brazilian-ecommerce"}


def test_valid_dataset_manifest_is_read_only_and_records_nine_files(tmp_path):
    from scripts.dataset_manifest import validate_dataset

    data = tmp_path / "data"
    shutil.copytree(FIXTURE, data)
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    result = validate_dataset(data, source=SOURCE)
    assert result["schema_version"] == 1
    assert result["source"] == SOURCE
    assert len(result["files"]) == 9
    for expected in EXPECTED:
        actual = result["files"][expected["name"]]
        assert actual["sha256"] == expected["sha256"]
        assert actual["size_bytes"] == expected["size_bytes"]
        assert actual["row_count"] == 1
        assert actual["columns"] == before[expected["name"]].decode().splitlines()[
            0
        ].split(",")
    assert {p.name: p.read_bytes() for p in data.iterdir()} == before


def test_missing_required_file_reports_filename(tmp_path):
    import pytest
    from scripts.dataset_manifest import DatasetValidationError, validate_dataset

    shutil.copytree(FIXTURE, tmp_path / "data")
    (tmp_path / "data" / "olist_sellers_dataset.csv").unlink()
    with pytest.raises(
        DatasetValidationError, match="olist_sellers_dataset.csv: missing required file"
    ):
        validate_dataset(tmp_path / "data", source=SOURCE)


def test_missing_required_field_reports_file_and_field(tmp_path):
    import csv
    import pytest
    from scripts.dataset_manifest import DatasetValidationError, validate_dataset

    shutil.copytree(FIXTURE, tmp_path / "data")
    path = tmp_path / "data" / "olist_order_items_dataset.csv"
    rows = list(csv.reader(path.read_text().splitlines()))
    index = rows[0].index("price")
    for row in rows:
        row.pop(index)
    with path.open("w", newline="") as stream:
        csv.writer(stream).writerows(rows)
    with pytest.raises(
        DatasetValidationError,
        match="olist_order_items_dataset.csv: price: missing required column",
    ):
        validate_dataset(path.parent, source=SOURCE)


import pytest


@pytest.mark.parametrize(
    "contents", ["", "order_id\n", "a,b\nsecret\n", 'a,b\n"secret']
)
def test_empty_or_truncated_csv_reports_no_source_values(tmp_path, contents):
    from scripts.dataset_manifest import DatasetValidationError, validate_dataset

    shutil.copytree(FIXTURE, tmp_path / "data")
    path = tmp_path / "data" / "olist_orders_dataset.csv"
    path.write_text(contents)
    with pytest.raises(DatasetValidationError) as error:
        validate_dataset(path.parent, source=SOURCE)
    assert "olist_orders_dataset.csv" in str(error.value)
    assert "secret" not in str(error.value)


def replace_cell(data, filename, field, value):
    import csv

    path = data / filename
    with path.open(newline="") as stream:
        rows = list(csv.reader(stream))
    rows[1][rows[0].index(field)] = value
    with path.open("w", newline="") as stream:
        csv.writer(stream, lineterminator="\n").writerows(rows)


@pytest.mark.parametrize("value", ["", "secret-invalid-key", "a" * 31, "g" * 32])
def test_required_keys_are_nonempty_olist_identifiers(tmp_path, value):
    from scripts.dataset_manifest import DatasetValidationError, validate_dataset

    shutil.copytree(FIXTURE, tmp_path / "data")
    replace_cell(tmp_path / "data", "olist_orders_dataset.csv", "customer_id", value)
    with pytest.raises(
        DatasetValidationError,
        match="olist_orders_dataset.csv: customer_id: invalid key",
    ):
        validate_dataset(tmp_path / "data", source=SOURCE)


@pytest.mark.parametrize(
    "value", ["NaN", "nan", "Inf", "-Infinity", "NULL", "-0.01", "secret"]
)
def test_raw_money_rejects_negative_nonfinite_and_malformed_values(tmp_path, value):
    from scripts.dataset_manifest import DatasetValidationError, validate_dataset

    shutil.copytree(FIXTURE, tmp_path / "data")
    replace_cell(tmp_path / "data", "olist_order_items_dataset.csv", "price", value)
    with pytest.raises(
        DatasetValidationError,
        match="olist_order_items_dataset.csv: price: invalid number",
    ):
        validate_dataset(tmp_path / "data", source=SOURCE)


@pytest.mark.parametrize(
    "filename,field,value",
    [
        ("olist_orders_dataset.csv", "order_purchase_timestamp", "secret"),
        ("olist_orders_dataset.csv", "order_purchase_timestamp", ""),
        ("olist_orders_dataset.csv", "order_status", "secret"),
        ("olist_order_items_dataset.csv", "order_item_id", "1.5"),
        ("olist_order_items_dataset.csv", "order_item_id", "0"),
        ("olist_order_payments_dataset.csv", "payment_sequential", ""),
        ("olist_order_payments_dataset.csv", "payment_installments", "1.5"),
        ("olist_geolocation_dataset.csv", "geolocation_lat", "secret"),
        ("olist_products_dataset.csv", "product_weight_g", "secret"),
        ("olist_order_reviews_dataset.csv", "review_score", "1.5"),
    ],
)
def test_required_types_report_safe_file_and_field(tmp_path, filename, field, value):
    from scripts.dataset_manifest import DatasetValidationError, validate_dataset

    shutil.copytree(FIXTURE, tmp_path / "data")
    replace_cell(tmp_path / "data", filename, field, value)
    with pytest.raises(DatasetValidationError) as error:
        validate_dataset(tmp_path / "data", source=SOURCE)
    assert f"{filename}: {field}:" in str(error.value)
    assert "secret" not in str(error.value)


def test_duplicate_required_primary_key_is_rejected(tmp_path):
    from scripts.dataset_manifest import DatasetValidationError, validate_dataset

    shutil.copytree(FIXTURE, tmp_path / "data")
    path = tmp_path / "data" / "olist_orders_dataset.csv"
    with path.open("a") as stream:
        stream.write(path.read_text().splitlines()[1] + "\n")
    with pytest.raises(
        DatasetValidationError,
        match="olist_orders_dataset.csv: order_id: duplicate key",
    ):
        validate_dataset(path.parent, source=SOURCE)


def test_nullable_values_and_raw_review_geolocation_duplicates_are_preserved(tmp_path):
    from scripts.dataset_manifest import validate_dataset

    shutil.copytree(FIXTURE, tmp_path / "data")
    data = tmp_path / "data"
    for field in [
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]:
        replace_cell(data, "olist_orders_dataset.csv", field, "")
    for field in ["price", "freight_value"]:
        replace_cell(data, "olist_order_items_dataset.csv", field, "")
    replace_cell(data, "olist_order_payments_dataset.csv", "payment_value", "")
    for filename in [
        "olist_order_reviews_dataset.csv",
        "olist_geolocation_dataset.csv",
    ]:
        path = data / filename
        row = path.read_text().splitlines()[1]
        with path.open("a") as stream:
            stream.write(row + "\n")
    before = {p.name: p.read_bytes() for p in data.iterdir()}
    result = validate_dataset(data, source=SOURCE)
    assert result["files"]["olist_order_reviews_dataset.csv"]["row_count"] == 2
    assert result["files"]["olist_geolocation_dataset.csv"]["row_count"] == 2
    assert before == {p.name: p.read_bytes() for p in data.iterdir()}


def test_numeric_composite_keys_compare_by_value(tmp_path):
    from scripts.dataset_manifest import DatasetValidationError, validate_dataset

    shutil.copytree(FIXTURE, tmp_path / "data")
    path = tmp_path / "data" / "olist_order_items_dataset.csv"
    row = path.read_text().splitlines()[1].replace(",1,", ",1.0,")
    with path.open("a") as stream:
        stream.write(row + "\n")
    with pytest.raises(
        DatasetValidationError, match="order_id,order_item_id: duplicate key"
    ):
        validate_dataset(path.parent, source=SOURCE)
