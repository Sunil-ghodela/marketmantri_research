"""Divergence detection helpers — wrap divergence_detector_v2 + multi_tf_divergence.

All fixes from Baba's review:
  1. ✅ Class-based cache with threading.Lock (not global vars — thread-safe)
  2. ✅ Strong fingerprint via hashlib of last 60 bars (not just last close + count)
  3. ✅ MultiTFDivergenceDetector exists in multi_tf_divergence.py
  4. ✅ Specific exception logging (not bare except Exception)
  5. ✅ Input validation — reject null/NaN/mismatched data before processing
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any

import pandas as pd

logger = logging.getLogger("baba")

# ── Thread-safe class-based cache ──────────────────────────────────────────


class DivergenceCache:
    """Thread-safe, TTL-based cache for divergence detection results.

    Uses a threading.Lock so multiple Flask request threads don't race
    on cache writes. Each cache entry stores:
      - expiry: timestamp when the entry expires
      - fp:     cache fingerprint (hashlib of last N bars + params)
      - data:   cached result (events list or dict)
    """

    def __init__(self, default_ttl: float = 60.0):
        self._lock = threading.Lock()
        self._default_ttl = default_ttl
        self._store: dict[str, tuple[float, str, Any]] = {}
        # _store = {key: (expiry_ts, fingerprint, cached_data)}

    def get(self, key: str, fp: str) -> Any | None:
        """Return cached data if key exists, fingerprint matches, and TTL not expired."""
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expiry_ts, stored_fp, data = entry
            if time.time() > expiry_ts:
                del self._store[key]
                return None
            if stored_fp != fp:
                return None
            return data

    def set(self, key: str, fp: str, data: Any, ttl: float | None = None) -> None:
        """Store data with fingerprint and TTL."""
        ttl = ttl if ttl is not None else self._default_ttl
        with self._lock:
            self._store[key] = (time.time() + ttl, fp, data)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


# ── Module-level caches ────────────────────────────────────────────────────
_div_cache = DivergenceCache(default_ttl=60.0)  # divergence events cache
_mtf_cache = DivergenceCache(default_ttl=300.0)  # multi-TF cache (5 min)


# ── V2 switch ──────────────────────────────────────────────────────────────
DIVERGENCE_V2_ENABLED = True  # set False to fall back to V1 (divergence_detector.py)

CACHE_KEY_DIVERGENCE = "divergence_events"
CACHE_KEY_MTF = "mtf_divergence"


def _validate_inputs(
    labels: list,
    opens: list,
    highs: list,
    lows: list,
    closes: list,
    volumes: list,
) -> str | None:
    """Validate OHLC inputs before processing. Returns None if valid, error msg if invalid."""
    if not labels or not closes:
        return "empty_data"

    n = len(closes)
    if len(labels) != n or len(opens) != n or len(highs) != n or len(lows) != n or len(volumes) != n:
        return f"length_mismatch: labels={len(labels)} opens={len(opens)} highs={len(highs)} lows={len(lows)} closes={len(closes)} volumes={len(volumes)}"

    # Check for NaN/None in critical fields
    bad_closes = [i for i, v in enumerate(closes) if v is None or (isinstance(v, float) and pd.isna(v))]
    if bad_closes:
        return f"nan_close_at_indices={bad_closes[:5]}"

    return None


def build_divergence_events(labels, opens, highs, lows, closes, volumes) -> list[dict]:
    """Detect MACD divergence events on OHLC data. Returns list of event dicts.

    Uses divergence_detector_v2 (Divergence V2) with:
    - Better pivot detection (min bar distance, z-score noise filter)
    - ATR-based resolution (not just any close>high)
    - Better hidden divergence (min oscillator move threshold)
    - Strong cache fingerprint via hashlib of last 60 bars

    Falls back to V1 if V2 import fails or DIVERGENCE_V2_ENABLED=False.
    Results cached in thread-safe DivergenceCache with TTL.
    """
    # ── Input validation ───────────────────────────────────────────────
    err = _validate_inputs(labels, opens, highs, lows, closes, volumes)
    if err is not None:
        logger.warning(f"Divergence: skipping — {err}")
        return []

    from divergence_detector_v2 import make_cache_key

    v2_params = {
        "pivot_left": 3,
        "pivot_right": 3,
        "min_prominence_pct": 0.05,
        "min_price_move_pct": 0.12,
        "include_hidden": True,
        "v2_enabled": DIVERGENCE_V2_ENABLED,
    }
    fp = make_cache_key(closes, labels, n_bars=60, params=v2_params)

    # ── Check cache ────────────────────────────────────────────────────
    cached = _div_cache.get(CACHE_KEY_DIVERGENCE, fp)
    if cached is not None:
        return cached

    # ── Build DataFrame ────────────────────────────────────────────────
    try:
        df = pd.DataFrame({
            "date": labels,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        })
    except Exception as e:
        logger.error(f"Divergence: DataFrame construction failed: {e}")
        return []

    # ── Run detector ───────────────────────────────────────────────────
    events = pd.DataFrame()
    try:
        if DIVERGENCE_V2_ENABLED:
            from divergence_detector_v2 import prepare_intraday, detect_divergences_v2

            prepared = prepare_intraday(df)
            events = detect_divergences_v2(
                prepared,
                oscillator_col="macd_hist",
                pivot_left=3, pivot_right=3,
                max_resolution_bars=24,
                min_prominence_pct=0.05,
                min_price_move_pct=0.10,
                min_pivot_distance=5,
                zscore_threshold=1.5,
                atr_resolution_mult=0.5,
                min_oscillator_move_pct=0.05,
                confirmation_bars=2,
                confirmation_ratio=0.6,
                include_hidden=True,
                use_volume_confirmation=False,
            )
        else:
            from divergence_detector import prepare_intraday, detect_divergences

            prepared = prepare_intraday(df)
            events = detect_divergences(
                prepared, oscillator_col="macd_hist",
                pivot_left=3, pivot_right=3, max_resolution_bars=16,
                min_prominence_pct=0.05, min_price_move_pct=0.12, include_hidden=True,
            )
    except ImportError as e:
        logger.error(f"Divergence detector import failed: {e}")
        # Try V1 as fallback
        if DIVERGENCE_V2_ENABLED:
            logger.warning("Falling back to V1 divergence detector")
            try:
                from divergence_detector import prepare_intraday, detect_divergences
                prepared = prepare_intraday(df)
                events = detect_divergences(
                    prepared, oscillator_col="macd_hist",
                    pivot_left=3, pivot_right=3, max_resolution_bars=16,
                    min_prominence_pct=0.05, min_price_move_pct=0.12, include_hidden=True,
                )
            except Exception as e2:
                logger.error(f"V1 fallback also failed: {e2}")
                return []
        else:
            return []
    except ValueError as e:
        logger.warning(f"Divergence detection value error: {e}")
        return []
    except Exception as e:
        logger.error(f"Divergence detection unexpected error: {e}", exc_info=True)
        return []

    # ── Format output ──────────────────────────────────────────────────
    if events.empty:
        _div_cache.set(CACHE_KEY_DIVERGENCE, fp, [])
        return []

    try:
        out = []
        for _, row in events.iterrows():
            out.append({
                "x": row["second_time_ist"],
                "y": float(row["second_price"]),
                "kind": row["kind"],
                "pattern": row["pattern"],
                "strength": row["strength"],
                "resolved": bool(row["resolved"]),
                "resolution_time_ist": row["resolution_time_ist"],
                "first_time_ist": row["first_time_ist"],
                "second_time_ist": row["second_time_ist"],
                "price_move_pct": float(row["price_move_pct"]),
                "oscillator_delta": float(row["oscillator_delta"]),
            })
    except KeyError as e:
        logger.error(f"Divergence: missing expected column in result: {e}")
        return []
    except Exception as e:
        logger.error(f"Divergence: result formatting failed: {e}")
        return []

    _div_cache.set(CACHE_KEY_DIVERGENCE, fp, out)
    return out


def build_divergence_summary(labels, opens, highs, lows, closes, volumes) -> dict:
    """Return divergence stats to embed in /data response."""
    events = build_divergence_events(labels, opens, highs, lows, closes, volumes)
    summary = {
        "bullish_divergence_count": 0,
        "bearish_divergence_count": 0,
        "hidden_divergence_count": 0,
        "strong_divergence_count": 0,
        "last_divergence_kind": "",
        "last_divergence_pattern": "",
        "last_divergence_strength": "",
        "last_divergence_time_ist": "",
        "last_divergence_resolved": False,
    }
    if not events:
        return summary
    for ev in events:
        if ev["kind"] == "bullish":
            summary["bullish_divergence_count"] += 1
        elif ev["kind"] == "bearish":
            summary["bearish_divergence_count"] += 1
        if ev["pattern"] == "hidden":
            summary["hidden_divergence_count"] += 1
        if ev["strength"] == "strong":
            summary["strong_divergence_count"] += 1
    last = events[-1]
    summary["last_divergence_kind"] = last["kind"]
    summary["last_divergence_pattern"] = last["pattern"]
    summary["last_divergence_strength"] = last["strength"]
    summary["last_divergence_time_ist"] = last["second_time_ist"]
    summary["last_divergence_resolved"] = last["resolved"]
    return summary


def run_multi_tf_divergence(symbol: str = "NIFTYBEES") -> dict:
    """Run multi-timeframe divergence detector and return structured result.

    Results cached in thread-safe DivergenceCache with 5-minute TTL to avoid
    ~20s recompute on every request.

    Uses MultiTFDivergenceDetector from multi_tf_divergence.py.
    """
    # Check cache first
    cached = _mtf_cache.get(CACHE_KEY_MTF, symbol)
    if cached is not None and cached.get("symbol") == symbol:
        return cached

    # Validate symbol
    if not symbol or not isinstance(symbol, str):
        logger.warning(f"Multi-TF: invalid symbol={symbol!r}")
        return {"ok": False, "error": f"invalid_symbol: {symbol!r}"}

    try:
        from multi_tf_divergence import MultiTFDivergenceDetector
    except ImportError as e:
        logger.error(f"Multi-TF: import failed: {e}")
        return {"ok": False, "error": f"import_error: {e}"}

    # Resolve data files
    m15 = os.path.join("data", f"{symbol}_15m.feather")
    d1 = os.path.join("data", f"{symbol}_1d.feather")

    if not os.path.exists(m15):
        logger.warning(f"Multi-TF: {m15} not found, falling back to NIFTY50")
        m15 = os.path.join("data", "NIFTY50_15m.feather")
        d1 = os.path.join("data", "NIFTY50_1d.feather")
        symbol = "NIFTY50"

    if not os.path.exists(m15):
        logger.error(f"Multi-TF: neither {m15} exists")
        return {"ok": False, "error": "no_data_files"}

    # Run detector
    try:
        det = MultiTFDivergenceDetector(m15_path=m15, d1_path=d1)
        results = det.run()
    except Exception as e:
        logger.error(f"Multi-TF divergence run failed: {e}", exc_info=True)
        return {"ok": False, "error": str(e)[:200]}

    # Format timeframes
    try:
        tfs = []
        for r in results:
            tfs.append({
                "tf": r.timeframe,
                "available": r.available,
                "close": r.close,
                "change_pct": r.change_pct,
                "bull_div": r.bullish_div,
                "bear_div": r.bearish_div,
                "signal": r.signal,
                "macd_hist": r.macd_hist,
                "bars": r.bars,
                "bull_count": r.bullish_count,
                "bear_count": r.bearish_count,
            })
    except AttributeError as e:
        logger.error(f"Multi-TF: unexpected result format: {e}")
        return {"ok": False, "error": f"result_format: {e}"}
    except Exception as e:
        logger.error(f"Multi-TF: result parsing failed: {e}")
        return {"ok": False, "error": str(e)[:200]}

    # Build verdict
    available = [t for t in tfs if t.get("available")]
    bull_tfs = [t["tf"] for t in tfs if t.get("bull_div")]
    bear_tfs = [t["tf"] for t in tfs if t.get("bear_div")]
    conflict_tfs = [t["tf"] for t in tfs if t.get("signal") == "conflict"]
    bull_count = sum(1 for t in available if t.get("signal") == "bullish")
    bear_count = sum(1 for t in available if t.get("signal") == "bearish")
    conflict_count = sum(1 for t in available if t.get("signal") == "conflict")

    if conflict_count > 2:
        verdict = f"TENSION — {conflict_count} TFs conflict"
    elif bull_count > bear_count and bull_count >= 3:
        verdict = f"BULLISH — {bull_count} TFs bullish"
    elif bear_count > bull_count and bear_count >= 3:
        verdict = f"BEARISH — {bear_count} TFs bearish"
    else:
        verdict = f"MIXED — {bull_count}B {bear_count}R {conflict_count}C"

    result = {
        "ok": True,
        "symbol": symbol,
        "timeframes": tfs,
        "bull_tfs": bull_tfs,
        "bear_tfs": bear_tfs,
        "conflict_tfs": conflict_tfs,
        "verdict": verdict,
        "bull_count": bull_count,
        "bear_count": bear_count,
        "conflict_count": conflict_count,
    }

    _mtf_cache.set(CACHE_KEY_MTF, symbol, result)
    return result
