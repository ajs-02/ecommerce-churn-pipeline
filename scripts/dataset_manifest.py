"""Read-only validation and fingerprints for the raw Olist dataset."""

import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation
from datetime import datetime
import re
from pathlib import Path

import pandas as pd

SCHEMAS = {
    "olist_customers_dataset.csv": "customer_id customer_unique_id customer_zip_code_prefix customer_city customer_state",
    "olist_geolocation_dataset.csv": "geolocation_zip_code_prefix geolocation_lat geolocation_lng geolocation_city geolocation_state",
    "olist_orders_dataset.csv": "order_id customer_id order_status order_purchase_timestamp order_approved_at order_delivered_carrier_date order_delivered_customer_date order_estimated_delivery_date",
    "olist_order_items_dataset.csv": "order_id order_item_id product_id seller_id shipping_limit_date price freight_value",
    "olist_order_payments_dataset.csv": "order_id payment_sequential payment_type payment_installments payment_value",
    "olist_order_reviews_dataset.csv": "review_id order_id review_score review_comment_title review_comment_message review_creation_date review_answer_timestamp",
    "olist_products_dataset.csv": "product_id product_category_name product_name_lenght product_description_lenght product_photos_qty product_weight_g product_length_cm product_height_cm product_width_cm",
    "olist_sellers_dataset.csv": "seller_id seller_zip_code_prefix seller_city seller_state",
    "product_category_name_translation.csv": "product_category_name product_category_name_english",
}
UNIQUE_KEYS = {
    "olist_customers_dataset.csv": ["customer_id"],
    "olist_orders_dataset.csv": ["order_id"],
    "olist_products_dataset.csv": ["product_id"],
    "olist_sellers_dataset.csv": ["seller_id"],
    "olist_order_items_dataset.csv": ["order_id", "order_item_id"],
    "olist_order_payments_dataset.csv": ["order_id", "payment_sequential"],
    "product_category_name_translation.csv": ["product_category_name"],
}

MONEY = {"price", "freight_value", "payment_value"}
INTEGERS = {
    "order_item_id",
    "payment_sequential",
    "payment_installments",
    "review_score",
    "product_name_lenght",
    "product_description_lenght",
    "product_photos_qty",
    "customer_zip_code_prefix",
    "seller_zip_code_prefix",
    "geolocation_zip_code_prefix",
}
NUMBERS = (
    MONEY
    | INTEGERS
    | {
        "geolocation_lat",
        "geolocation_lng",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    }
)
TIMESTAMPS = {
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
    "shipping_limit_date",
    "review_creation_date",
    "review_answer_timestamp",
}
REQUIRED = {"order_item_id", "payment_sequential", "order_purchase_timestamp"}
STATUSES = {
    "delivered",
    "shipped",
    "canceled",
    "unavailable",
    "invoiced",
    "processing",
    "created",
    "approved",
}


class DatasetValidationError(ValueError):
    """A dataset cannot safely be published; messages exclude source values."""


def validate_dataset(data_dir: Path | str, *, source: dict[str, str]) -> dict:
    """Return a manifest without modifying the directory or its CSV files."""
    files = {}
    for name, schema in SCHEMAS.items():
        path = Path(data_dir) / name
        if not path.is_file():
            raise DatasetValidationError(f"{name}: missing required file")
        try:
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream, strict=True)
                header = next(reader)
                if len(header) != len(set(header)):
                    raise DatasetValidationError(f"{name}: duplicate columns")
                count = 0
                for row in reader:
                    if len(row) != len(header):
                        raise DatasetValidationError(f"{name}: malformed CSV record")
                    count += 1
                if count == 0:
                    raise DatasetValidationError(f"{name}: empty dataset")
            frame = pd.read_csv(
                path,
                engine="c",
                dtype_backend="pyarrow",
                dtype="string[pyarrow]",
                keep_default_na=False,
                chunksize=50000,
            )
        except DatasetValidationError:
            raise
        except Exception:
            raise DatasetValidationError(
                f"{name}: unreadable or malformed CSV"
            ) from None
        seen_keys = set()
        for frame in frame:
            for field in schema.split():
                if field not in frame.columns:
                    raise DatasetValidationError(
                        f"{name}: {field}: missing required column"
                    )
            for field in frame.columns:
                if field in {
                    "customer_id",
                    "customer_unique_id",
                    "order_id",
                    "product_id",
                    "seller_id",
                    "review_id",
                }:
                    if not frame[field].str.fullmatch(r"[0-9a-f]{32}").all():
                        raise DatasetValidationError(f"{name}: {field}: invalid key")
            for field in NUMBERS & set(frame.columns):
                for value in frame[field]:
                    if value == "" and field not in REQUIRED:
                        continue
                    try:
                        number = Decimal(value)
                        valid = number.is_finite()
                        if valid and field in MONEY:
                            valid = number >= 0
                        if valid and field in INTEGERS:
                            valid = number == number.to_integral_value()
                        if valid and field in {"order_item_id", "payment_sequential"}:
                            valid = number > 0
                    except InvalidOperation:
                        valid = False
                    if not valid:
                        raise DatasetValidationError(f"{name}: {field}: invalid number")
            key = UNIQUE_KEYS.get(name)
            if key:
                key_frame = frame[key].copy()
                for field in set(key) & INTEGERS:
                    key_frame[field] = key_frame[field].map(Decimal)
                key_rows = list(key_frame.itertuples(index=False, name=None))
                if key_frame.duplicated().any() or any(
                    row in seen_keys for row in key_rows
                ):
                    raise DatasetValidationError(
                        f"{name}: {','.join(key)}: duplicate key"
                    )
                seen_keys.update(key_rows)
            for field in TIMESTAMPS & set(frame.columns):
                for value in frame[field]:
                    if value == "" and field not in REQUIRED:
                        continue
                    try:
                        if not re.fullmatch(
                            r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?", value
                        ):
                            raise ValueError
                        datetime.fromisoformat(value)
                    except ValueError:
                        raise DatasetValidationError(
                            f"{name}: {field}: invalid timestamp"
                        ) from None
            if (
                "order_status" in frame
                and not frame["order_status"].isin(STATUSES).all()
            ):
                raise DatasetValidationError(f"{name}: order_status: invalid status")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        files[name] = {
            "sha256": digest,
            "size_bytes": path.stat().st_size,
            "row_count": count,
            "columns": frame.columns.tolist(),
        }
    return {
        "schema_version": 1,
        "source": dict(source),
        "timestamp_interpretation": "Source timestamps are timezone-naive; no timezone inferred.",
        "files": files,
        "dataset_sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True).encode()
        ).hexdigest(),
    }


def validate_saved_manifest(data_dir, manifest):
    """Check an acquisition manifest when present; legacy datasets remain supported."""
    path = Path(data_dir) / "dataset_manifest.json"
    if path.exists():
        try:
            stored = json.loads(path.read_text())
        except (ValueError, OSError):
            raise DatasetValidationError(
                "dataset_manifest.json: unreadable manifest"
            ) from None
        if (
            not isinstance(stored, dict)
            or stored.get("schema_version") != 1
            or stored.get("files") != manifest["files"]
            or stored.get("dataset_sha256") != manifest["dataset_sha256"]
        ):
            raise DatasetValidationError(
                "dataset_manifest.json: dataset fingerprint mismatch"
            )
