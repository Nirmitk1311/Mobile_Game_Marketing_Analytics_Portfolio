"""Run the SQL layer of the analysis (sql/*.sql) on the synthetic data with SQLite (standard library).

Tables loaded: player_metrics (outputs/analysis/<month>/player_metrics.csv, all months) and creative_daily
(data/synthetic/creative_daily_<month>.csv). Each query's result is written to outputs/sql/<query name>.csv.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=Path("data/synthetic"))
    ap.add_argument("--analysis", type=Path, default=Path("outputs/analysis"))
    ap.add_argument("--sql", type=Path, default=Path("sql"))
    ap.add_argument("--output", type=Path, default=Path("outputs/sql"))
    args = ap.parse_args()

    players = pd.concat([pd.read_csv(p) for p in sorted(args.analysis.glob("*/player_metrics.csv"))], ignore_index=True)
    creative = pd.concat([pd.read_csv(p) for p in sorted(args.data.glob("creative_daily_*.csv"))], ignore_index=True)
    con = sqlite3.connect(":memory:")
    players.to_sql("player_metrics", con, index=False)
    creative.to_sql("creative_daily", con, index=False)

    args.output.mkdir(parents=True, exist_ok=True)
    for q in sorted(args.sql.glob("*.sql")):
        result = pd.read_sql_query(q.read_text(encoding="utf-8"), con)
        result.to_csv(args.output / f"{q.stem}.csv", index=False)
        print(f"SQL {q.name}: {len(result)} rows")
    con.close()


if __name__ == "__main__":
    main()
