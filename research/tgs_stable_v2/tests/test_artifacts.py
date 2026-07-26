from __future__ import annotations

from pathlib import Path

import pandas as pd

from tgs_stable_v2.artifacts import write_csv, write_json


def test_artifacts_are_byte_reproducible(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        [
            {"ticker": "6273.T", "date": "2024-01-02", "value": 1.23456789123},
            {"ticker": "6301.T", "date": "2024-01-03", "value": None},
        ]
    )
    first_csv = tmp_path / "first.csv"
    second_csv = tmp_path / "second.csv"
    first_json = tmp_path / "first.json"
    second_json = tmp_path / "second.json"
    write_csv(first_csv, frame)
    write_csv(second_csv, frame)
    payload = {"b": 2, "a": [1, None]}
    write_json(first_json, payload)
    write_json(second_json, payload)
    assert first_csv.read_bytes() == second_csv.read_bytes()
    assert first_json.read_bytes() == second_json.read_bytes()


def test_artifacts_do_not_contain_secret_fields(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    write_json(path, {"model_id": "tgs_stable_v2_universe_lab", "token_accessed": False})
    text = path.read_text(encoding="utf-8")
    assert "sk-" not in text
    assert "gho_" not in text
    assert "service_account" not in text
