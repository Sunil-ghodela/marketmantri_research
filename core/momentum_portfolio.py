"""momentum_portfolio.py — auto paper-trade engine for the Momentum BASKET.

Extends the single-instrument momentum_paper.py to a 56-stock watchlist with a K=15
max-concurrent cap and 1/K sizing on a fixed pool. Builds a real, timestamped FORWARD
record (the deployable basket), persisted to momentum_portfolio_state.json (git-ignored).

Core logic is pure: scan_and_update(signals, ltp) takes per-stock signals + prices and
manages positions. Signal computation / live data is a separate layer (the caller).

Rules (faithful to Momentum v1, rec6 + sig5):
  - Entry (flat slot): 1H MACD cross UP, not bearish divergence, and a free slot (<K open)
  - Exit (in pos):     2% stop (every call) · MACD cross DOWN · bearish divergence · 3-day max-hold
  - Sizing:            POOL / K per position (equal weight); never more than K open
"""
from __future__ import annotations

import json
import os
import threading
import datetime

# State-file path. PRODUCTION (VPS) uses the default canonical record. For LOCAL dev/testing,
# set env MOMENTUM_STATE_FILE=momentum_portfolio_state_DEV.json so testing NEVER touches the live record.
_FILE = os.environ.get(
    "MOMENTUM_STATE_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "momentum_portfolio_state.json"))
_LOCK = threading.Lock()

POOL_INR = 500_000.0     # paper capital pool
K = 15                   # max concurrent positions
STOP_PCT = 2.0
MAX_HOLD_DAYS = 3


# ── Sizing multiplier: Loss-2→2x, Loss-3→2.5x, Loss-4→3x ────────────
def _sizing_mult(cons_losses: int) -> float:
    if cons_losses >= 4:
        return 3.0
    elif cons_losses >= 3:
        return 2.5
    elif cons_losses >= 2:
        return 2.0
    return 1.0


def _blank() -> dict:
    return {"open": {}, "trades": [], "equity": [], "skipped": [],
            "last_bar": "", "started": "", "cons_losses": 0}


def _load() -> dict:
    try:
        with open(_FILE) as f:
            d = json.load(f)
        for k, v in _blank().items():
            d.setdefault(k, v)
        return d
    except Exception:
        return _blank()


def _save(d: dict) -> None:
    try:
        with open(_FILE, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def _today() -> str:
    return datetime.date.today().isoformat()


def _stats(trades: list) -> dict:
    n = len(trades)
    wins = sum(1 for t in trades if t.get("pnl_pct", 0) > 0)
    return {"count": n, "wins": wins, "losses": n - wins,
            "win_rate": round(wins / n * 100, 1) if n else 0.0,
            "total_pnl": round(sum(t.get("pnl_abs", 0) for t in trades), 2)}


def _view(d: dict, ltp: dict | None = None) -> dict:
    ltp = ltp or {}
    open_list = []
    unrealized = 0.0
    for stock, op in d.get("open", {}).items():
        ep = op["entry_price"]
        px = ltp.get(stock)
        pnl_pct = ((px - ep) / ep * 100) if (px and ep) else 0.0
        pnl_abs = op["notional"] * pnl_pct / 100
        unrealized += pnl_abs
        try:
            days = (datetime.date.today() - datetime.date.fromisoformat(op["entry_date"])).days
        except Exception:
            days = 0
        open_list.append({
            "stock": stock,
            "entry_date": op.get("entry_date", ""),
            "entry_price": round(ep, 2),
            "ltp": round(px, 2) if px else None,
            "pnl_pct": round(pnl_pct, 2),
            "pnl_abs": round(pnl_abs, 2),
            "days": days,
        })
    open_list.sort(key=lambda x: x["pnl_pct"], reverse=True)
    st = _stats(d.get("trades", []))
    return {
            "ok": True,
            "open": open_list,
            "trades": list(reversed(d.get("trades", [])))[:200],
            "equity": d.get("equity", []),
            "signal_scan": list(reversed(d.get("skipped", [])))[:20],
            "kpi": {
                "open_count": len(d.get("open", {})),
                "k": K,
                "pool": POOL_INR,
                "total_pnl": st["total_pnl"],
                "unrealized": round(unrealized, 2),
                "trades": st["count"],
                "wins": st["wins"],
                "losses": st["losses"],
                "win_rate": st["win_rate"],
                "cons_losses": d.get("cons_losses", 0),
            },
            "started": d.get("started", ""),
        }


def _scan_bar(signals: dict) -> str:
    bars = [s.get("bar_time_ist", "") for s in signals.values() if s.get("bar_time_ist")]
    return max(bars) if bars else ""


def scan_and_update(signals: dict, ltp: dict, now_ts: str | None = None) -> dict:
    """Advance the basket from per-stock signals. Idempotent per bar.

    signals: {stock: {"cross": "up"|"down"|"none", "bar_time_ist": str, "div_state": str}}
    ltp:     {stock: float}
    """
    signals = signals or {}
    ltp = ltp or {}
    today = now_ts or _today()
    scan_bar = _scan_bar(signals)

    with _LOCK:
        d = _load()
        if not d.get("started"):
            d["started"] = today
        new_bar = bool(scan_bar) and scan_bar != d.get("last_bar", "")

        # ── EXITS (check every open position) ──
        for stock in list(d["open"].keys()):
            op = d["open"][stock]
            entry = op["entry_price"]
            px = ltp.get(stock)
            sg = signals.get(stock, {})
            reason = None
            if px and entry and px <= entry * (1 - STOP_PCT / 100):
                reason = "Stop Loss"                       # every call
            elif new_bar and sg.get("cross") == "down":
                reason = "MACD Cross"
            elif new_bar and sg.get("div_state") == "bearish":
                reason = "Bearish Div"
            elif new_bar:
                try:
                    ed = datetime.date.fromisoformat(op.get("entry_date", today))
                    if (datetime.date.today() - ed).days >= MAX_HOLD_DAYS:
                        reason = "Max Hold"
                except Exception:
                    pass
            # NOTE: this block must stay a sibling of the if/elif chain above. Indenting it
            # into the max-hold branch (as c7c3c45 did) silently kills the stop/cross/div
            # exits and drops positions with no trade record.
            if reason and px:
                pnl_pct = (px - entry) / entry * 100 if entry else 0.0
                pnl_abs = op["notional"] * pnl_pct / 100
                is_win = pnl_pct > 0
                # Track sizing info
                size_mult = op.get("size_mult", 1.0)
                d["trades"].append({
                    "stock": stock,
                    "entry_date": op.get("entry_date", ""),
                    "entry_time": op.get("entry_time", ""),
                    "entry_price": round(entry, 2),
                    "exit_time": scan_bar or today,
                    "exit_price": round(px, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "pnl_abs": round(pnl_abs, 2),
                    "is_win": is_win,
                    "exit_reason": reason,
                    "size_mult": size_mult,
                })
                # Update cons_losses counter for sizing
                if is_win:
                    d["cons_losses"] = 0
                else:
                    d["cons_losses"] = d.get("cons_losses", 0) + 1
                realized = round(sum(t["pnl_abs"] for t in d["trades"]), 2)
                d["equity"].append({"ts": scan_bar or today, "value": realized})
                del d["open"][stock]

        # ── ENTRIES (only on a fresh bar) ──
        if new_bar:
            for stock, sg in signals.items():
                if stock in d["open"]:
                    continue
                if sg.get("cross") != "up":
                    continue
                if sg.get("div_state") == "bearish":   # divergence blocks the entry — log it
                    d["skipped"].append({"stock": stock, "bar": scan_bar,
                                         "reason": "bearish divergence active"})
                    continue
                if sg.get("gated"):                       # decay gate: stock benched (recent 3mo weak)
                    d["skipped"].append({"stock": stock, "bar": scan_bar, "reason": "decay gate (recent 3mo weak)"})
                    continue
                px = ltp.get(stock)
                if not px:
                    continue
                if len(d["open"]) < K:
                    cons_l = d.get("cons_losses", 0)
                    size_mult = _sizing_mult(cons_l)
                    base_notional = round(POOL_INR / K, 2)
                    d["open"][stock] = {
                        "entry_date": today,
                        "entry_time": scan_bar,
                        "entry_price": round(px, 2),
                        "notional": round(base_notional * size_mult, 2),
                        "size_mult": size_mult,
                    }
                else:
                    d["skipped"].append({"stock": stock, "bar": scan_bar, "reason": "slot full (K=%d)" % K})

        if new_bar:
            d["last_bar"] = scan_bar
            d["skipped"] = d["skipped"][-50:]   # keep recent
        _save(d)
        return _view(d, ltp)


def read(ltp: dict | None = None) -> dict:
    with _LOCK:
        return _view(_load(), ltp)
