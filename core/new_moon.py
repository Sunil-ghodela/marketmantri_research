"""New Moon integration — cached fetch, backtest stats, calendar."""
from __future__ import annotations
import time, datetime, logging
from typing import Any
from core.state import state

logger = logging.getLogger("baba")

_NEW_MOON_CACHE: dict = {}
_NEW_MOON_CACHE_TS: float = 0.0


def fetch_new_moon_state() -> None:
    """Update state['new_moon'] with current New Moon info (cached 1 hour)."""
    global _NEW_MOON_CACHE, _NEW_MOON_CACHE_TS
    now = time.time()
    if now - _NEW_MOON_CACHE_TS < 3600 and _NEW_MOON_CACHE:
        state["new_moon"] = _NEW_MOON_CACHE
        return
    try:
        from new_moon_integration import (
            is_new_moon_entry_date,
            get_active_new_moon,
            new_moon_summary,
            get_new_moon_backtest_stats,
        )
        today = datetime.date.today()
        active = get_active_new_moon(today)
        summary = new_moon_summary()
        backtest = get_new_moon_backtest_stats()
        info = {
            "is_entry_date": is_new_moon_entry_date(today),
            "active": active,
            "upcoming": summary.get("upcoming", []),
            "total_windows": summary.get("total_windows", 0),
            "is_active": bool(active and active.get("status") == "active"),
            "t2_date": str(today) if is_new_moon_entry_date(today) else None,
            "backtest": backtest,
        }
        _NEW_MOON_CACHE = info
        _NEW_MOON_CACHE_TS = now
        state["new_moon"] = info
    except Exception as e:
        logger.warning(f"New Moon fetch error: {e}")
        state["new_moon"] = {"is_active": False, "error": str(e)}


def json_safe_dates(value):
    """Convert datetime.date/datetime.datetime to ISO strings recursively."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: json_safe_dates(v) for k, v in value.items()}
    if isinstance(value, list):
        return [json_safe_dates(v) for v in value]
    return value


def load_new_moon_streaks(limit: int = 18) -> list[dict]:
    import os, pandas as pd
    path = os.path.join("reports", "strategy_new_moon_consecutive_streaks.csv")
    if not os.path.exists(path):
        return []
    df = pd.read_csv(path)
    df = df[(df["instrument"] == "NIFTYBEES") & (df["variant"] == "T-2")].copy()
    if df.empty:
        return []
    df["abs_len"] = df["streak_len"].astype(int)
    df["abs_return"] = df["total_return_pct"].astype(float).abs()
    df = df.sort_values(["abs_len", "abs_return"], ascending=[False, False]).head(limit)
    keep = [
        "result", "streak_len", "start_entry_date", "end_exit_date",
        "start_month", "start_year", "end_month", "end_year",
        "total_return_pct", "avg_return_pct", "trade_dates",
    ]
    return df[keep].to_dict(orient="records")
