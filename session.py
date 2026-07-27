"""
session.py — NSE trading session utilities.

NSE equity cash session is 09:15 – 15:30 IST, Monday to Friday, minus
exchange holidays. All OHLCV dataframes in this project store timestamps
as timezone-aware UTC; session logic converts to IST only when needed.

IST is UTC+5:30 — so NSE open at 09:15 IST = 03:45 UTC, close at 15:30
IST = 10:00 UTC. At a 15-minute timeframe there are 25 candles per
trading day (03:45, 04:00, ..., 09:45 UTC — the 09:45 candle being the
one that closes at 10:00 UTC / 15:30 IST).
"""

from __future__ import annotations

from datetime import time, date, timezone, timedelta
from functools import lru_cache

import pandas as pd

# Pandas 3.x prefers zoneinfo over pytz. Use zoneinfo if available (Python 3.9+),
# fall back to pytz for older environments.
try:
    import zoneinfo
    IST = zoneinfo.ZoneInfo("Asia/Kolkata")
    UTC = timezone.utc
except (ImportError, Exception):
    import pytz
    IST = pytz.timezone("Asia/Kolkata")
    UTC = pytz.UTC

NSE_OPEN_IST = time(9, 15)
NSE_CLOSE_IST = time(15, 30)
NSE_OPEN_UTC = time(3, 45)      # 9:15 IST
NSE_CLOSE_UTC = time(10, 0)     # 15:30 IST
LAST_15M_CANDLE_OPEN_UTC = time(9, 45)  # the final 15m bar opens at 15:15 IST


def ensure_utc(df: pd.DataFrame) -> pd.DataFrame:
    """Return df with a UTC-aware `date` column. Accepts naive or tz-aware input."""
    df = df.copy()
    if "date" not in df.columns:
        raise ValueError("Dataframe must have a 'date' column")
    if df["date"].dt.tz is None:
        # Assume naive timestamps are already UTC (Kite returns IST; we convert at fetch time)
        df["date"] = df["date"].dt.tz_localize("UTC")
    else:
        df["date"] = df["date"].dt.tz_convert("UTC")
    return df


def add_session_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enriches an intraday NSE dataframe with per-candle session metadata.

    Adds columns:
        ist_date         — IST calendar date of the candle (python date)
        ist_time         — IST clock time of the candle (python time)
        session_first    — 1 if this candle is the first of its trading day, else 0
        session_last     — 1 if this candle is the last of its trading day, else 0
        minutes_into_session — minutes since 09:15 IST (0 for the opening candle)

    Works for 15m / 5m / 1m intraday data. A no-op on daily data (session_first
    and session_last both become 1 on every row, which is technically correct).
    """
    df = ensure_utc(df)
    ist = df["date"].dt.tz_convert(IST)
    df["ist_date"] = ist.dt.date
    df["ist_time"] = ist.dt.time

    ist_naive = ist.dt.tz_localize(None)
    open_dt = ist_naive.dt.normalize() + pd.Timedelta(hours=9, minutes=15)
    df["minutes_into_session"] = ((ist_naive - open_dt).dt.total_seconds() / 60).astype(int)

    # First and last candle per trading day
    df["session_first"] = 0
    df["session_last"] = 0
    idx_first = df.groupby("ist_date", sort=False)["date"].idxmin()
    idx_last = df.groupby("ist_date", sort=False)["date"].idxmax()
    df.loc[idx_first, "session_first"] = 1
    df.loc[idx_last, "session_last"] = 1

    return df


@lru_cache(maxsize=16)
def nse_holidays(year: int) -> frozenset[date]:
    """Return the set of NSE holiday dates for a given year."""
    try:
        import pandas_market_calendars as mcal
    except ImportError:
        return frozenset()

    try:
        cal = mcal.get_calendar("NSE")
        holidays = cal.holidays().holidays
        return frozenset(h for h in holidays if hasattr(h, "year") and h.year == year)
    except Exception:
        return frozenset()


def filter_trading_hours(df: pd.DataFrame) -> pd.DataFrame:
    """
    Remove rows outside NSE trading hours (belt-and-braces for data sources
    that may return pre/post-market candles). Applied to intraday data only.
    """
    df = ensure_utc(df)
    ist_time = df["date"].dt.tz_convert(IST).dt.time
    mask = (ist_time >= NSE_OPEN_IST) & (ist_time <= NSE_CLOSE_IST)
    return df[mask].reset_index(drop=True)


def session_date(ts: pd.Timestamp) -> date:
    """Return the IST calendar date of a UTC timestamp."""
    if ts.tz is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert(IST).date()


if __name__ == "__main__":
    # Quick self-test with synthetic 15-minute NIFTYBEES data
    import numpy as np

    start = pd.Timestamp("2025-10-13 03:45", tz="UTC")   # Monday 9:15 IST
    end = pd.Timestamp("2025-10-14 10:00", tz="UTC")     # Tuesday 15:30 IST
    dates = pd.date_range(start, end, freq="15min")

    df = pd.DataFrame({
        "date": dates,
        "open": np.random.uniform(245, 250, len(dates)),
        "high": np.random.uniform(245, 250, len(dates)),
        "low":  np.random.uniform(245, 250, len(dates)),
        "close": np.random.uniform(245, 250, len(dates)),
        "volume": np.random.randint(1000, 10000, len(dates)),
    })

    # Drop candles outside NSE hours (date_range above is naive to session)
    df = filter_trading_hours(df)
    df = add_session_columns(df)

    print(f"rows: {len(df)}")
    print(f"unique ist_dates: {df['ist_date'].nunique()}")
    print(f"session_first sum: {df['session_first'].sum()}")
    print(f"session_last sum: {df['session_last'].sum()}")
    assert df["session_first"].sum() == df["session_last"].sum() == df["ist_date"].nunique()
    print(f"first candle IST times: {df[df['session_first'] == 1]['ist_time'].unique()}")
    print(f"last candle IST times:  {df[df['session_last'] == 1]['ist_time'].unique()}")
    print("session.py self-test OK")
