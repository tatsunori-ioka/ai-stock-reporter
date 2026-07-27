from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from pit_lite.acquisition import _records as acquisition_records
from pit_lite.pipeline import _records as pipeline_records


@pytest.mark.parametrize("records", [acquisition_records, pipeline_records])
def test_dataframe_records_convert_nan_nat_and_pd_na_to_json_safe_none(
    records,
) -> None:
    frame = pd.DataFrame(
        {
            "Date": pd.to_datetime(["2024-01-02", None]),
            "metric": [1.25, np.nan],
            "nullable_count": pd.Series([7, pd.NA], dtype="Int64"),
            "label": ["ok", None],
        }
    )

    converted = records(frame)

    assert converted == [
        {
            "Date": "2024-01-02",
            "metric": 1.25,
            "nullable_count": 7,
            "label": "ok",
        },
        {
            "Date": None,
            "metric": None,
            "nullable_count": None,
            "label": None,
        },
    ]
    # This is the exact strict mode used by the private JSON writers.
    json.dumps(converted, allow_nan=False)
