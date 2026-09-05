# Olist Repeat Buyer Propensity Pipeline

End-to-end data science project for an entry-level analytics and modeling portfolio. The goal is to score one-time buyers on the Brazilian Olist marketplace by how likely they are to purchase again, so marketing can focus retention spend on high-propensity customers.

The work is a full pipeline, not a single notebook: raw extract, warehouse, tested transformations, a leakage-aware feature mart, a prediction layer, a Power BI dashboard, and CI/CD.

## Scale

The Kaggle Olist extract is production-shaped, not a toy table.

- About 100,000 orders and 96,000 unique customers across nine related tables (customers, orders, items, payments, reviews, products, sellers, geolocation, category translation)
- Repeat buyers are roughly 3% of customers, so accuracy is the wrong headline metric
- Split tenders, missing lifecycle timestamps, and a small number of source-quality issues are handled in SQL rather than ignored

## Design

A few choices keep the score honest for one-time buyers:

- **First-order window.** Predictors come from the first delivered order only. Lifetime order count is the label source and is never a model input.
- **Frozen recency.** Days since purchase are measured against a fixed as-of date, not `current_date` or the last order.
- **No label reconstruction.** Spend, payment type, voucher use, items, freight, reviews, and delivery times are not computed from later orders. Average order value is kept for the dashboard; it is not passed into the model alongside spend.
- **Warehouse-owned features.** Typed dbt staging, one customer-grain mart, and imputation with missingness flags live in Postgres. Python trains and writes scores; it does not redefine the feature window.
- **Imbalance.** Training uses SMOTE on the train split only, plus XGBoost `scale_pos_weight`. Evaluation is PR-AUC, F1, and a confusion matrix.

Local development uses CSVs and/or local Postgres. The same models run against Heroku Postgres for the live dashboard.

## Stack

| Layer | Tools |
| --- | --- |
| Ingest and analysis | Python, Pandas, PyArrow, SQLAlchemy |
| Warehouse | PostgreSQL (local and Heroku) |
| Transform | dbt (`ecommerce_transform/`) |
| Model | scikit-learn, XGBoost, imbalanced-learn |
| Dashboard | Power BI on the scored Postgres table |
| Quality | dbt tests, pytest |
| Automation | GitHub Actions (train and rescore on push to `main` and a weekly schedule) |

The prediction layer trains on `customer_features`, upserts repeat-purchase probabilities into Postgres, and is what Power BI reads. CI/CD retrains against the cloud database using repository secrets; it does not replace local development.

## Layout

```
data/                    # Olist CSVs (not committed)
scripts/                 # upload, validation, connection check
ecommerce_transform/     # dbt staging + customer_features mart
```

## Local setup

1. Create a virtual environment and install `requirements.txt`.
2. Copy `.env.example` to `.env` and point it at local or Heroku Postgres.
3. Place the Olist CSVs in `data/`.
4. Load them with `python scripts/upload_data.py`, then confirm row counts with `python scripts/validate_upload.py`.
5. From `ecommerce_transform/`, run `dbt run` and `dbt test` (set `DBT_PROFILES_DIR` as in `.env.example`).
