"""Export the dbt-owned feature eligibility census and bounded candidate evidence."""

import argparse
import json
from pathlib import Path

from sqlalchemy import text, inspect
from arrow_loaders import iter_sql_frames
from upload_data import get_db_engine, public_error


def load_feature_census(connection):
    """Return reconciled aggregate evidence from the same candidates as the mart."""
    if not inspect(connection).has_table("customer_feature_diagnostics") or not inspect(
        connection
    ).has_table("customer_features"):
        raise ValueError("Feature mart/diagnostics absent; run dbt first")
    populations = {
        name: dict(
            total=0,
            positive=0,
            mature_positive=0,
            early_positive=0,
            negative=0,
            uncertain=0,
        )
        for name in ["all", "eligible", "excluded"]
    }
    for eligible, label, complete, count in connection.execute(
        text(
            "SELECT is_eligible,repeat_within_180_days,has_complete_followup,count(*) FROM customer_feature_diagnostics GROUP BY 1,2,3"
        )
    ):
        for population in ["all", "eligible" if eligible else "excluded"]:
            totals = populations[population]
            totals["total"] += count
            if label == 1:
                totals["positive"] += count
                totals["mature_positive" if complete else "early_positive"] += count
            else:
                totals["negative" if label == 0 else "uncertain"] += count

    def reason_counts(column, predicate="true"):
        return dict(
            connection.execute(
                text(
                    f"SELECT reason,count(*) FROM customer_feature_diagnostics CROSS JOIN LATERAL unnest({column}) reason WHERE {predicate} GROUP BY reason ORDER BY reason"
                )
            ).all()
        )

    def patterns(column, predicate="true"):
        return dict(
            connection.execute(
                text(
                    f"SELECT array_to_string({column},'|'),count(*) FROM customer_feature_diagnostics WHERE cardinality({column})>0 AND {predicate} GROUP BY 1 ORDER BY 1"
                )
            ).all()
        )

    metadata = (
        connection.execute(
            text(
                "SELECT DISTINCT observation_end_ts,observation_end_provenance,as_of_date FROM customer_feature_diagnostics"
            )
        )
        .mappings()
        .all()
    )
    if len(metadata) > 1:
        raise ValueError("Inconsistent feature configuration; rebuild dbt")
    actual_mart = connection.execute(
        text("SELECT count(*) FROM customer_features")
    ).scalar_one()
    mismatch = connection.execute(
        text(
            "SELECT count(*) FROM customer_feature_diagnostics d FULL JOIN customer_features m USING(customer_unique_id) WHERE (d.is_eligible AND m.customer_unique_id IS NULL) OR (m.customer_unique_id IS NOT NULL AND NOT coalesce(d.is_eligible,false))"
        )
    ).scalar_one()
    if actual_mart != populations["eligible"]["total"] or mismatch:
        raise ValueError("Mart and diagnostic eligibility disagree; rebuild dbt")
    return dict(
        candidates=populations["all"]["total"],
        eligible=populations["eligible"]["total"],
        excluded=populations["excluded"]["total"],
        populations=populations,
        exclusion_reasons=reason_counts("exclusion_reasons"),
        exclusion_patterns=patterns("exclusion_reasons"),
        warning_reasons=reason_counts("warning_reasons"),
        warning_patterns=patterns("warning_reasons"),
        retained_warning_reasons=reason_counts("warning_reasons", "is_eligible"),
        retained_warning_patterns=patterns("warning_reasons", "is_eligible"),
        retained_warning_customers=connection.execute(
            text(
                "SELECT count(*) FROM customer_feature_diagnostics WHERE is_eligible AND cardinality(warning_reasons)>0"
            )
        ).scalar_one(),
        recovered_spend_candidates=connection.execute(
            text(
                "SELECT count(*) FROM customer_feature_diagnostics WHERE spend_recovered_from_items"
            )
        ).scalar_one(),
        configuration=dict(metadata[0]) if metadata else {},
        timestamp_interpretation="Timezone-naive source timestamps; no timezone assigned. Recency and lateness use calendar dates.",
        counting_policy="Each population and pattern counts a customer once. Reason counts overlap and must not be added as a union.",
        observation_assumption="The default maximum purchase assumes extract coverage through that timestamp; it does not prove coverage.",
        selection_bias="Early observed positives are labeled before complete follow-up; unfinished non-repeat customers remain uncertain.",
    )


def export_feature_diagnostics(output_dir):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    engine = get_db_engine()
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as conn:
            with conn.begin():
                census = load_feature_census(conn)
                # Separate bounded parts avoid guessing nullable Arrow schemas from the first batch.
                for stale in output.glob("candidates-*.parquet"):
                    stale.unlink()
                for index, frame in enumerate(
                    iter_sql_frames(
                        text(
                            "SELECT * FROM customer_feature_diagnostics ORDER BY customer_unique_id"
                        ),
                        conn,
                    )
                ):
                    frame.to_parquet(
                        output / f"candidates-{index:05d}.parquet", index=False
                    )
                (output / "census.json").write_text(
                    json.dumps(census, indent=2, default=str) + "\n", encoding="utf-8"
                )
        return census
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default="reports/feature_diagnostics")
    args = parser.parse_args()
    try:
        census = export_feature_diagnostics(args.output_dir)
        print(
            f"Exported {census['candidates']} candidates, {census['eligible']} eligible and {census['excluded']} excluded customers to {args.output_dir}"
        )
        return 0
    except ValueError as exc:
        print(str(exc))
        return 1
    except Exception as exc:
        print(public_error(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
