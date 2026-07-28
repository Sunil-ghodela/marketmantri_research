"""momentum_portfolio_feed.py — live signal feed for the momentum basket paper engine.

Fetches the watchlist's recent 15m bars (Yahoo, free), computes each stock's 1H MACD
cross signal (12/26/SIGNAL=5 — the shipped sig5) AND V2 MACD divergence state (v1.1),
and feeds them to core.momentum_portfolio.

Self-gates to a ~15-minute cadence and to market hours, so it's safe to call every refresh cycle.

Divergence (v1.1):
  - Computed ONCE per stock via detect_divergences_v2 (same params as basket-100 backtest)
  - Uses look-ahead fix: pivot_right=3 shift (p2 + 3) before marking divergence state
  - Cached per fingerprint (hash of last 60 closes + params) with 120s TTL
  - Computed only for stocks that NEED it: open positions (exit check) + fresh cross="up" (entry check)
  - Other stocks: div_state="none" (fast path)
"""
from __future__ import annotations

import hashlib
import time
import threading
import datetime
import json
import os

import numpy as np
import pandas as pd

from core import momentum_portfolio as engine
from divergence_detector_v2 import detect_divergences_v2

_GATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'gate_flags.json')

# ── Divergence cache ────────────────────────────────────────────────────────
# Keyed by fingerprint (hash of last 60 closes + params), 120s TTL.
# Avoids re-computing V2 for stocks whose data hasn't changed between scans.
_DIV_CACHE: dict[str, tuple[float, str]] = {}  # fp -> (expiry_ts, div_state)
_DIV_CACHE_TTL = 120.0

# Divergence recency: how many bars a detected divergence stays active.
# Exit Lab 2026-06-19 tuned this to 6 (beats 15, OOS-robust) and STRATEGY.md documents 6 as
# deployed — but the live engines shipped with 15 and, until 28 Jul, a dead detector. Aligned
# to the tuned value on 28 Jul 2026 (same day the record restarted, so no mid-record change).
DIV_RECENCY = 6


def _div_fingerprint(df: pd.DataFrame) -> str:
    """Quick fingerprint from last 60 closes + params."""
    closes = df["Close"].tail(60).round(2).tolist()
    raw = {"c": closes, "pl": 3, "pr": 3, "rec": DIV_RECENCY, "hid": True}
    return hashlib.md5(json.dumps(raw, sort_keys=True).encode()).hexdigest()[:16]


def _compute_div_state(df: pd.DataFrame) -> str:
    """Compute current bar's divergence state from 15m OHLC DataFrame.
    Returns 'bearish', 'bullish', or 'none'.
    
    Uses V2 detector with same params as basket-100 backtest.
    Applies look-ahead fix: pivot_right=3 shift before marking state.
    Cached via fingerprint for 120s.
    """
    n = len(df)
    if n < 100:
        return "none"

    fp = _div_fingerprint(df)
    now = time.time()
    cached = _DIV_CACHE.get(fp)
    if cached is not None and now < cached[0]:
        return cached[1]

    # Compute MACD hist on 15m
    close = df["Close"].astype(float)
    e12 = close.ewm(span=12, adjust=False).mean()
    e26 = close.ewm(span=26, adjust=False).mean()
    macd_h = (e12 - e26 - (e12 - e26).ewm(span=9, adjust=False).mean()).values

    # The V2 detector formats df.index[...] with .strftime() when it builds an event row, so it
    # needs the real DatetimeIndex. Passing a bare RangeIndex made every call raise
    # AttributeError, which the except below turned into a permanent "none" — divergence was
    # dead in this engine from the V2 commit (9529eff, 11 Jun) until 28 Jul.
    prep = pd.DataFrame({
        "close": close.values,
        "high": df["High"].values.astype(float),
        "low": df["Low"].values.astype(float),
        "volume": df["Volume"].values.astype(float),
        "macd_hist": macd_h,
    }, index=df.index)

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
        # Never swallow silently again — a permanently-failing detector is indistinguishable
        # from "no divergence" and that is exactly how this went unnoticed for seven weeks.
        print("[div] detector failed (%s: %s) — treating as 'none'" % (type(e).__name__, e),
              flush=True)
        _DIV_CACHE[fp] = (now + _DIV_CACHE_TTL, "none")
        return "none"

    if events.empty:
        _DIV_CACHE[fp] = (now + _DIV_CACHE_TTL, "none")
        return "none"

    # Build state array with look-ahead fix (p2 + pivot_right)
    state = np.zeros(n, dtype=int)
    recency = DIV_RECENCY
    pivot_right = 3
    for _, ev in events.iterrows():
        p2 = int(ev["second_pos"])
        kind = str(ev["kind"])
        pattern = str(ev["pattern"])
        p2_fixed = p2 + pivot_right  # look-ahead fix
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


def _gate_flags() -> dict:
    """Load decay-gate flags {stock: {'in': bool}}. Missing file / stock -> default IN (not gated)."""
    try:
        with open(_GATE_PATH) as f:
            return json.load(f).get('flags', {})
    except Exception:
        return {}

_LOCK = threading.Lock()
_LAST_LTP: dict[str, float] = {}
_LAST_SCAN = 0.0
SCAN_GAP_S = 14 * 60          # ~15m cadence
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 12, 26, 5    # sig5 (shipped)

# 56-stock watchlist (breadth universe minus extreme-DD SOLARINDS/CGPOWER/ADANIENT; TRENT excluded — no data)
# Expanded universe (2026-06-21): 93 tradeable stocks = the 96 "clean" archive names minus the 3
# indices (NIFTY 50 / NIFTY BANK / INDIA VIX — not tradeable as stocks) and the extreme-DD names.
# The feed gracefully skips any symbol whose Yahoo fetch fails (newer/uncertain listings); the live
# universe is whatever fetches. "Universe stocks ko change karte rahenge" — just edit this list.
WATCH = [
    'RELIANCE','HDFCBANK','ICICIBANK','INFY','TCS','ITC','SBIN','KOTAKBANK','BHARTIARTL','LT',
    'AXISBANK','BAJFINANCE','BAJAJFINSV','MARUTI','ASIANPAINT','HINDUNILVR','SUNPHARMA','TITAN',
    'ULTRACEMCO','NESTLEIND','WIPRO','HCLTECH','TATASTEEL','TMPV','MM','POWERGRID','NTPC','ONGC',
    'COALINDIA','JSWSTEEL','ADANIPORTS','GRASIM','CIPLA','TECHM','HAL','CHOLAFIN','MUTHOOTFIN',
    'MAZDOCK','DMART','MOTHERSON','TVSMOTOR','SIEMENS','ABB','BOSCHLTD','CUMMINSIND','DLF','GODREJCP',
    'AMBUJACEM','PIDILITIND','TORNTPHARM','INDHOTEL','PFC','RECLTD','BANKBARODA','INDIGO',
    # ── expansion: new names ──
    'APOLLOHOSP','DIVISLAB','DRREDDY','ZYDUSLIFE','BRITANNIA','TATACONSUM','UNITDSPR','VBL',
    'EICHERMOT','BAJAJ-AUTO','HYUNDAI','BPCL','IOC','GAIL','TATAPOWER','ADANIPOWER','ADANIGREEN',
    'ADANIENT','ADANIENSOL','VEDL','HINDALCO','HINDZINC','JINDALSTEL','SHREECEM','MAXHEALTH',
    'CANBK','PNB','UNIONBANK','SHRIRAMFIN','BAJAJHLDNG','HDFCAMC','JIOFIN','TATACAP','LODHA',
    'ETERNAL',
]

# symbols whose Yahoo ticker differs from "{sym}.NS"
_YMAP = {'TMPV': 'TATAMOTORS', 'MM': 'M&M'}


def _yahoo(sym: str) -> str:
    return _YMAP.get(sym, sym) + '.NS'


def signal_1h(closes: list[float], labels: list[str]) -> dict:
    """1H MACD(12/26/5) cross from 15m closes+labels. Returns {cross, bar_time_ist, state}."""
    if len(closes) < 40 or not labels:
        return {"cross": "none", "bar_time_ist": "", "state": "unknown"}
    idx = pd.to_datetime(pd.Series(labels), errors="coerce")
    s = pd.Series(closes, index=idx).dropna()
    h = s.resample("1h").last().dropna()
    if len(h) < 35:
        return {"cross": "none", "bar_time_ist": "", "state": "unknown"}
    macd = h.ewm(span=MACD_FAST, adjust=False).mean() - h.ewm(span=MACD_SLOW, adjust=False).mean()
    sigl = macd.ewm(span=MACD_SIGNAL, adjust=False).mean()
    m, mp = macd.iloc[-1], macd.iloc[-2]
    g, gp = sigl.iloc[-1], sigl.iloc[-2]
    cross = "up" if (mp <= gp and m > g) else ("down" if (mp > gp and m <= g) else "none")
    return {"cross": cross, "bar_time_ist": str(h.index[-1])[:16],
            "state": "green" if m > g else "red"}


def last_ltp() -> dict:
    with _LOCK:
        return dict(_LAST_LTP)


def _market_open() -> bool:
    try:
        from core.data import is_market_open
        return bool(is_market_open())
    except Exception:
        now = datetime.datetime.now().time()
        return datetime.time(9, 15) <= now <= datetime.time(15, 30)


def update_open_ltp() -> None:
    """Light, frequent price refresh for the OPEN positions only → live P&L between full 15m scans.
    Safe to call every ~60s during market hours. Never raises."""
    if not _market_open():
        return
    try:
        open_stocks = [p["stock"] for p in engine.read({}).get("open", [])]
        if not open_stocks:
            return
        import yfinance as yf
        tickers = [_yahoo(s) for s in open_stocks]
        data = yf.download(tickers, period="1d", interval="1m",
                           group_by="ticker", auto_adjust=False, progress=False, threads=True)
        upd = {}
        single = len(open_stocks) == 1
        for s in open_stocks:
            yt = _yahoo(s)
            try:
                df = data if single else (data[yt] if yt in data.columns.get_level_values(0) else None)
                if df is None:
                    continue
                df = df.dropna()
                if not df.empty:
                    upd[s] = float(df["Close"].iloc[-1])
            except Exception:
                continue
        if upd:
            with _LOCK:
                _LAST_LTP.update(upd)
    except Exception:
        pass


def scan(force: bool = False) -> dict | None:
    """Fetch watchlist 15m bars, compute signals, advance the engine. Self-gated to ~15m + market hours."""
    global _LAST_SCAN
    if not force:
        if not _market_open():
            return None
        if time.time() - _LAST_SCAN < SCAN_GAP_S:
            return None
    try:
        import yfinance as yf
    except Exception:
        return None
    tickers = [_yahoo(s) for s in WATCH]
    try:
        data = yf.download(tickers, period="7d", interval="15m",
                           group_by="ticker", auto_adjust=False, progress=False, threads=True)
    except Exception:
        return None

    gflags = _gate_flags()                 # decay-gate: {stock: {'in': bool}}; missing -> IN

    # ── v1.1: read open positions so we only compute divergence where needed ──
    open_stocks = set()
    try:
        eng_state = engine.read({})
        for pos in eng_state.get("open", []):
            if isinstance(pos, dict) and "stock" in pos:
                open_stocks.add(pos["stock"])
    except Exception:
        pass

    signals, ltp = {}, {}
    for sym in WATCH:
        yt = _yahoo(sym)
        try:
            df = data[yt].dropna() if yt in data.columns.get_level_values(0) else None
            if df is None or df.empty:
                continue
            closes = df["Close"].tolist()
            labels = [str(x) for x in df.index]
            sg = signal_1h(closes, labels)

            # ── v1.1: divergence — only compute for stocks that need it ──
            sg["div_state"] = "none"
            need_div = sym in open_stocks or sg.get("cross") == "up"
            if need_div:
                sg["div_state"] = _compute_div_state(df)

            gf = gflags.get(sym)
            sg["gated"] = bool(gf is not None and not gf.get("in", True))   # decay gate OUT?
            signals[sym] = sg
            ltp[sym] = float(closes[-1])
        except Exception:
            continue

    with _LOCK:
        _LAST_LTP.update(ltp)
        _LAST_SCAN = time.time()
    if not signals:
        return None
    return engine.scan_and_update(signals, ltp)
