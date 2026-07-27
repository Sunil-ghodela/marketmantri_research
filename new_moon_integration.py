"""
new_moon_integration.py — Shared New Moon utility for live & backtest.

Provides:
  - Precomputed T-2 windows (entry/exit dates) from daily OHLC data + future predictions
  - is_new_moon_entry_date(date) -> bool  — check if a date is a T-2 entry
  - get_active_new_moon(date) -> dict | None  — current/newest window info
  - get_upcoming_new_moons(n=3) -> list  — next N new moon events
  - new_moon_summary() -> dict  — aggregate stats for dashboard

Future new moons are computed astronomically (swisseph) for up to 12 months ahead,
so the moon calendar works even when price data doesn't extend far enough.

Caches daily data + events on first import. Thread-safe for live use.
"""

from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from datetime import date, timedelta

import pandas as pd

from strategy_new_moon import (
    build_new_moon_events,
    exact_new_moons,
    load_daily_ohlc,
    StrategyNewMoon,
)

HERE = Path(__file__).resolve().parent
DAILY_FILE = HERE / "data" / "NIFTYBEES_1d.feather"
TRADING_TZ = "Asia/Kolkata"
MARKET_CLOSE_HM = (15, 30)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _next_weekday(d: date, forward: bool = True) -> date:
    """Move to the next weekday (Mon-Fri), either forward or backward."""
    while d.weekday() >= 5:  # Sat=5, Sun=6
        d += timedelta(days=1 if forward else -1)
    return d


def _estimate_t2_dates(event_date_ist: date) -> tuple[date, date]:
    """Estimate T-2 entry & exit dates for a given new moon event date.
    
    T-2 means 2 trading days before the event. Since we don't have future
    trading calendars, we use calendar days and skip weekends.
    The entry is ~3 calendar days before, exit ~2 calendar days before.
    """
    entry = event_date_ist - timedelta(days=3)
    exit_d = event_date_ist - timedelta(days=2)
    entry = _next_weekday(entry, forward=True)
    exit_d = _next_weekday(exit_d, forward=True)
    # Ensure entry < exit
    if entry >= exit_d:
        exit_d = _next_weekday(exit_d + timedelta(days=1), forward=True)
    return entry, exit_d


def _compute_future_windows(months_ahead: int = 12) -> list[dict]:
    """Compute upcoming T-2 new moon windows using astronomical predictions.
    
    Uses swisseph to find exact new moon timestamps for the next N months,
    then estimates T-2 entry/exit dates using calendar-based weekday logic.
    
    Returns list of window dicts matching the format of _t2_windows().
    """
    today = date.today()
    start = pd.Timestamp(today - timedelta(days=7), tz="UTC")  # small overlap
    end = pd.Timestamp(today.replace(year=today.year + 1) + timedelta(days=60), tz="UTC")
    
    try:
        future_nms = exact_new_moons(start, end)
    except Exception:
        return []
    
    windows = []
    for ts_utc in future_nms:
        ts_ist = ts_utc.tz_convert(TRADING_TZ)
        event_date = ts_ist.date()
        # Determine trade date: same day if before close, else next trading day
        if (ts_ist.hour, ts_ist.minute) > MARKET_CLOSE_HM:
            event_date = _next_weekday(event_date + timedelta(days=1), forward=True)
        else:
            event_date = _next_weekday(event_date, forward=True)
        
        entry_date, exit_date = _estimate_t2_dates(event_date)
        
        w = {
            "entry_date": entry_date,
            "exit_date": exit_date,
            "new_moon_ist": ts_ist.isoformat(),
            "new_moon_utc": ts_utc.isoformat(),
            "event_trade_date": str(event_date),
            "future_prediction": True,
        }
        windows.append(w)
    
    return windows


# ── Internal cache ──────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _t2_entries() -> frozenset[date]:
    """Return frozenset of all T-2 entry dates (historical + future predictions)."""
    windows, _ = _t2_windows()
    entries = {w["entry_date"] for w in windows}
    return frozenset(entries)


@lru_cache(maxsize=1)
def _t2_windows() -> tuple[list[dict], dict]:
    """Return (windows_list, lookup_by_entry_date) for all T-2 events.

    Combines historical windows from daily data + future astronomical predictions.

    Each window dict:
      entry_date: date
      exit_date: date
      new_moon_ist: str
      new_moon_utc: str
      event_trade_date: str
      future_prediction: bool (True for predicted, False for price-data-based)
    """
    windows = []
    
    # 1) Historical windows from daily data
    daily_path = DAILY_FILE
    if daily_path.exists():
        try:
            daily = load_daily_ohlc(daily_path)
            events = build_new_moon_events(daily)
            trades = StrategyNewMoon(setups=("T-2",)).build_trades(daily, events)
            for _, t in trades.iterrows():
                w = {
                    "entry_date": pd.Timestamp(t["entry_date"]).date(),
                    "exit_date": pd.Timestamp(t["exit_date"]).date(),
                    "new_moon_ist": t.get("new_moon_ist", ""),
                    "new_moon_utc": t.get("new_moon_utc", ""),
                    "event_trade_date": t["event_trade_date"],
                    "future_prediction": False,
                }
                windows.append(w)
        except Exception:
            pass
    
    # 2) Future predictions (astronomical)
    try:
        future = _compute_future_windows(12)
        # Only add future windows that don't overlap with historical ones
        existing_entry_dates = {w["entry_date"] for w in windows}
        for fw in future:
            if fw["entry_date"] not in existing_entry_dates:
                windows.append(fw)
    except Exception:
        pass
    
    # Sort by entry_date
    windows.sort(key=lambda x: x["entry_date"])
    
    lookup = {str(w["entry_date"]): w for w in windows}
    return windows, lookup


# ── Public API ──────────────────────────────────────────────────────────────

def is_new_moon_entry_date(d: date | str | pd.Timestamp) -> bool:
    """Check if *d* is a T-2 New Moon entry date."""
    if isinstance(d, pd.Timestamp):
        d = d.date()
    elif isinstance(d, str):
        d = pd.Timestamp(d).date()
    return d in _t2_entries()


def get_active_new_moon(d: date | str | pd.Timestamp | None = None) -> dict | None:
    """Return the current/newest T-2 New Moon window info, or None.

    If *d* is None, uses today's date.
    """
    if d is None:
        d = date.today()
    elif isinstance(d, pd.Timestamp):
        d = d.date()
    elif isinstance(d, str):
        d = pd.Timestamp(d).date()

    windows, lookup = _t2_windows()
    if not windows:
        return None

    # Direct entry date lookup
    cached = lookup.get(str(d))
    if cached:
        return dict(cached)

    # Find the most recent window that includes this date
    for w in sorted(windows, key=lambda x: x["entry_date"], reverse=True):
        if w["entry_date"] <= d <= w["exit_date"]:
            result = dict(w)
            result["status"] = "active"
            return result

    # Find the next upcoming window
    for w in sorted(windows, key=lambda x: x["entry_date"]):
        if w["entry_date"] > d:
            result = dict(w)
            result["status"] = "upcoming"
            return result

    return None


def get_upcoming_new_moons(n: int = 3) -> list[dict]:
    """Return the next *n* upcoming new moon events with T-2 dates."""
    windows, _ = _t2_windows()
    today = date.today()
    upcoming = [w for w in windows if w["entry_date"] >= today]
    return upcoming[:n]


def new_moon_summary() -> dict:
    """Return aggregate stats for the dashboard panel."""
    windows, _ = _t2_windows()
    active = get_active_new_moon()
    upcoming = get_upcoming_new_moons(8)
    historical = [w for w in windows if not w.get("future_prediction")]
    return {
        "total_windows": len(windows),
        "historical_windows": len(historical),
        "active": active,
        "upcoming": upcoming,
    }


@lru_cache(maxsize=1)
def get_new_moon_trade_timeline() -> list[dict]:
    """Return list of all T-2 backtest trades sorted by entry date.

    Each trade dict:
      entry_date: str (YYYY-MM-DD)
      exit_date: str (YYYY-MM-DD)
      return_pct: float (percentage)
      cum_return_pct: float (cumulative sum of return_pct)
      entry_close: float
      exit_close: float
      trade_num: int (1-based index)
    """
    try:
        daily_path = DAILY_FILE
        if not daily_path.exists():
            return []

        daily = load_daily_ohlc(daily_path)
        events = build_new_moon_events(daily)
        trades = StrategyNewMoon(setups=("T-2",)).build_trades(daily, events)

        if trades.empty:
            return []

        timeline = []
        cum = 0.0
        for i, (_, t) in enumerate(trades.sort_values("entry_date").iterrows()):
            ret = float(t["return_pct"])
            cum += ret
            timeline.append({
                "trade_num": i + 1,
                "entry_date": str(t["entry_date"]),
                "exit_date": str(t["exit_date"]),
                "return_pct": round(ret, 2),
                "cum_return_pct": round(cum, 2),
                "entry_close": round(float(t["entry_close"]), 2),
                "exit_close": round(float(t["exit_close"]), 2),
                "setup": str(t["setup"]),
            })

        return timeline
    except Exception as e:
        return []


@lru_cache(maxsize=1)
def get_new_moon_backtest_stats() -> dict:
    """Run the New Moon T-2 backtest and return actual computed stats.

    Returns dict with:
      total_trades, win_rate_pct, profit_factor, avg_return_pct,
      total_return_pct, max_drawdown_pct, best_trade_pct, worst_trade_pct

    Cached on first call since historical data doesn't change.
    """
    try:
        daily_path = DAILY_FILE
        if not daily_path.exists():
            return {"error": "No daily data file"}

        daily = load_daily_ohlc(daily_path)
        events = build_new_moon_events(daily)
        trades = StrategyNewMoon(setups=("T-2",)).build_trades(daily, events)

        if trades.empty:
            return {"error": "No trades generated"}

        n = len(trades)
        returns = trades["return_pct"]
        total_return = returns.sum()
        avg_return = returns.mean()
        median_return = returns.median()

        wins = returns[returns > 0]
        losses = returns[returns < 0]
        n_wins = len(wins)
        n_losses = len(losses)
        wr = (n_wins / n * 100) if n > 0 else 0.0

        total_gain = wins.sum() if n_wins > 0 else 0.0
        total_loss = abs(losses.sum()) if n_losses > 0 else 1.0
        pf = round(total_gain / total_loss, 2) if total_loss > 0 else 999.0

        # Max drawdown on cumulative returns
        cum = returns.cumsum()
        rolling_max = cum.cummax()
        drawdown = cum - rolling_max
        max_dd = abs(drawdown.min()) if len(drawdown) > 0 else 0.0

        return {
            "total_trades": int(n),
            "win_rate_pct": round(wr, 2),
            "profit_factor": pf,
            "avg_return_pct": round(avg_return, 4),
            "median_return_pct": round(median_return, 4),
            "total_return_pct": round(total_return, 2),
            "max_drawdown_pct": round(max_dd, 2),
            "best_trade_pct": round(returns.max(), 2),
            "worst_trade_pct": round(returns.min(), 2),
            "wins": int(n_wins),
            "losses": int(n_losses),
        }
    except Exception as e:
        return {"error": str(e)}
