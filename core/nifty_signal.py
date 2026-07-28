"""nifty_signal.py — NIFTY momentum AUTO paper-trade engine (bidirectional: long->CE, short->PE).

Fetches NIFTY 15m bars (Yahoo ^NSEI, free), computes the 1H MACD(12/26/5) cross via the basket feed's
signal_1h(), AND V2 MACD divergence (v1.1), then auto-advances a single-instrument paper position using
the COMBINED strategy: enter on cross + no bearish div, exit on opposite cross / bearish div / 2% stop /
3-day max-hold. State persisted to JSON.

Entry rules (Combined):
  - MACD cross UP + no bearish divergence → enter LONG
  - MACD cross DOWN + no bullish divergence → enter SHORT

Exit rules:
  - 2% stop (always checked)
  - MACD cross opposite → flip to opposite direction
  - Bearish divergence (in long) / Bullish divergence (in short) → exit
  - 3-day max-hold

v1.1 addition: V2 divergence detection with pivot_right=3 look-ahead fix.
"""
from __future__ import annotations
import hashlib
import json
import os
import time
import datetime
import threading

import numpy as np
import pandas as pd

from core.momentum_portfolio_feed import signal_1h, _market_open  # reuse the tested 1H-MACD-cross signal
from divergence_detector_v2 import detect_divergences_v2

STOP_PCT = 2.0                 # 2% stop (matches the deployed momentum strategy)
MAX_HOLD_BARS_1H = 18          # ~3 trading days (6 one-hour bars/day)
YAHOO = "^NSEI"                # NIFTY 50 index
SCAN_GAP_S = 14 * 60           # ~15-minute cadence

# ── Divergence cache (same pattern as momentum_portfolio_feed) ─────────────
_DIV_CACHE: dict[str, tuple[float, str]] = {}
_DIV_CACHE_TTL = 120.0
DIV_RECENCY = 6   # tuned value (Exit Lab 2026-06-19); aligned with the basket feed 28 Jul 2026


def _div_fingerprint(closes: list) -> str:
    tail = [round(c, 2) for c in closes[-60:]]
    raw = {"c": tail, "pl": 3, "pr": 3, "rec": DIV_RECENCY, "hid": True}
    return hashlib.md5(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:16]


def _div_index(closes, labels) -> pd.DatetimeIndex:
    """A DatetimeIndex for the detector. It only uses the index to format event labels, but it
    does so with .strftime(), so an integer index makes every call raise. Prefer the real bar
    labels; fall back to a synthetic 15m range so the detector still runs for callers that
    have no timestamps to hand.
    """
    if labels is not None and len(labels) == len(closes):
        idx = pd.to_datetime(pd.Series(labels), errors="coerce")
        if idx.notna().all():
            return pd.DatetimeIndex(idx)
    return pd.date_range("2000-01-01", periods=len(closes), freq="15min")


def _compute_div_state(closes, highs, lows, volumes, labels=None) -> str:
    """Compute current bar's divergence state from NIFTY 15m OHLC data.
    Returns 'bearish', 'bullish', or 'none'.
    Uses V2 detector with look-ahead fix (pivot_right=3).
    """
    n = len(closes)
    if n < 100:
        return "none"

    fp = _div_fingerprint(closes)
    now = time.time()
    cached = _DIV_CACHE.get(fp)
    if cached is not None and now < cached[0]:
        return cached[1]

    # MACD hist on 15m
    c = pd.Series(closes).astype(float)
    e12 = c.ewm(span=12, adjust=False).mean()
    e26 = c.ewm(span=26, adjust=False).mean()
    macd_h = (e12 - e26 - (e12 - e26).ewm(span=9, adjust=False).mean()).values

    # The V2 detector calls .strftime() on df.index when it builds an event row, so it needs
    # the real timestamps. Without them every call raised AttributeError and the except below
    # made it a permanent "none" — divergence was dead here too, since 9529eff (11 Jun).
    prep = pd.DataFrame({
        "close": np.array(closes, dtype=float),
        "high": np.array(highs, dtype=float),
        "low": np.array(lows, dtype=float),
        "volume": np.array(volumes, dtype=float),
        "macd_hist": macd_h,
    }, index=_div_index(closes, labels))

    try:
        events = detect_divergences_v2(
            prep,
            oscillator_col="macd_hist",
            pivot_left=3, pivot_right=3,
            min_prominence_pct=0.05, min_price_move_pct=0.12,
            min_pivot_distance=5, zscore_threshold=1.5,
            atr_resolution_mult=0.5, min_oscillator_move_pct=0.05,
            confirmation_bars=2, confirmation_ratio=0.6,
            include_hidden=True, use_volume_confirmation=False,
        )
    except Exception as e:
        print("[nifty-div] detector failed (%s: %s) — treating as 'none'"
              % (type(e).__name__, e), flush=True)
        _DIV_CACHE[fp] = (now + _DIV_CACHE_TTL, "none")
        return "none"

    if events.empty:
        _DIV_CACHE[fp] = (now + _DIV_CACHE_TTL, "none")
        return "none"

    # Build state array with look-ahead fix
    state = np.zeros(n, dtype=int)
    recency, pivot_right = DIV_RECENCY, 3
    for _, ev in events.iterrows():
        p2 = int(ev["second_pos"])
        kind = str(ev["kind"])
        pattern = str(ev["pattern"])
        p2_fixed = p2 + pivot_right
        end = min(n, p2_fixed + recency + 1)
        if p2_fixed >= end:
            continue
        if kind in ("bullish",) and pattern in ("regular", "hidden"):
            state[p2_fixed:end] = np.maximum(state[p2_fixed:end], 1)
        elif kind in ("bearish",) and pattern in ("regular", "hidden"):
            state[p2_fixed:end] = np.maximum(state[p2_fixed:end], 2)

    current = int(state[-1])
    if current == 2:
        result = "bearish"
    elif current == 1:
        result = "bullish"
    else:
        result = "none"

    _DIV_CACHE[fp] = (now + _DIV_CACHE_TTL, result)
    return result

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FILE = os.environ.get("NIFTY_STATE_FILE", os.path.join(_ROOT, "nifty_signal_state.json"))
_LOCK = threading.Lock()
_LAST_SCAN = 0.0


def _now_ist() -> str:
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M")


def _default_state() -> dict:
    return {"position": None, "ltp": None, "last_signal": {}, "last_bar": "",
            "closed_trades": [], "stats": {"trades": 0, "wins": 0, "total_pnl_pct": 0.0},
            "updated": ""}


def read() -> dict:
    try:
        with open(_FILE) as f:
            return json.load(f)
    except Exception:
        return _default_state()


def _save(state: dict) -> None:
    tmp = _FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, _FILE)


def _open(state: dict, direction: str, price: float, bar: str, ts: str) -> None:
    state["position"] = {"dir": direction, "signal": "CE" if direction == "long" else "PE",
                         "entry_price": price, "entry_time": ts, "entry_bar": bar, "bars_held": 0}


def _close(state: dict, price: float, reason: str, ts: str) -> None:
    p = state["position"]
    if not p:
        return
    pnl = ((price - p["entry_price"]) / p["entry_price"] * 100) if p["dir"] == "long" \
        else ((p["entry_price"] - price) / p["entry_price"] * 100)
    state["closed_trades"].append({**p, "exit_price": price, "exit_time": ts,
                                   "pnl_pct": round(pnl, 2), "reason": reason})
    state["closed_trades"] = state["closed_trades"][-200:]
    s = state["stats"]
    s["trades"] += 1
    s["wins"] += 1 if pnl > 0 else 0
    s["total_pnl_pct"] = round(s["total_pnl_pct"] + pnl, 2)
    state["position"] = None


def scan_and_update(signal: dict, ltp: float, now_ts: str | None = None) -> dict:
    """Advance the paper position given the latest 1H signal + last price.

    Uses COMBINED strategy (v1.1):
      Entry: MACD cross + no opposing divergence
      Exit:  opposite cross / opposing divergence / 2% stop / max-hold
    """
    ts = now_ts or _now_ist()
    state = read()
    state["ltp"] = ltp
    state["last_signal"] = signal
    bar = signal.get("bar_time_ist", "")
    cross = signal.get("cross", "none")
    div_state = signal.get("div_state", "none")   # v1.1: divergence state
    new_bar = bool(bar) and bar != state.get("last_bar", "")

    pos = state["position"]
    if pos:
        if new_bar:
            pos["bars_held"] = pos.get("bars_held", 0) + 1
        d = pos["dir"]; ep = pos["entry_price"]
        stop_hit = (d == "long" and ltp <= ep * (1 - STOP_PCT / 100)) or \
                   (d == "short" and ltp >= ep * (1 + STOP_PCT / 100))
        max_hold = pos["bars_held"] >= MAX_HOLD_BARS_1H
        opp_cross = new_bar and ((d == "long" and cross == "down") or (d == "short" and cross == "up"))
        # v1.1: exit on opposing divergence
        div_exit = new_bar and (
            (d == "long" and div_state == "bearish") or
            (d == "short" and div_state == "bullish")
        )
        if stop_hit:
            _close(state, ltp, "Stop", ts)
        elif max_hold:
            _close(state, ltp, "Max Hold", ts)
        elif div_exit:
            _close(state, ltp, "Bearish Div" if d == "long" else "Bullish Div", ts)
        elif opp_cross:
            _close(state, ltp, "MACD Cross", ts)
            _open(state, "short" if cross == "down" else "long", ltp, bar, ts)   # flip

    if state["position"] is None and new_bar:
        # v1.1: skip entry if opposing divergence active
        can_enter_long = cross == "up" and div_state != "bearish"
        can_enter_short = cross == "down" and div_state != "bullish"
        if can_enter_long:
            _open(state, "long", ltp, bar, ts)
        elif can_enter_short:
            _open(state, "short", ltp, bar, ts)

    if new_bar:
        state["last_bar"] = bar
    state["updated"] = ts
    _save(state)
    return state


def scan(force: bool = False) -> dict | None:
    """Fetch NIFTY 15m, compute 1H signal + divergence, advance the paper engine.
    Self-gated to ~15m + market hours."""
    global _LAST_SCAN
    if not force:
        if not _market_open():
            return None
        if time.time() - _LAST_SCAN < SCAN_GAP_S:
            return None
    try:
        import yfinance as yf
        df = yf.download(YAHOO, period="7d", interval="15m", auto_adjust=False, progress=False)
        if df is None or df.empty:
            return None
        # Handle both MultiIndex (group_by) and simple columns
        if isinstance(df.columns, pd.MultiIndex):
            closes = df["Close"].squeeze().tolist()
            highs = df["High"].squeeze().tolist()
            lows = df["Low"].squeeze().tolist()
            volumes = df["Volume"].squeeze().tolist()
        else:
            closes = df["Close"].tolist() if "Close" in df.columns else []
            highs = df["High"].tolist() if "High" in df.columns else []
            lows = df["Low"].tolist() if "Low" in df.columns else []
            volumes = df["Volume"].tolist() if "Volume" in df.columns else []
        labels = [str(x) for x in df.index]
        sig = signal_1h(closes, labels)
        # v1.1: compute divergence state
        sig["div_state"] = _compute_div_state(closes, highs, lows, volumes, labels)
        ltp = float(closes[-1]) if closes else 0.0
    except Exception:
        return None
    with _LOCK:
        _LAST_SCAN = time.time()
    return scan_and_update(sig, ltp)
