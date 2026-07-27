"""Global state, trade persistence, engine_state — shared across all core modules."""
from __future__ import annotations
import os, json, datetime, logging
from typing import Any

logger = logging.getLogger("baba")

# ── File paths ──
TRADES_FILE = "trades_history.json"

# ── Global state ──
state: dict[str, Any] = {
    "ltp": 0.0,
    "open": 0.0,
    "high": 0.0,
    "low": 0.0,
    "close": 0.0,
    "volume": 0,
    "prev_close": 0.0,
    "adx": None,
    "rsi": None,
    "ema9": None,
    "ema21": None,
    "change_pct": 0.0,
    "regime": "LOADING",
    "strategy": "—",
    "target_pct": 0.6,
    "stop_pct": 0.2,
    "symbol": "",
    "trades": [],
    "daily_pnl": 0.0,
    "trade_count": 0,
    "wins": 0,
    "losses": 0,
    "win_rate": 0.0,
    "last_updated": None,
    "error": "Fetching data...",
    "data_source": "yfinance",
    "chart_labels": [],
    "chart_closes": [],
    "chart_opens": [],
    "chart_highs": [],
    "chart_lows": [],
    "chart_volumes": [],
    "chart_ema9": [],
    "chart_ema21": [],
    "session_dates": [],
    "market_open": False,
    "signal": None,
    "signal_type": None,
    "signal_price": None,
    "signal_reason": "",
    "signals_log": [],
    "instruments": {},
    "primary_ticker": "",
    "timeframe": "15m",
    "instrument_charts": {},
    "new_moon": {},
}

_RAW_1M_CACHE: dict[str, dict] = {}


def get_raw_cache() -> dict[str, dict]:
    return _RAW_1M_CACHE


def set_raw_cache(key: str, data: dict) -> None:
    _RAW_1M_CACHE[key] = data


# ── Trade persistence ──

def load_trades() -> None:
    try:
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE, "r") as f:
                data = json.load(f)
                state["trades"] = data.get("trades", [])
                state["trade_count"] = len(state["trades"])
                state["daily_pnl"] = data.get("daily_pnl", 0.0)
                state["wins"] = data.get("wins", 0)
                state["losses"] = data.get("losses", 0)
                state["win_rate"] = data.get("win_rate", 0.0)
                logger.info(f"Loaded {len(state['trades'])} trades from file")
    except Exception as e:
        logger.warning(f"Trade load error: {e}")


def save_trades() -> None:
    try:
        data = {
            "trades": state["trades"],
            "daily_pnl": state["daily_pnl"],
            "wins": state["wins"],
            "losses": state["losses"],
            "win_rate": state["win_rate"],
            "last_save": datetime.datetime.now().isoformat(),
        }
        with open(TRADES_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.warning(f"Trade save error: {e}")


def recalc_trade_stats() -> None:
    pnl_sum = 0.0
    wins = 0
    losses = 0
    for t in state["trades"]:
        p = float(t.get("pnl", 0.0) or 0.0)
        pnl_sum += p
        if p > 0:
            wins += 1
        elif p < 0:
            losses += 1
    state["trade_count"] = len(state["trades"])
    state["daily_pnl"] = round(pnl_sum, 2)
    state["wins"] = wins
    state["losses"] = losses
    state["win_rate"] = round((wins / len(state["trades"]) * 100), 1) if state["trades"] else 0.0


def append_trade(trade: dict) -> None:
    trade = dict(trade)
    trade["id"] = state["trade_count"] + 1
    state["trades"].append(trade)
    recalc_trade_stats()
    save_trades()


def resolve_trade_candle_idx(trade: dict, labels: list) -> int | None:
    idx = trade.get("candle_idx")
    if isinstance(idx, int) and 0 <= idx < len(labels):
        return idx
    trade_time = str(trade.get("chart_time") or trade.get("time") or "").strip()
    if not trade_time:
        return None
    t_hhmm = trade_time[:5]
    for i in range(len(labels) - 1, -1, -1):
        lbl = str(labels[i])
        if lbl == trade_time or lbl.endswith(trade_time) or lbl[-5:] == t_hhmm:
            return i
    return None
