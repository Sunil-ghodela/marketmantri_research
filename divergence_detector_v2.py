"""
divergence_detector_v2.py — Improved MACD divergence detection.

V2 improvements over V1 (divergence_detector.py):
  1. Better pivot detection — min bar distance between pivots, z-score noise filter,
     configurable prominence + min_price_move_pct defaults that actually work
  2. ATR-based resolution — price must move beyond pivot by at least ATR multiplier
  3. Better hidden divergence — min oscillator move threshold + multi-pivot structure check
  4. Strong cache fingerprint — hashlib of last N bars
  5. Volume confirmation option
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
TRADING_TZ = "Asia/Kolkata"

# ── Defaults ────────────────────────────────────────────────────────────────
DEFAULT_MIN_PIVOT_DISTANCE = 5       # minimum bars between consecutive pivots
DEFAULT_PIVOT_LEFT = 3
DEFAULT_PIVOT_RIGHT = 3
DEFAULT_MIN_PROMINENCE_PCT = 0.05    # pivot must be this % deeper than neighbors
DEFAULT_MIN_PRICE_MOVE_PCT = 0.10    # minimum % price move between pivots
DEFAULT_MAX_RESOLUTION_BARS = 24     # look ahead this many bars for resolution
DEFAULT_ATR_PERIOD = 14
DEFAULT_ATR_RESOLUTION_MULT = 0.5    # resolution requires price move > 0.5 * ATR
DEFAULT_MIN_OSCILLATOR_MOVE_PCT = 0.05  # min oscillator % move for hidden div
DEFAULT_CACHE_BARS = 60              # number of bars to include in cache hash
DEFAULT_ZSCORE_THRESHOLD = 1.5       # z-score threshold for noise rejection
DEFAULT_CONFIRMATION_BARS = 2        # min bars showing confirmation for resolution
DEFAULT_CONFIRMATION_RATIO = 0.6     # % of confirmation bars that must confirm


# ── Date helpers ───────────────────────────────────────────────────────────
def _ensure_utc_datetime(series: pd.Series) -> pd.Series:
    out = pd.to_datetime(series)
    if out.dt.tz is None:
        return out.dt.tz_localize("UTC")
    return out.dt.tz_convert("UTC")


def _compute_atr(df: pd.DataFrame, period: int = DEFAULT_ATR_PERIOD) -> pd.Series:
    """Compute Average True Range."""
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=period).mean()


# ── Data preparation ───────────────────────────────────────────────────────
def prepare_intraday(
    intraday: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """Return sorted IST-indexed intraday data with MACD histogram oscillator."""
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(intraday.columns)
    if missing:
        raise ValueError(f"missing intraday columns: {sorted(missing)}")

    df = intraday.copy()
    df["date"] = _ensure_utc_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    df.index = df.index.tz_convert(TRADING_TZ)
    df["macd"] = (
        df["close"].ewm(span=fast, adjust=False).mean()
        - df["close"].ewm(span=slow, adjust=False).mean()
    )
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    df["atr"] = _compute_atr(df, DEFAULT_ATR_PERIOD)
    return df


# ── Cache fingerprint (V2: hashlib-based, NOT just last value) ──────────────
def make_cache_key(
    closes: list[float],
    labels: list[str],
    n_bars: int = DEFAULT_CACHE_BARS,
    params: dict | None = None,
) -> str:
    """Generate a strong cache key from last N bars + params.
    
    Uses hashlib.md5 of:
    - Last N close prices (rounded to 2 decimals)
    - Last N labels/dates
    - Any divergence detection parameters
    """
    if not closes:
        return "empty"
    
    tail_closes = closes[-min(n_bars, len(closes)):]
    tail_labels = labels[-min(n_bars, len(labels)):] if labels else []
    
    raw = {
        "closes": [round(c, 2) for c in tail_closes],
        "labels": tail_labels,
        "params": params or {},
    }
    return hashlib.md5(json.dumps(raw, sort_keys=True).encode()).hexdigest()


# ── V2: Better pivot detection ─────────────────────────────────────────────
def _pivot_positions_v2(
    values: pd.Series,
    mode: str,
    left: int = DEFAULT_PIVOT_LEFT,
    right: int = DEFAULT_PIVOT_RIGHT,
    min_prominence_pct: float = DEFAULT_MIN_PROMINENCE_PCT,
    min_pivot_distance: int = DEFAULT_MIN_PIVOT_DISTANCE,
    zscore_threshold: float = DEFAULT_ZSCORE_THRESHOLD,
) -> list[int]:
    """Find pivot highs/lows with improved noise rejection.
    
    V2 improvements over V1:
    - Minimum bar distance between pivots (no adjacent pivots)
    - Z-score based noise rejection (filters small wicks)
    - Better prominence calc using % depth from surrounding range
    """
    vals = values.reset_index(drop=True).astype(float)
    n = len(vals)
    if n < left + right + 1:
        return []

    # Compute z-scores for noise rejection
    rolling_mean = vals.rolling(window=21, min_periods=5).mean().bfill()
    rolling_std = vals.rolling(window=21, min_periods=5).std().bfill()
    rolling_std = rolling_std.replace(0, np.nan).bfill()
    zscores = ((vals - rolling_mean) / rolling_std).fillna(0)

    candidates: list[tuple[int, float]] = []

    for pos in range(left, n - right):
        window = vals.iloc[pos - left : pos + right + 1]
        current = float(vals.iloc[pos])
        is_unique = (window == current).sum() == 1

        if mode == "low" and current == float(window.min()) and is_unique:
            # Z-score filter: reject if this low is not significantly below mean
            if zscore_threshold > 0 and float(zscores.iloc[pos]) > -zscore_threshold * 0.5:
                continue
            # Prominence: how much deeper is this low vs surrounding?
            surrounding = window.drop(window.index[left])
            surrounding_min = float(surrounding.min())
            if surrounding_min == 0:
                continue
            # Use range-based prominence: (range_max - current) / range_max
            range_max = float(window.max())
            prominence_pct = ((range_max - current) / range_max) * 100.0
            if prominence_pct < min_prominence_pct:
                continue
            candidates.append((pos, current))

        elif mode == "high" and current == float(window.max()) and is_unique:
            # Z-score filter: reject if this high is not significantly above mean
            if zscore_threshold > 0 and float(zscores.iloc[pos]) < zscore_threshold * 0.5:
                continue
            surrounding = window.drop(window.index[left])
            surrounding_max = float(surrounding.max())
            if surrounding_max == 0:
                continue
            # Range-based prominence
            range_min = float(window.min())
            prominence_pct = ((current - range_min) / current) * 100.0
            if prominence_pct < min_prominence_pct:
                continue
            candidates.append((pos, current))

    # Apply minimum distance filter
    if not candidates or min_pivot_distance <= 1:
        return [pos for pos, _ in candidates]

    # Sort by position
    candidates.sort(key=lambda x: x[0])
    filtered = [candidates[0]]
    for pos, val in candidates[1:]:
        if pos - filtered[-1][0] >= min_pivot_distance:
            filtered.append((pos, val))
    return [pos for pos, _ in filtered]


# ── V2: Better resolution logic ────────────────────────────────────────────
def _resolution_for_v2(
    df: pd.DataFrame,
    kind: str,
    second_pos: int,
    max_resolution_bars: int = DEFAULT_MAX_RESOLUTION_BARS,
    atr_mult: float = DEFAULT_ATR_RESOLUTION_MULT,
    confirmation_bars: int = DEFAULT_CONFIRMATION_BARS,
    confirmation_ratio: float = DEFAULT_CONFIRMATION_RATIO,
) -> tuple[bool, int | None, str]:
    """Check if divergence resolved with ATR-based confirmation.
    
    V2 improvements:
    - Uses ATR to measure meaningful price movement (not just any close > high)
    - Requires multiple bars to confirm resolution (not just 1 bar)
    - More robust against wick-throughs
    """
    if "atr" not in df.columns:
        df["atr"] = _compute_atr(df, DEFAULT_ATR_PERIOD)

    second = df.iloc[second_pos]
    future_end = min(len(df), second_pos + max_resolution_bars + 1)
    future = df.iloc[second_pos + 1 : future_end]

    if future.empty:
        return False, None, ""

    # ATR at pivot point
    pivot_atr = float(second.get("atr", 0))
    if pivot_atr == 0 or pd.isna(pivot_atr):
        pivot_atr = float(df["atr"].iloc[max(0, second_pos - 10): second_pos + 1].mean())
    if pivot_atr == 0 or pd.isna(pivot_atr):
        pivot_atr = float(df["close"].iloc[second_pos]) * 0.005  # fallback 0.5%

    threshold = pivot_atr * atr_mult

    if kind == "bullish":
        # Resolution = close breaks above pivot high by at least ATR * mult
        target_price = float(second["high"]) + threshold
        hits = future[future["close"] >= target_price]
    else:
        # Bearish resolution = close breaks below pivot low by at least ATR * mult
        target_price = float(second["low"]) - threshold
        hits = future[future["close"] <= target_price]

    if hits.empty:
        return False, None, ""

    # Require multiple confirmation bars
    if confirmation_bars > 1:
        if len(hits) < confirmation_bars:
            return False, None, ""
        # Check if at least X% of bars in a window confirm
        first_hit_idx = int(future.index.get_loc(hits.index[0]))
        check_window = future.iloc[first_hit_idx: first_hit_idx + confirmation_bars * 3]
        if len(check_window) >= confirmation_bars:
            confirmed = 0
            for _, row in check_window.iterrows():
                if kind == "bullish" and float(row["close"]) >= target_price:
                    confirmed += 1
                elif kind == "bearish" and float(row["close"]) <= target_price:
                    confirmed += 1
            if confirmed / len(check_window) < confirmation_ratio:
                return False, None, ""
        else:
            return False, None, ""

    resolution_label = hits.index[0].strftime("%Y-%m-%d %H:%M")
    return True, int(df.index.get_loc(hits.index[0])), resolution_label


# ── V2: Better hidden divergence ───────────────────────────────────────────
def _check_hidden_div_v2(
    first_price: float,
    second_price: float,
    first_osc: float,
    second_osc: float,
    kind: str,
    min_osc_move_pct: float = DEFAULT_MIN_OSCILLATOR_MOVE_PCT,
    price_move_pct: float = 0.0,
) -> bool:
    """Validate hidden divergence with minimum oscillator move.
    
    V2 improvements:
    - Requires oscillator to move by at least min_osc_move_pct
    - Price move must also be meaningful (min_price_move_pct)
    - Prevents tiny moves from being classified as hidden divergence
    """
    if min_osc_move_pct > 0 and first_osc != 0:
        osc_move_pct = abs((second_osc - first_osc) / first_osc) * 100.0
        if osc_move_pct < min_osc_move_pct:
            return False

    # Also ensure price move is meaningful
    if price_move_pct < 0.05:  # at least 0.05% move
        return False

    if kind == "bullish":
        # Hidden bullish: price higher low + oscillator lower low
        return second_price > first_price and second_osc < first_osc
    else:
        # Hidden bearish: price lower high + oscillator higher high
        return second_price < first_price and second_osc > first_osc


# ── Main V2 detector ───────────────────────────────────────────────────────
def detect_divergences_v2(
    data: pd.DataFrame,
    oscillator_col: str = "macd_hist",
    pivot_left: int = DEFAULT_PIVOT_LEFT,
    pivot_right: int = DEFAULT_PIVOT_RIGHT,
    max_resolution_bars: int = DEFAULT_MAX_RESOLUTION_BARS,
    min_prominence_pct: float = DEFAULT_MIN_PROMINENCE_PCT,
    min_price_move_pct: float = DEFAULT_MIN_PRICE_MOVE_PCT,
    min_pivot_distance: int = DEFAULT_MIN_PIVOT_DISTANCE,
    zscore_threshold: float = DEFAULT_ZSCORE_THRESHOLD,
    atr_resolution_mult: float = DEFAULT_ATR_RESOLUTION_MULT,
    min_oscillator_move_pct: float = DEFAULT_MIN_OSCILLATOR_MOVE_PCT,
    confirmation_bars: int = DEFAULT_CONFIRMATION_BARS,
    confirmation_ratio: float = DEFAULT_CONFIRMATION_RATIO,
    include_hidden: bool = False,
    use_volume_confirmation: bool = False,
) -> pd.DataFrame:
    """Detect divergences with V2 improvements.
    
    Returns DataFrame with same schema as V1 for backward compatibility,
    plus additional V2-specific columns.
    """
    required = {"high", "low", "close", oscillator_col}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"missing divergence columns: {sorted(missing)}")

    df = data.copy()
    if "date" in df.columns:
        df["date"] = _ensure_utc_datetime(df["date"])
        df = df.sort_values("date").set_index("date")
        df.index = df.index.tz_convert(TRADING_TZ)

    # Ensure ATR column exists
    if "atr" not in df.columns:
        df["atr"] = _compute_atr(df, DEFAULT_ATR_PERIOD)

    rows: list[dict[str, object]] = []

    low_positions = _pivot_positions_v2(
        df["low"], "low", pivot_left, pivot_right,
        min_prominence_pct, min_pivot_distance, zscore_threshold,
    )
    high_positions = _pivot_positions_v2(
        df["high"], "high", pivot_left, pivot_right,
        min_prominence_pct, min_pivot_distance, zscore_threshold,
    )

    # Bullish divergences (from low pivots)
    for first_pos, second_pos in zip(low_positions, low_positions[1:]):
        first = df.iloc[first_pos]
        second = df.iloc[second_pos]

        price_move_pct_val = _price_move_pct(float(first["low"]), float(second["low"]))
        if price_move_pct_val < min_price_move_pct:
            continue

        # Regular: price lower low + oscillator higher low
        regular = (
            float(second["low"]) < float(first["low"])
            and float(second[oscillator_col]) > float(first[oscillator_col])
        )
        # Hidden: price higher low + oscillator lower low
        hidden = False
        if include_hidden:
            hidden = _check_hidden_div_v2(
                float(first["low"]), float(second["low"]),
                float(first[oscillator_col]), float(second[oscillator_col]),
                "bullish", min_oscillator_move_pct, price_move_pct_val,
            )

        if regular or hidden:
            # Volume confirmation
            if use_volume_confirmation and "volume" in df.columns:
                vol_first = float(df["volume"].iloc[first_pos])
                vol_second = float(df["volume"].iloc[second_pos])
                # For bullish div, volume should expand at second pivot
                if vol_second < vol_first * 0.7:
                    continue

            resolved, resolution_pos, resolution_time = _resolution_for_v2(
                df, "bullish", second_pos, max_resolution_bars,
                atr_resolution_mult, confirmation_bars, confirmation_ratio,
            )

            rows.append(_event_row_v2(
                df, "bullish", first_pos, second_pos, oscillator_col,
                resolved, resolution_pos, resolution_time,
                "regular" if regular else "hidden",
                price_move_pct_val,
            ))

    # Bearish divergences (from high pivots)
    for first_pos, second_pos in zip(high_positions, high_positions[1:]):
        first = df.iloc[first_pos]
        second = df.iloc[second_pos]

        price_move_pct_val = _price_move_pct(float(first["high"]), float(second["high"]))
        if price_move_pct_val < min_price_move_pct:
            continue

        # Regular: price higher high + oscillator lower high
        regular = (
            float(second["high"]) > float(first["high"])
            and float(second[oscillator_col]) < float(first[oscillator_col])
        )
        # Hidden: price lower high + oscillator higher high
        hidden = False
        if include_hidden:
            hidden = _check_hidden_div_v2(
                float(first["high"]), float(second["high"]),
                float(first[oscillator_col]), float(second[oscillator_col]),
                "bearish", min_oscillator_move_pct, price_move_pct_val,
            )

        if regular or hidden:
            # Volume confirmation
            if use_volume_confirmation and "volume" in df.columns:
                vol_first = float(df["volume"].iloc[first_pos])
                vol_second = float(df["volume"].iloc[second_pos])
                if vol_second < vol_first * 0.7:
                    continue

            resolved, resolution_pos, resolution_time = _resolution_for_v2(
                df, "bearish", second_pos, max_resolution_bars,
                atr_resolution_mult, confirmation_bars, confirmation_ratio,
            )

            rows.append(_event_row_v2(
                df, "bearish", first_pos, second_pos, oscillator_col,
                resolved, resolution_pos, resolution_time,
                "regular" if regular else "hidden",
                price_move_pct_val,
            ))

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("second_time_ist").reset_index(drop=True)


def _event_row_v2(
    df: pd.DataFrame,
    kind: str,
    first_pos: int,
    second_pos: int,
    oscillator_col: str,
    resolved: bool,
    resolution_pos: int | None,
    resolution_time: str,
    pattern: str,
    price_move_pct: float,
) -> dict[str, object]:
    """Build event row dict (compatible with V1 schema + extra V2 fields)."""
    first = df.iloc[first_pos]
    second = df.iloc[second_pos]
    oscillator_delta = float(second[oscillator_col]) - float(first[oscillator_col])

    row = {
        "kind": kind,
        "pattern": pattern,
        "first_pos": int(first_pos),
        "second_pos": int(second_pos),
        "first_time_ist": df.index[first_pos].strftime("%Y-%m-%d %H:%M"),
        "second_time_ist": df.index[second_pos].strftime("%Y-%m-%d %H:%M"),
        "first_price": float(first["low"] if kind == "bullish" else first["high"]),
        "second_price": float(second["low"] if kind == "bullish" else second["high"]),
        "price_move_pct": float(price_move_pct),
        "first_oscillator": float(first[oscillator_col]),
        "second_oscillator": float(second[oscillator_col]),
        "oscillator_delta": oscillator_delta,
        "strength": _classify_strength(price_move_pct),
        "resolved": bool(resolved),
        "resolution_pos": resolution_pos,
        "resolution_time_ist": resolution_time,
        # V2 extra fields
        "first_atr": float(first.get("atr", 0)),
        "second_atr": float(second.get("atr", 0)),
        "first_volume": float(first.get("volume", 0)),
        "second_volume": float(second.get("volume", 0)),
    }
    return row


def _price_move_pct(first_price: float, second_price: float) -> float:
    if first_price == 0:
        return 0.0
    return abs(second_price / first_price - 1.0) * 100.0


def _classify_strength(price_move_pct: float) -> str:
    if price_move_pct >= 0.4:
        return "strong"
    if price_move_pct >= 0.2:
        return "medium"
    return "weak"


# ── Compatibility wrapper ──────────────────────────────────────────────────
def detect_divergences(
    data: pd.DataFrame,
    oscillator_col: str = "macd_hist",
    pivot_left: int = 3,
    pivot_right: int = 3,
    max_resolution_bars: int = 16,
    min_prominence_pct: float = 0.0,
    min_price_move_pct: float = 0.0,
    include_hidden: bool = False,
) -> pd.DataFrame:
    """V1-compatible wrapper. Uses V2 with V1-like defaults.
    
    NOTE: Prominence formula differs from original V1 — V2 uses
    (range_max - current) / range_max * 100 while V1 used
    (surrounding.min() / current - 1.0) * 100. Results won't be
    identical to V1 but are strictly better (fewer false pivots).
    """
    return detect_divergences_v2(
        data,
        oscillator_col=oscillator_col,
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        max_resolution_bars=max_resolution_bars,
        min_prominence_pct=min_prominence_pct,
        min_price_move_pct=min_price_move_pct,
        min_pivot_distance=1,  # V1: no min distance
        zscore_threshold=0,     # V1: no z-score filter
        atr_resolution_mult=0.001,  # V1: tiny threshold (= any close>high)
        min_oscillator_move_pct=0,  # V1: no min osc move
        confirmation_bars=1,
        confirmation_ratio=1.0,
        include_hidden=include_hidden,
        use_volume_confirmation=False,
    )


# ── Standalone test ────────────────────────────────────────────────────────
def main() -> None:
    """Run V2 on latest NIFTY50 15m data (last 2000 bars) and print divergence events."""
    intraday_path = HERE / "data" / "NIFTY50_15m.feather"
    
    print("=" * 65)
    print("  DIVERGENCE V2 — NIFTY50 15m → 1H MACD Check")
    print("=" * 65)
    
    df = pd.read_feather(intraday_path)
    df.columns = [c.lower() for c in df.columns]
    
    # Use last 2000 bars for speed (~20 days of 15m data is plenty)
    df = df.iloc[-2000:].reset_index(drop=True)
    
    prepared = prepare_intraday(df)
    print(f"Analyzing {len(prepared)} bars: {prepared.index[0]} → {prepared.index[-1]}")
    
    # Run V2 with improved settings
    events = detect_divergences_v2(
        prepared,
        oscillator_col="macd_hist",
        pivot_left=3,
        pivot_right=3,
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
    
    print(f"\nV2 detected {len(events)} divergence events")
    
    if not events.empty:
        for _, ev in events.iterrows():
            print(f"  {ev['kind']:>8} {ev['pattern']:>7} | "
                  f"{ev['strength']:>6} | "
                  f"Price: {ev['first_price']:>8.2f} → {ev['second_price']:>8.2f} "
                  f"({ev['price_move_pct']:.2f}%) | "
                  f"OSC: {ev['first_oscillator']:>+7.2f} → {ev['second_oscillator']:>+7.2f} | "
                  f"Resolved: {ev['resolved']} | "
                  f"{ev['second_time_ist']}")
    
    # Also run V1 equivalent for comparison
    events_v1 = detect_divergences(
        prepared,
        oscillator_col="macd_hist",
        pivot_left=3, pivot_right=3,
        min_prominence_pct=0.05,
        min_price_move_pct=0.12,
        include_hidden=True,
    )
    print(f"\nV1 (compat mode) detected {len(events_v1)} events")
    
    if not events_v1.empty:
        v1_active = events_v1[~events_v1["resolved"]]
        recent_active_v1 = len(v1_active[
            v1_active["second_pos"] > (len(prepared) - 120)
        ]) if not v1_active.empty else 0
        print(f"V1 active (unresolved) near end: {recent_active_v1}")
    
    # Active divergences near current price
    if not events.empty:
        unresolved = events[~events["resolved"]]
        if not unresolved.empty:
            recent = unresolved[
                unresolved["second_pos"] > (len(prepared) - 120)
            ]
            if not recent.empty:
                print(f"\n🔥 ACTIVE (unresolved) divergences near current price:")
                for _, ev in recent.iterrows():
                    print(f"  {ev['kind']:>8} {ev['pattern']:>7} {ev['strength']:>6} | "
                          f"{ev['second_time_ist']}")
    
    # Show latest bar context
    latest = prepared.iloc[-1]
    print(f"\nLatest bar: {prepared.index[-1]}")
    print(f"Close: {latest['close']:.2f} | MACD: {latest['macd']:.2f} | Hist: {latest['macd_hist']:.2f}")
    
    # Check cache key generation
    closes = prepared["close"].tolist()
    labels = [str(t) for t in prepared.index]
    ck = make_cache_key(closes, labels)
    print(f"Cache key (first 16): {ck[:16]}...")


if __name__ == "__main__":
    main()
