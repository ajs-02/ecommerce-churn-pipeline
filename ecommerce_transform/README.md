# ecommerce_transform

dbt project on PostgreSQL for the Olist repeat-buyer pipeline. Typed staging models clean the nine-table extract; `customer_features` is the customer-grain mart used for training and the Power BI score table.

Staging is views; the mart is a table. Recency uses `var('as_of_date')` when set, otherwise the latest purchase date in the extract.

```
dbt run
dbt test
dbt docs generate
```

Profiles read `POSTGRES_*` from the environment. See the repo root README for setup and design notes.
