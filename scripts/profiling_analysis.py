"""Shared PostgreSQL profiling and repeat-order analysis."""

import html
import json
import shutil
import sys
import tempfile
from pathlib import Path

import pandas as pd
from sqlalchemy import text
from arrow_loaders import iter_sql_frames
from dataset_manifest import SCHEMAS
from export_feature_diagnostics import load_feature_census
from upload_data import get_db_engine, table_name_for

RAW_TABLES = tuple(table_name_for(name) for name in SCHEMAS)
NUMERIC_PREDICTORS = (
    "total_spent",
    "seconds_since_first_purchase",
    "item_count",
    "freight_value",
    "delivery_seconds",
    "approval_seconds",
    "carrier_seconds",
    "after_estimated_delivery_seconds",
)


def load_relation(connection, table):
    if table not in (*RAW_TABLES, "customer_features"):
        raise ValueError("Unsupported profile relation")
    # Bounded ingestion; ydata itself requires one complete table at a time.
    return pd.concat(
        iter_sql_frames(text(f'SELECT * FROM "{table}"'), connection), ignore_index=True
    )


def table_summary(frame):
    columns = {}
    for name in frame:
        series = frame[name]
        valid = series.dropna()
        distinct = int(valid.nunique())
        column = {
            "dtype": str(series.dtype),
            "missing": int(series.isna().sum()),
            "distinct": distinct,
            "unique": bool(series.is_unique),
            "zero_variance": distinct == 1,
        }
        if pd.api.types.is_numeric_dtype(
            series.dtype
        ) and not pd.api.types.is_bool_dtype(series.dtype):
            column.update(
                zero=int((valid == 0).sum()),
                negative=int((valid < 0).sum()),
                min=float(valid.min()) if len(valid) else None,
                max=float(valid.max()) if len(valid) else None,
            )
        columns[name] = column
    return {"rows": len(frame), "columns": columns}


def write_index(output, summary):
    links = "".join(
        f'<li><a href="profiles/{name}.html">{name}</a> ({values["rows"]:,} rows)</li>'
        for name, values in summary["tables"].items()
    )
    content = f"""<!doctype html><html lang="en"><meta charset="utf-8"><title>Olist profiles and repeat-order EDA</title>
    <style>body{{font:16px system-ui;max-width:1100px;margin:40px auto;padding:20px}}pre{{white-space:pre-wrap}}img{{max-width:100%}}</style>
    <h1>Olist profiles and repeat-order EDA</h1><p>PostgreSQL source, Arrow-backed ingestion. Profiles use ydata-profiling.</p>
    <h2>Table profiles</h2><ul>{links}</ul>
    <h2>Eligibility, exclusions, warnings and target census</h2><p>Known labels include early observed positives. Uncertain customers are separate, never negatives. Reason counts overlap; population and exclusive-pattern counts count each customer once.</p>
    <p>Historical post-purchase associations do not establish prospective or causal performance. Early positives favor fast observed repeats; the maximum purchase timestamp assumes coverage rather than proving it.</p>
    <pre>{html.escape(json.dumps(summary['census'],indent=2,default=str))}</pre>
    <h2>Repeat-order EDA</h2><pre>{html.escape(json.dumps(summary['eda'],indent=2))}</pre>
    {''.join(f'<figure><img src="plots/{name}.png" alt="{name.replace(chr(95),chr(32))}"></figure>' for name in ['delivered_counts','target_distribution','spend_by_target','state_repeat_rates','numeric_correlations','uncertain_spend'])}
    <h2>Types, cardinality, missingness, signs, zeros and ranges</h2><p>Constant columns have zero variance. Large values remain visible without cutoffs. Raw geolocation signs are descriptive, not monetary validity errors.</p>
    <pre>{html.escape(json.dumps(summary['tables'],indent=2,default=str))}</pre></html>"""
    (output / "data_profile_report.html").write_text(content, encoding="utf-8")


def generate_profiles(output_dir):
    from profiling_adapter import write_profile

    requested = Path(output_dir).resolve()
    project = Path(__file__).resolve().parents[1]
    if project.is_relative_to(requested):
        raise ValueError("Report output directory must not contain the project")
    requested.parent.mkdir(parents=True, exist_ok=True)
    engine = get_db_engine()
    try:
        with tempfile.TemporaryDirectory(
            prefix=".profile-staging-", dir=requested.parent
        ) as temporary:
            output = Path(temporary) / "reports"
            with engine.connect().execution_options(
                isolation_level="REPEATABLE READ"
            ) as connection:
                with connection.begin():
                    census = load_feature_census(connection)
                    output.mkdir()
                    (output / "profiles").mkdir()
                    summary = {"source": "PostgreSQL", "census": census, "tables": {}}
                    for table in (*RAW_TABLES, "customer_features"):
                        frame = load_relation(connection, table)
                        if frame.empty:
                            raise ValueError(
                                f"Cannot generate genuine ydata profile for empty table {table}"
                            )
                        summary["tables"][table] = table_summary(frame)
                        summary["tables"][table]["profile_statistics"] = write_profile(
                            frame,
                            output / "profiles" / f"{table}.html",
                            f"Olist {table}",
                        )
                        if table == "customer_features":
                            summary["eda"] = analyze_features(frame, census)
                            write_eda_plots(frame, summary["eda"], output / "plots")
                    (output / "summary.json").write_text(
                        json.dumps(summary, indent=2, default=str), encoding="utf-8"
                    )
                    write_index(output, summary)
            backup = Path(
                tempfile.mkdtemp(prefix=".profile-previous-", dir=requested.parent)
            )
            backup.rmdir()
            previous = requested.exists()
            if previous:
                requested.rename(backup)
            try:
                output.rename(requested)
            except OSError:
                if previous:
                    try:
                        backup.rename(requested)
                    except OSError:
                        raise ValueError(
                            f"Report publication failed; previous reports retained at {backup}"
                        ) from None
                raise
            if backup.exists():
                try:
                    shutil.rmtree(backup)
                except OSError:
                    print(
                        f"Complete reports published; previous backup retained at {backup}",
                        file=sys.stderr,
                    )
            return summary
    finally:
        engine.dispose()


def analyze_features(frame, census):
    known = frame[frame["repeat_within_180_days"].notna()]
    uncertain = frame[frame["repeat_within_180_days"].isna()]
    positive = int((known["repeat_within_180_days"] == 1).sum())
    counts = {
        str(int(key)): int(value)
        for key, value in frame["total_orders"].value_counts().sort_index().items()
    }
    states = []
    for state, group in known.groupby("customer_state"):
        n = len(group)
        repeats = int((group["repeat_within_180_days"] == 1).sum())
        states.append(
            {
                "state": str(state),
                "labeled": n,
                "positive": repeats,
                "repeat_rate": repeats / n,
            }
        )
    states = sorted(states, key=lambda value: (-value["labeled"], value["state"]))[:5]
    spend = {}
    for label in (0, 1):
        group = known[known["repeat_within_180_days"] == label]["total_spent"]
        spend[str(label)] = {
            "count": len(group),
            "mean": float(group.mean()) if len(group) else None,
            "median": float(group.median()) if len(group) else None,
        }
    return {
        "target_distribution": {
            "0": len(known) - positive,
            "1": positive,
            "uncertain": len(uncertain),
        },
        "labeled_denominator": len(known),
        "repeat_rate": positive / len(known) if len(known) else None,
        "early_positive": census["populations"]["eligible"]["early_positive"],
        "delivered_count_distribution": counts,
        "spend_by_target": spend,
        "top_five_states": states,
        "correlation_columns": list(NUMERIC_PREDICTORS),
        "uncertain": {
            "count": len(uncertain),
            "mean_first_order_spend": (
                float(uncertain["total_spent"].mean()) if len(uncertain) else None
            ),
        },
        "state_policy": "Top five states by labeled customer count, ties alphabetical; numerator observed repeats, denominator known labels only.",
        "correlation_population": "All eligible customers, including uncertain labels; numeric predictors only. Constant-column correlations are undefined.",
        "interpretation": "Historical associations using post-purchase features, not causal or proven prospective evidence. Early positives favor fast observed repeats. Uncertain customers are excluded from known-label comparisons.",
    }


def write_eda_plots(frame, eda, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)

    def save(name):
        plt.tight_layout()
        plt.savefig(output / f"{name}.png", dpi=120)
        plt.close()

    plt.figure(figsize=(8, 4))
    counts = eda["delivered_count_distribution"]
    plt.bar(list(counts), list(counts.values()))
    plt.xlabel("Lifetime delivered orders, descriptive only")
    plt.ylabel("Eligible customers")
    save("delivered_counts")
    plt.figure(figsize=(8, 4))
    plt.bar(
        ["Known negative", "Known positive", "Uncertain"],
        [eda["target_distribution"][key] for key in ("0", "1", "uncertain")],
    )
    plt.ylabel("Eligible customers")
    plt.title(
        f"Observed repeat rate {eda['repeat_rate']:.2%} among {eda['labeled_denominator']:,} known labels"
        if eda["repeat_rate"] is not None
        else "No known labels; repeat rate undefined"
    )
    save("target_distribution")
    plt.figure(figsize=(8, 4))
    for label, name in [(0, "Known negative"), (1, "Known positive")]:
        values = (
            frame.loc[frame["repeat_within_180_days"] == label, "total_spent"]
            .dropna()
            .to_numpy(dtype=float)
        )
        if len(values):
            plt.hist(values, bins=30, alpha=0.55, label=f"{name}, n={len(values):,}")
    plt.xlabel("First-order spend, source currency units")
    plt.ylabel("Customers")
    if eda["labeled_denominator"]:
        plt.legend()
    save("spend_by_target")
    plt.figure(figsize=(8, 4))
    states = eda["top_five_states"]
    plt.bar(
        [f"{row['state']}\nn={row['labeled']:,}" for row in states],
        [row["repeat_rate"] for row in states],
    )
    plt.ylim(0, 1)
    plt.ylabel("Observed repeats / labeled customers")
    plt.title("Top five states by known-label denominator")
    save("state_repeat_rates")
    correlations = frame[list(NUMERIC_PREDICTORS)].corr()
    plt.figure(figsize=(10, 9))
    matrix = correlations.to_numpy(dtype=float)
    image = plt.imshow(np.ma.masked_invalid(matrix), vmin=-1, vmax=1, cmap="coolwarm")
    plt.colorbar(image, label="Pearson correlation; blank = undefined")
    plt.xticks(range(len(NUMERIC_PREDICTORS)), NUMERIC_PREDICTORS, rotation=90)
    plt.yticks(range(len(NUMERIC_PREDICTORS)), NUMERIC_PREDICTORS)
    plt.title("Numeric predictors, all eligible customers")
    save("numeric_correlations")
    plt.figure(figsize=(8, 4))
    values = (
        frame.loc[frame["repeat_within_180_days"].isna(), "total_spent"]
        .dropna()
        .to_numpy(dtype=float)
    )
    if len(values):
        plt.hist(values, bins=30, color="gray")
    plt.xlabel("First-order spend of uncertain customers")
    plt.ylabel("Customers")
    plt.title(f"Uncertain cohort, n={len(values):,}; no negative labels assigned")
    save("uncertain_spend")


def generate_eda(output_dir):
    output = Path(output_dir)
    engine = get_db_engine()
    try:
        with engine.connect().execution_options(
            isolation_level="REPEATABLE READ"
        ) as connection:
            with connection.begin():
                census = load_feature_census(connection)
                frame = load_relation(connection, "customer_features")
                eda = analyze_features(frame, census)
                write_eda_plots(frame, eda, output / "plots")
                output.mkdir(parents=True, exist_ok=True)
                result = {"census": census, "eda": eda}
                (output / "eda_summary.json").write_text(
                    json.dumps(result, indent=2, default=str), encoding="utf-8"
                )
                return result
    finally:
        engine.dispose()
