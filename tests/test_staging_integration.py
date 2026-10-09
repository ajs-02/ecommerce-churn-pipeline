import os
import subprocess
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import upload_data

@pytest.fixture
def staging(monkeypatch):
    port = os.getenv('T03_POSTGRES_PORT')
    if not port:
        pytest.skip('Set T03_POSTGRES_PORT for disposable PostgreSQL')
    for key, value in {'HOST': '127.0.0.1', 'PORT': port, 'DB': 'postgres', 'USER': 't02', 'PASSWORD': 'disposable'}.items():
        monkeypatch.setenv('POSTGRES_' + key, value)
    engine = upload_data.get_db_engine()
    with engine.begin() as conn:
        conn.execute(text('DROP SCHEMA public CASCADE'))
        conn.execute(text('CREATE SCHEMA public'))
    assert upload_data.upload_csvs_to_postgres(ROOT / 'tests/fixtures/olist_valid') == 0
    yield engine
    engine.dispose()

def dbt(*args):
    result = subprocess.run([str(Path(sys.executable).with_name('dbt.exe')), *args, '--project-dir', str(ROOT / 'ecommerce_transform'), '--profiles-dir', str(ROOT / 'ecommerce_transform')], capture_output=True, text=True)
    evidence = os.getenv('T03_EVIDENCE_DIR')
    if evidence:
        path = Path(evidence)
        path.mkdir(parents=True, exist_ok=True)
        with (path / 'dbt_commands.log').open('a', encoding='utf-8') as stream:
            stream.write('\nCOMMAND: dbt ' + ' '.join(args) + '\nEXIT: ' + str(result.returncode) + '\n' + result.stdout + result.stderr)
    return result

def build():
    result = dbt('run', '--select', 'path:models/staging')
    assert result.returncode == 0, result.stdout + result.stderr

def test_split_tender_uses_summed_type_values(staging):
    with staging.begin() as conn:
        conn.execute(text('DELETE FROM order_payments'))
        conn.execute(text("INSERT INTO order_payments VALUES (:order,1,'voucher',1,30),(:order,2,'voucher',1,30),(:order,3,'credit_card',1,50)"), {'order': 'b' * 32})
    build()
    with staging.connect() as conn:
        assert conn.execute(text('SELECT total_payment_value, favorite_payment_type, used_voucher, payment_row_count FROM stg_order_payments')).one() == (110, 'voucher', True, 3)

def test_payment_tie_is_alphabetical_and_source_order_independent(staging):
    with staging.begin() as conn:
        conn.execute(text('DELETE FROM order_payments'))
        conn.execute(text("INSERT INTO order_payments VALUES (:order,1,'voucher',1,60),(:order,2,'credit_card',1,60)"), {'order': 'b' * 32})
    build()
    with staging.connect() as conn:
        assert conn.execute(text('SELECT total_payment_value, favorite_payment_type FROM stg_order_payments')).one() == (120, 'credit_card')
    with staging.begin() as conn:
        conn.execute(text('UPDATE order_payments SET payment_sequential = 3-payment_sequential'))
    with staging.connect() as conn:
        assert conn.execute(text('SELECT total_payment_value, favorite_payment_type FROM stg_order_payments')).one() == (120, 'credit_card')

def test_required_staging_column_types_and_grains(staging):
    with staging.begin() as conn:
        conn.execute(text("ALTER TABLE products ALTER COLUMN product_weight_g TYPE text, ALTER COLUMN product_length_cm TYPE text, ALTER COLUMN product_height_cm TYPE text, ALTER COLUMN product_width_cm TYPE text"))
    build()
    expected = {
        'stg_customers': [('customer_id','text'),('customer_unique_id','text'),('customer_zip_code_prefix','integer'),('customer_city','text'),('customer_state','text')],
        'stg_orders': [('order_id','text'),('customer_id','text'),('order_status','text'),('order_purchase_ts','timestamp without time zone'),('order_approved_ts','timestamp without time zone'),('order_delivered_carrier_ts','timestamp without time zone'),('order_delivered_customer_ts','timestamp without time zone'),('order_estimated_delivery_ts','timestamp without time zone')],
        'stg_products': [('product_id','text'),('product_category_name','text'),('category_english','text'),('product_weight_g','numeric'),('product_length_cm','numeric'),('product_height_cm','numeric'),('product_width_cm','numeric')],
    }
    with staging.connect() as conn:
        for relation, columns in expected.items():
            actual = conn.execute(text('SELECT column_name,data_type FROM information_schema.columns WHERE table_schema=\'public\' AND table_name=:relation ORDER BY ordinal_position'), {'relation':relation}).all()
            assert actual == columns


def test_negative_payment_cannot_hide_inside_positive_aggregate(staging):
    with staging.begin() as conn:
        conn.execute(text("UPDATE order_payments SET payment_value=-1"))
        conn.execute(text("INSERT INTO order_payments VALUES (:order,2,'voucher',1,20)"), {'order': 'b'*32})
    build()
    result = dbt('test','--select','assert_nonnegative_raw_payments')
    assert result.returncode != 0, result.stdout + result.stderr
