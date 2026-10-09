"""Narrow Arrow statistics adapter for ydata-profiling 4.18.4."""

import pandas as pd
from scipy import stats
from ydata_profiling import ProfileReport
from ydata_profiling.model.pandas.describe_numeric_pandas import (
    pandas_describe_numeric_1d,
)


class _ArrowStatisticsSeries(pd.Series):
    @property
    def _constructor(self):
        return _ArrowStatisticsSeries

    def kurt(self, *args, **kwargs):
        values = self.dropna().to_numpy(dtype=float)
        if len(values) < 4:
            return float("nan")
        return (
            0.0
            if self.nunique() == 1
            else stats.kurtosis(values, fisher=True, bias=False)
        )

    def skew(self, *args, **kwargs):
        values = self.dropna().to_numpy(dtype=float)
        if len(values) < 3:
            return float("nan")
        return 0.0 if self.nunique() == 1 else stats.skew(values, bias=False)


def _describe_numeric(config, series, summary):
    # pandas Arrow arrays lack kurt/skew. All other storage/reductions remain Arrow.
    return pandas_describe_numeric_1d(config, _ArrowStatisticsSeries(series), summary)


def write_profile(frame, path, title):
    schema = {
        name: "DateTime"
        for name in frame
        if pd.api.types.is_datetime64_any_dtype(frame[name].dtype)
    }
    profile = ProfileReport(
        frame,
        title=title,
        minimal=True,
        progress_bar=False,
        type_schema=schema,
        pool_size=1,
        samples={"head": 0, "tail": 0},
    )
    # Public customization hook; keep inherited count/missingness summarizers.
    profile.summarizer.summary_map["Numeric"][-1] = _describe_numeric
    profile.to_file(path)
    description = profile.get_description()
    return {
        name: {
            "type": values["type"],
            "rows": int(values["n"]),
            "missing": int(values["n_missing"]),
            **({"zero": int(values["n_zeros"])} if "n_zeros" in values else {}),
        }
        for name, values in description.variables.items()
    }
