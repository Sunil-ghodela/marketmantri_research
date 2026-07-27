"""momentum_paper.py — Auto paper-trade tracker for Momentum Strategy v1.

Builds a real FORWARD record of the momentum strategy: when the live 1H MACD
signal crosses, it opens / closes a paper position automatically and records the
trade. No manual logging needed.

Faithful to Momentum v1 rules:
  - Entry (flat):  1H MACD cross UP  AND not bearish divergence
  - Exit (in pos): 1H MACD cross DOWN, OR bearish divergence, OR 2% stop, OR max-hold

Idempotent per 1H bar: entries/cross-exits only fire when the bar advances, so it
is safe to call from /data on every poll. The 2% stop is checked every call.
State persists to momentum_paper_trades.json (git-ignored, like trades_history.json).
"""
from __future__ import annotations

import json
import os
import threading
import datetime

_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "momentum_paper_trades.json")
_LOCK = threading.Lock()

NOTIONAL_INR = 100_000.0   # fixed notional for ₹ P&L display
STOP_PCT = 2.0
MAX_HOLD_DAYS = 4


def _blank() -> dict:
    return {"open": None, "trades": [], "last_bar": "", "started": ""}


def _load() -> dict:
    try:
        with open(_FILE) as f:
            d = json.load(f)
        for k in ("open", "trades", "last_bar", "started"):
            d.setdefault(k, _blank()[k])
        return d
    except Exception:
        return _blank()


def _save(d: dict) -> None:
    try:
        with open(_FILE, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def _stats(trades: list) -> dict:
    n = len(trades)
    wins = sum(1 for t in trades if t.get("pnl_pct", 0) > 0)
    return {
        "count": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate": round(wins / n * 100, 1) if n else 0.0,
        "total_pnl": round(sum(t.get("pnl_abs", 0) for t in trades), 2),
        "total_pct": round(sum(t.get("pnl_pct", 0) for t in trades), 2),
    }


def _view(d: dict, price: float | None = None) -> dict:
    op = d.get("open")
    cur = None
    if op and price:
        ep = op["entry_price"]
        cur = {
            "entry_date": op.get("entry_date", ""),
            "entry_time": op.get("entry_time", ""),
            "entry_price": round(ep, 2),
            "ltp": round(price, 2),
            "pnl_pct": round((price - ep) / ep * 100, 2) if ep else 0.0,
        }
    return {
        "ok": True,
        "open": cur,
        "trades": list(reversed(d.get("trades", [])))[:50],
        "stats": _stats(d.get("trades", [])),
        "started": d.get("started", ""),
    }


def update(signal: dict, price: float | None, div_state: str | None) -> dict:
    """Advance the paper position from the latest momentum signal. Idempotent per bar."""
    if not signal or not price:
        return read(price)
    bar = signal.get("bar_time_ist", "") or ""
    cross = signal.get("cross", "none")
    today = datetime.date.today().isoformat()
    with _LOCK:
        d = _load()
        if not d.get("started"):
            d["started"] = today
        new_bar = bool(bar) and bar != d.get("last_bar", "")
        op = d.get("open")

        if op:
            entry = op["entry_price"]
            reason = None
            if entry and price <= entry * (1 - STOP_PCT / 100):
                reason = "Stop Loss"          # checked every call
            elif new_bar and cross == "down":
                reason = "MACD Cross"
            elif new_bar and div_state == "bearish":
                reason = "Bearish Div"
            else:
                try:
                    ed = datetime.date.fromisoformat(op.get("entry_date", today))
                    if (datetime.date.today() - ed).days >= MAX_HOLD_DAYS:
                        reason = "Max Hold"
                except Exception:
                    pass
            if reason:
                pnl_pct = (price - entry) / entry * 100 if entry else 0.0
                d["trades"].append({
                    "entry_date": op.get("entry_date", ""),
                    "entry_time": op.get("entry_time", ""),
                    "entry_price": round(entry, 2),
                    "exit_time": bar or today,
                    "exit_price": round(price, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "pnl_abs": round(NOTIONAL_INR * pnl_pct / 100, 2),
                    "is_win": pnl_pct > 0,
                    "exit_reason": reason,
                })
                d["open"] = None
        elif new_bar and cross == "up" and div_state != "bearish":
            d["open"] = {"entry_date": today, "entry_time": bar, "entry_price": round(price, 2)}

        if new_bar:
            d["last_bar"] = bar
        _save(d)
        return _view(d, price)


def read(price: float | None = None) -> dict:
    with _LOCK:
        return _view(_load(), price)
