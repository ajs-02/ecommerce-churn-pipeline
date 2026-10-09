# ecommerce_transform

dbt project on PostgreSQL for the Olist repeat-order exploration. Staging models clean the nine-table extract; `customer_features` is the customer-grain ML mart. T04 SQL implements the inclusive all-status 180-day target, seconds-based anchor features and the shared eligibility census in [the specification](../docs/project_spec.md).

Staging is views; the mart is a table. Frozen recency uses `var('as_of_date')` when set, otherwise the latest purchase date in the extract. The planned prediction history is separate from the feature mart. Power BI remains unedited and its refresh may break after AOV removal and seconds/recency column renames.

```
dbt run
dbt test
dbt docs generate
```

Profiles read `POSTGRES_*` from the environment. See the repo root README for setup and design notes.

T03 staging is verified through real dbt on disposable PostgreSQL. See [ERD cardinalities](../docs/erd.md). To check staging independently before building the mart, use `dbt run --select path:models/staging` then `dbt test --select path:models/staging tag:staging --indirect-selection cautious`. Full `dbt test` includes mart assertions and requires the mart to exist.

`customer_feature_diagnostics` retains one candidate per first-delivered customer before exclusions, with original timestamps and overlapping exclusion/warning arrays. `customer_features` selects eligible candidates; incomplete follow-up without a repeat remains NULL, while early observed repeats are positive. Recency and lateness preserve calendar-date semantics; elapsed seconds retain fractions. Raw negative/non-finite monetary values and invalid observation/recency overrides abort feature publication. Use `dbt build` for all source/staging/mart integrity tests. `observation_end_ts` defaults to the all-status maximum purchase timestamp; an override cannot precede recorded purchases. Export with `python scripts/export_feature_diagnostics.py --output-dir reports/feature_diagnostics` from the repository root.
