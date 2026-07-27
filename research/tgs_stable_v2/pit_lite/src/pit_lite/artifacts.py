from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .safety import SafetyError, assert_aggregate_mapping


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    assert_aggregate_mapping(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )


def _validate_csv_rows(rows: list[Mapping[str, Any]]) -> list[str]:
    if not rows:
        raise SafetyError("aggregate CSV must have at least one row")
    columns = list(rows[0])
    column_set = set(columns)
    for row in rows:
        if set(row) != column_set:
            raise SafetyError("aggregate CSV rows must have identical columns")
        assert_aggregate_mapping(row)
    return columns


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    materialized = list(rows)
    columns = _validate_csv_rows(materialized)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(materialized)
