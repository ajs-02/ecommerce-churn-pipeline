# ecommerce_transform

dbt project on PostgreSQL for the Olist repeat-order exploration. Staging models clean the nine-table extract; `customer_features` is the customer-grain ML mart. Current SQL has not yet been migrated to the agreed target, seconds-based features, and eligibility policy in [the specification](../docs/project_spec.md).

Staging is views; the mart is a table. Frozen recency uses `var('as_of_date')` when set, otherwise the latest purchase date in the extract. The planned prediction history is separate from the feature mart. Power BI remains unedited and its refresh may break after the planned schema changes.

```
dbt run
dbt test
dbt docs generate
```

Profiles read `POSTGRES_*` from the environment. See the repo root README for setup and design notes.
