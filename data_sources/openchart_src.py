"""
data_sources/openchart_src.py — OpenChart wrapper for NSE historical data.

Standalone, no broker account, pulls from NSE's own public charting APIs
via the `openchart` package. Used as a fallback when Kite is unavailable
or as a cross-validation source during fetch verification.

Note: OpenChart is unofficial. NSE can change its chart endpoints and
break this path without warning. Kite remains the primary source for
production research; OpenChart is the "no credentials" safety net.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import pytz

IST = pytz.timezone("Asia/Kolkata")

# OpenChart interval mapping (their strings → Kite-style strings we use internally)
OPENCHART_INTERVAL_MAP = {
    "minute": "1m",
    "5minute": "5m",
    "10minute": "10m",
    "15minute": "15m",
    "30minute": "30m",
    "60minute": "1h",
    "hour": "1h",
    "day": "1d",
    "week": "1w",
}


class OpenChartDataSource:
    def __init__(self):
        try:
            from openchart import NSEData
        except ImportError as e:
            raise RuntimeError(
                "openchart not installed. Run `pip install openchart`."
            ) from e
        self.nse = NSEData()
        self.nse.download()  # populates symbol master; needed before queries

    def fetch(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        exchange: str = "NSE",
    ) -> pd.DataFrame:
        """Fetch historical data for a symbol and return the standard dataframe format."""
        if interval not in OPENCHART_INTERVAL_MAP:
            raise ValueError(f"Interval {interval!r} not supported by OpenChart wrapper")

        oc_interval = OPENCHART_INTERVAL_MAP[interval]
        if end is None:
            end = datetime.now()
        if start is None:
            start = end - timedelta(days=365 * 2)

        # OpenChart wants segment: 'NSE' for equities, 'IDX' for indices
        # Index instruments are stored in NSE_IDX exchange code
        segment = "NSE"
        sym = symbol
        if "NIFTY" in symbol.upper() and "BEES" not in symbol.upper():
            segment = "NSE_IDX"
            sym = symbol.replace("_", " ")

        df = self.nse.historical(
            symbol=sym,
            exchange=segment,
            start=pd.Timestamp(start),
            end=pd.Timestamp(end),
            interval=oc_interval,
        )

        if df is None or len(df) == 0:
            raise RuntimeError(f"OpenChart returned no data for {symbol} {interval}")

        # Normalize columns: openchart returns 'Timestamp, Open, High, Low, Close, Volume'
        df = df.reset_index()
        rename_map = {
            "Timestamp": "date",
            "Date": "date",
            "Datetime": "date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
        df = df.rename(columns=rename_map)

        if df["date"].dt.tz is None:
            df["date"] = df["date"].dt.tz_localize(IST)
        df["date"] = df["date"].dt.tz_convert("UTC")

        df = df[["date", "open", "high", "low", "close", "volume"]]
        df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        return df
