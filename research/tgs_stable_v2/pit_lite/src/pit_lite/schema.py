from __future__ import annotations

import re
from typing import Any, Iterable, Mapping

import pandas as pd


MASTER_FIELDS = ("Date", "Code", "ProdCat", "Mkt", "S33", "S33Nm", "CoName")
BAR_FIELDS = (
    "Date",
    "Code",
    "O",
    "H",
    "L",
    "C",
    "Vo",
    "Va",
    "AdjFactor",
    "AdjO",
    "AdjH",
    "AdjL",
    "AdjC",
    "AdjVo",
)
NUMERIC_BAR_FIELDS = BAR_FIELDS[2:]
SECURITY_CODE_PATTERN = re.compile(r"[0-9A-Z]{5}")


def validate_security_code(value: Any) -> str:
    code = str(value).strip()
    if not SECURITY_CODE_PATTERN.fullmatch(code):
        raise ValueError(
            "security code must be exactly five uppercase ASCII letters or digits"
        )
    return code


def normalize_master(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows))
    missing = [field for field in ("Date", "Code", "Mkt", "S33") if field not in frame]
    if missing:
        raise ValueError(f"master schema is missing fields: {missing}")
    for optional in ("ProdCat", "S33Nm", "CoName"):
        if optional not in frame:
            frame[optional] = ""
    result = frame.loc[:, MASTER_FIELDS].copy()
    result["Date"] = pd.to_datetime(result["Date"], errors="raise").dt.tz_localize(None)
    for column in MASTER_FIELDS[1:]:
        result[column] = result[column].fillna("").astype(str).str.strip()
    result["Code"] = result["Code"].map(validate_security_code)
    result = result.drop_duplicates(["Date", "Code"], keep="last")
    return result.sort_values(["Date", "Code"], ignore_index=True)


def normalize_bars(rows: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(list(rows))
    missing = [field for field in BAR_FIELDS if field not in frame]
    if missing:
        raise ValueError(f"bar schema is missing fields: {missing}")
    result = frame.loc[:, BAR_FIELDS].copy()
    result["Date"] = pd.to_datetime(result["Date"], errors="raise").dt.tz_localize(None)
    result["Code"] = result["Code"].fillna("").astype(str).str.strip()
    result["Code"] = result["Code"].map(validate_security_code)
    result[list(NUMERIC_BAR_FIELDS)] = result[list(NUMERIC_BAR_FIELDS)].apply(
        pd.to_numeric,
        errors="coerce",
    )
    result = result.drop_duplicates(["Date", "Code"], keep="last")
    return result.sort_values(["Code", "Date"], ignore_index=True)


def price_frame(bars: pd.DataFrame, basis: str) -> pd.DataFrame:
    if basis not in {"adjusted", "raw"}:
        raise ValueError("basis must be adjusted or raw")
    prefix = "Adj" if basis == "adjusted" else ""
    mapping = {
        f"{prefix}O": "Open",
        f"{prefix}H": "High",
        f"{prefix}L": "Low",
        f"{prefix}C": "Close",
        f"{prefix}Vo": "Volume",
    }
    result = bars.set_index("Date")[list(mapping)].rename(columns=mapping).copy()
    result.index = pd.to_datetime(result.index).tz_localize(None)
    result = result[~result.index.duplicated(keep="last")].sort_index()
    return result
