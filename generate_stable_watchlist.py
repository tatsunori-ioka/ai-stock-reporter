from __future__ import annotations

import csv
from pathlib import Path


STRONG_SECTORS = {
    "Trading companies",
    "Machinery",
    "Nonferrous metals",
    "Real estate",
    "Shipbuilding",
}

INPUT_PATH = Path("stable_universe_metadata.csv")
OUTPUT_PATH = Path("tradingview_stable_watchlist.csv")
OUTPUT_COLUMNS = ["symbol", "ticker", "code", "name", "sector", "market_cap", "market_cap_bucket"]


def main() -> None:
    with INPUT_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    stable_rows = [
        row
        for row in rows
        if row.get("market_cap_bucket") == "Large" and row.get("sector") in STRONG_SECTORS
    ]
    stable_rows.sort(key=lambda row: (row.get("sector", ""), row.get("code", "")))

    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        for row in stable_rows:
            writer.writerow(
                {
                    "symbol": f"TSE:{row.get('code', '')}",
                    "ticker": row.get("ticker", ""),
                    "code": row.get("code", ""),
                    "name": row.get("name", ""),
                    "sector": row.get("sector", ""),
                    "market_cap": row.get("market_cap", ""),
                    "market_cap_bucket": row.get("market_cap_bucket", ""),
                }
            )

    print(f"Wrote {OUTPUT_PATH} rows={len(stable_rows)}")


if __name__ == "__main__":
    main()
