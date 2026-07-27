"""
data_sources/yfinance_src.py — last-resort yfinance wrapper.

Daily-only in practice. yfinance's intraday windows are too short
(~60 days for 15m) to be useful for serious research, and its NSE
reliability in 2026 is degrading (empty dataframes, false 'delisted'
errors on active tickers). Used as emergency fallback only.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

YF_INTERVAL_MAP = {
    "minute": "1m",
    "5minute": "5m",
    "15minute": "15m",
    "30minute": "30m",
    "60minute": "60m",
    "hour": "60m",
    "day": "1d",
    "week": "1wk",
}


class YFinanceDataSource:
    def __init__(self):
        try:
            import yfinance  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "yfinance not installed. Run `pip install yfinance`."
            ) from e

    def fetch(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        exchange: str = "NSE",
    ) -> pd.DataFrame:
        import yfinance as yf

        if interval not in YF_INTERVAL_MAP:
            raise ValueError(f"Interval {interval!r} not supported by yfinance wrapper")

        yf_interval = YF_INTERVAL_MAP[interval]

        # yfinance ticker mapping:
        #   - Equity NSE:   RELIANCE.NS, NIFTYBEES.NS
        #   - BSE:          RELIANCE.BO
        #   - Nifty 50 idx: ^NSEI
        if symbol.upper() in ("NIFTY 50", "NIFTY50", "NIFTY_50", "^NSEI"):
            ticker = "^NSEI"
        elif "." in symbol:
            ticker = symbol
        else:
            ticker = f"{symbol}.NS" if exchange.upper() == "NSE" else f"{symbol}.BO"

        if end is None:
            end = datetime.now()
        if start is None:
            # Daily: plenty of history. Intraday: Yahoo caps.
            if yf_interval == "1d":
                start = end - timedelta(days=365 * 20)
            elif yf_interval in ("60m", "1h"):
                start = end - timedelta(days=700)
            else:
                start = end - timedelta(days=55)

        t = yf.Ticker(ticker)
        df = t.history(start=start, end=end, interval=yf_interval, auto_adjust=True)

        if df is None or len(df) == 0:
            raise RuntimeError(f"yfinance returned no data for {ticker} {yf_interval}")

        df = df.reset_index()
        rename_map = {
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
            df["date"] = df["date"].dt.tz_localize("UTC")
        else:
            df["date"] = df["date"].dt.tz_convert("UTC")

        df = df[["date", "open", "high", "low", "close", "volume"]]
        df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        return df
