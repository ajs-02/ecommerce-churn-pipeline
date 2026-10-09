"""Bounded Arrow-backed reads, preserving raw CSV values as strings."""

import pandas as pd


def iter_csv_frames(path, *, chunksize=50000):
    if chunksize <= 0:
        raise ValueError("chunksize must be positive")
    yield from pd.read_csv(
        path,
        engine="c",
        dtype_backend="pyarrow",
        dtype="string[pyarrow]",
        keep_default_na=False,
        na_values=[""],
        chunksize=chunksize,
    )


def iter_sql_frames(query, connection, *, chunksize=50000):
    if chunksize <= 0:
        raise ValueError("chunksize must be positive")
    yield from pd.read_sql(
        query,
        connection.execution_options(stream_results=True),
        dtype_backend="pyarrow",
        chunksize=chunksize,
    )
