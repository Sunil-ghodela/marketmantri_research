"""
multi_tf_divergence.py — Multi-Timeframe Divergence Engine

Detects bullish/bearish MACD divergence across ALL timeframes from available data.
Uses the OG divergence_detector.detect_divergences() for consistent results across
all detection surfaces (dashboard, strategy, analysis scripts).

Resamples 15m → 30m/1h/2h/4h, 1D → 1W/1M. Uses 1m archive where available.

Supports:
  - Regular + Hidden divergence detection on every timeframe
  - Strength classification (strong/medium/weak)
  - Resolution tracking (did price reach divergence target?)
  - Per-timeframe conflict scoring

Usage:
    from multi_tf_divergence import MultiTFDivergenceDetector

    det = MultiTFDivergenceDetector("data/NIFTY50_15m.feather", "data/NIFTY50_1d.feather")
    report = det.run()
    det.print_report(report)
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

from pathlib import Path
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Use the OG divergence detector for consistent results
from divergence_detector import detect_divergences as og_detect_divergences

TRADING_TZ = "Asia/Kolkata"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_ist_index(df: pd.DataFrame, date_col: str = "date") -> pd.DataFrame:
    """Ensure DataFrame has a tz-aware IST DatetimeIndex."""
    df = df.copy()
    if date_col in df.columns:
        df[date_col] = pd.to_datetime(df[date_col])
        if df[date_col].dt.tz is None:
            df[date_col] = df[date_col].dt.tz_localize("UTC")
        df[date_col] = df[date_col].dt.tz_convert(TRADING_TZ)
        df = df.sort_values(date_col).set_index(date_col)
    elif not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert(TRADING_TZ)
    return df


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample OHLCV data to a higher timeframe using pandas rule."""
    df = df.copy()
    for col in ["open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            # Try capitalized
            cap = col.capitalize()
            if cap in df.columns:
                df[col] = df[cap]

    resampled = df.resample(rule).agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["close"])
    return resampled


def _compute_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Compute MACD line, signal, and histogram."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    macd_signal = macd_line.ewm(span=signal, adjust=False).mean()
    macd_hist = macd_line - macd_signal
    return pd.DataFrame({
        "macd": macd_line,
        "macd_signal": macd_signal,
        "macd_hist": macd_hist,
    })


def detect_divergences_on_ohlcv(df: pd.DataFrame, pivot_left: int = 3, pivot_right: int = 3) -> dict:
    """
    Detect bullish/bearish divergence on an OHLCV DataFrame using OG divergence_detector.

    Uses the same detect_divergences() as the dashboard and research scripts for
    consistent results. Supports regular + hidden divergence, strength classification,
    and resolution tracking. This replaces the old inline pivot detection.

    Returns dict with:
      bullish_div: bool — regular bullish divergence detected near latest bars
      bearish_div: bool — regular bearish divergence detected near latest bars
      bullish_count: int — total regular bullish divergences
      bearish_count: int — total regular bearish divergences
      hidden_bullish: bool — hidden bullish divergence near latest bars
      hidden_bearish: bool — hidden bearish divergence near latest bars
      hidden_count: int — total hidden divergences
      last_resolved: bool — was the most recent divergence resolved?
      last_strength: str — strong/medium/weak
      signal: str — 'bullish' | 'bearish' | 'conflict' | 'none'
      macd_hist_latest: float
      close_latest: float
    """
    result = {
        "bullish_div": False,
        "bearish_div": False,
        "bullish_count": 0,
        "bearish_count": 0,
        "hidden_bullish": False,
        "hidden_bearish": False,
        "hidden_count": 0,
        "last_resolved": False,
        "last_strength": "",
        "last_bullish_time": None,
        "last_bearish_time": None,
        "signal": "none",
        "macd_hist_latest": float("nan"),
        "close_latest": float("nan"),
    }

    if len(df) < 30:
        return result

    # Use OG detector with include_hidden=True.
    # _analyze_tf() guarantees macd_hist column exists before calling this.
    events = og_detect_divergences(
        df,
        oscillator_col="macd_hist",
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        max_resolution_bars=16,
        min_prominence_pct=0.0,
        min_price_move_pct=0.0,
        include_hidden=True,
    )

    result["close_latest"] = float(df["close"].iloc[-1])

    if events.empty:
        return result

    n = len(df)
    recent_window = max(10, n // 10)

    # Count and classify all events
    reg_bull = events[(events["kind"] == "bullish") & (events["pattern"] == "regular")]
    reg_bear = events[(events["kind"] == "bearish") & (events["pattern"] == "regular")]
    hidden = events[events["pattern"] == "hidden"]
    hidden_bull = hidden[hidden["kind"] == "bullish"]
    hidden_bear = hidden[hidden["kind"] == "bearish"]

    result["bullish_count"] = len(reg_bull)
    result["bearish_count"] = len(reg_bear)
    result["hidden_count"] = len(hidden)

    # Recency check: most recent event within recent_window bars
    if not reg_bull.empty:
        last_ts = pd.Timestamp(reg_bull["second_time_ist"].iloc[-1])
        last_idx = df.index.get_indexer([last_ts], method="nearest")[0]
        if n - last_idx <= recent_window:
            result["bullish_div"] = True
            result["last_bullish_time"] = str(last_ts)

    if not reg_bear.empty:
        last_ts = pd.Timestamp(reg_bear["second_time_ist"].iloc[-1])
        last_idx = df.index.get_indexer([last_ts], method="nearest")[0]
        if n - last_idx <= recent_window:
            result["bearish_div"] = True
            result["last_bearish_time"] = str(last_ts)

    if not hidden_bull.empty:
        last_ts = pd.Timestamp(hidden_bull["second_time_ist"].iloc[-1])
        last_idx = df.index.get_indexer([last_ts], method="nearest")[0]
        result["hidden_bullish"] = (n - last_idx <= recent_window)

    if not hidden_bear.empty:
        last_ts = pd.Timestamp(hidden_bear["second_time_ist"].iloc[-1])
        last_idx = df.index.get_indexer([last_ts], method="nearest")[0]
        result["hidden_bearish"] = (n - last_idx <= recent_window)

    # Last event metadata
    last_event = events.iloc[-1]
    result["last_resolved"] = bool(last_event["resolved"])
    result["last_strength"] = str(last_event["strength"])

    # Signal: combine regular + hidden
    # Conflict: regular bull AND regular bear both active
    # Bullish: regular bull active (regardless of hidden)
    # Bearish: regular bear active (regardless of hidden)
    # Hidden-only: if only hidden divergence active, signal = bullish/bearish/conflict based on hidden
    if result["bullish_div"] and result["bearish_div"]:
        result["signal"] = "conflict"
    elif result["bullish_div"]:
        result["signal"] = "bullish"
    elif result["bearish_div"]:
        result["signal"] = "bearish"
    elif result["hidden_bullish"] and result["hidden_bearish"]:
        result["signal"] = "conflict"
    elif result["hidden_bullish"]:
        result["signal"] = "bullish"
    elif result["hidden_bearish"]:
        result["signal"] = "bearish"

    return result


# ── Dataclass for results ─────────────────────────────────────────────────────

@dataclass
class TFResult:
    """Result for one timeframe — enriched with hidden div, resolution, strength."""
    timeframe: str
    available: bool
    bars: int = 0
    close: float = 0.0
    change_pct: float = 0.0
    bullish_div: bool = False      # regular bullish
    bearish_div: bool = False       # regular bearish
    bullish_count: int = 0
    bearish_count: int = 0
    hidden_bullish: bool = False
    hidden_bearish: bool = False
    hidden_count: int = 0
    last_resolved: bool = False
    last_strength: str = ""         # strong/medium/weak
    signal: str = "none"
    macd_hist: float = 0.0
    last_bull_time: str = ""
    last_bear_time: str = ""
    error: str = ""


# ── Main detector ─────────────────────────────────────────────────────────────

class MultiTFDivergenceDetector:
    """
    Multi-timeframe divergence detection system.

    Timeframes analyzed (from 15m base):
      1m, 3m, 5m (from Yahoo archive if available)
      15m (direct)
      30m, 1h, 2h, 4h (resampled from 15m)
      1D (direct)
      1W, 1M (resampled from 1D)
    """

    # Timeframes organized by data source
    # LOWER TFs (1m-5m): only available if 1m Yahoo archive exists
    # MEDIUM TFs (15m-4H): from 15m data (downsample only)
    # HIGHER TFs (1D-1MTH): from 1D data (downsample only)
    TIMEFRAMES = [
        # --- From 1m archive (if available) ---
        ("1M", "1min", "m1"),
        ("3M", "3min", "m1"),
        ("5M", "5min", "m1"),
        # --- From 15m data ---
        ("15M", "15min", "m15"),
        ("30M", "30min", "m15"),
        ("1H", "1h", "m15"),
        ("2H", "2h", "m15"),
        ("4H", "4h", "m15"),
        # --- From 1D data ---
        ("1D", "1D", "d1"),
        ("1W", "1W", "d1"),
        ("1MTH", "1M", "d1"),
    ]

    RESAMPLE_MAP = {
        "3min": "3min",
        "5min": "5min",
        "30min": "30min",
        "1h": "1h",
        "2h": "2h",
        "4h": "4h",
        "1W": "1W",
        "1M": "1M",
    }

    def __init__(
        self,
        m15_path: str | Path | None = None,
        d1_path: str | Path | None = None,
        m1_path: str | Path | None = None,
    ):
        self.m15_path = Path(m15_path) if m15_path else None
        self.d1_path = Path(d1_path) if d1_path else None
        self.m1_path = Path(m1_path) if m1_path else None

        self._m15_df: pd.DataFrame | None = None
        self._d1_df: pd.DataFrame | None = None
        self._m1_df: pd.DataFrame | None = None

    def _load_m15(self) -> pd.DataFrame:
        if self._m15_df is not None:
            return self._m15_df
        if self.m15_path and self.m15_path.exists():
            df = pd.read_feather(self.m15_path)
            df.columns = [c.lower() for c in df.columns]
            self._m15_df = _ensure_ist_index(df)
            return self._m15_df
        raise FileNotFoundError(f"15m data not found: {self.m15_path}")

    def _load_d1(self) -> pd.DataFrame:
        if self._d1_df is not None:
            return self._d1_df
        if self.d1_path and self.d1_path.exists():
            df = pd.read_feather(self.d1_path)
            df.columns = [c.lower() for c in df.columns]
            self._d1_df = _ensure_ist_index(df)
            return self._d1_df
        raise FileNotFoundError(f"1D data not found: {self.d1_path}")

    def _load_m1(self) -> pd.DataFrame | None:
        if self._m1_df is not None:
            return self._m1_df
        if self.m1_path and self.m1_path.exists():
            df = pd.read_parquet(self.m1_path)
            df.columns = [c.lower() for c in df.columns]
            self._m1_df = _ensure_ist_index(df)
            return self._m1_df
        return None

    def _analyze_tf(self, df: pd.DataFrame, tf_label: str) -> TFResult:
        """Run divergence detection on a single timeframe DataFrame."""
        if df.empty or len(df) < 30:
            return TFResult(timeframe=tf_label, available=len(df) >= 30, bars=len(df))

        try:
            # Ensure MACD histogram is computed
            if "macd_hist" not in df.columns:
                macd_df = _compute_macd(df["close"])
                df = df.copy()
                df["macd_hist"] = macd_df["macd_hist"]

            div = detect_divergences_on_ohlcv(df)
            close_now = div["close_latest"]
            close_prev = float(df["close"].iloc[-2]) if len(df) >= 2 else close_now
            change = ((close_now / close_prev) - 1.0) * 100 if close_prev != 0 else 0

            return TFResult(
                timeframe=tf_label,
                available=True,
                bars=len(df),
                close=round(close_now, 2),
                change_pct=round(change, 3),
                bullish_div=div["bullish_div"],
                bearish_div=div["bearish_div"],
                bullish_count=div["bullish_count"],
                bearish_count=div["bearish_count"],
                hidden_bullish=div["hidden_bullish"],
                hidden_bearish=div["hidden_bearish"],
                hidden_count=div["hidden_count"],
                last_resolved=div["last_resolved"],
                last_strength=div["last_strength"],
                signal=div["signal"],
                macd_hist=round(div["macd_hist_latest"], 4),
                last_bull_time=div["last_bullish_time"] or "",
                last_bear_time=div["last_bearish_time"] or "",
            )
        except Exception as e:
            return TFResult(timeframe=tf_label, available=False, error=str(e))

    def run(self) -> list[TFResult]:
        """Run multi-timeframe divergence detection. Returns list of TFResult."""
        results: list[TFResult] = []

        # Load data
        try:
            m15 = self._load_m15()
        except FileNotFoundError:
            m15 = None
        try:
            d1 = self._load_d1()
        except FileNotFoundError:
            d1 = None
        m1 = self._load_m1()

        for tf_label, tf_key, source in self.TIMEFRAMES:
            try:
                if source == "m1":
                    # Needs 1m Yahoo archive
                    if m1 is None:
                        results.append(TFResult(timeframe=tf_label, available=False, error="No 1m archive"))
                        continue
                    if tf_key == "1min":
                        resampled = m1
                    else:
                        resampled = _resample_ohlcv(m1, tf_key)
                    results.append(self._analyze_tf(resampled, tf_label))

                elif source == "m15":
                    # From 15m data
                    if m15 is None:
                        results.append(TFResult(timeframe=tf_label, available=False, error="No 15m data"))
                        continue
                    if tf_key == "15min":
                        resampled = m15
                    else:
                        resampled = _resample_ohlcv(m15, tf_key)
                    results.append(self._analyze_tf(resampled, tf_label))

                elif source == "d1":
                    # From 1D data
                    if d1 is None:
                        results.append(TFResult(timeframe=tf_label, available=False, error="No 1D data"))
                        continue
                    if tf_key == "1D":
                        resampled = d1
                    else:
                        resampled = _resample_ohlcv(d1, tf_key)
                    results.append(self._analyze_tf(resampled, tf_label))

                else:
                    results.append(TFResult(timeframe=tf_label, available=False, error="Unknown source"))

            except Exception as e:
                results.append(TFResult(timeframe=tf_label, available=False, error=str(e)))

        return results

    @staticmethod
    def print_report(results: list[TFResult], symbol: str = "NIFTY50") -> str:
        """Print a beautiful multi-timeframe divergence report. Returns the string."""
        lines = []
        lines.append("")
        lines.append(f"{'=' * 80}")
        lines.append(f"  🔍 MULTI-TIMEFRAME DIVERGENCE REPORT — {symbol}")
        lines.append(f"{'=' * 80}")
        lines.append("")

        # Header
        header = f"  {'TF':<6} {'Close':>10} {'Chg%':>8} {'MACD H':>9} {'BullDiv':>8} {'BearDiv':>8} {'HidDiv':>7} {'Str':>5} {'Signal':>12} {'Bars':>6}"
        lines.append(header)
        lines.append(f"  {'-' * 86}")

        for r in results:
            if not r.available:
                status = f"  {r.timeframe:<6} {'N/A':>10} {'N/A':>8} {'N/A':>9} {'N/A':>8} {'N/A':>8} {'N/A':>7} {'N/A':>5} {'N/A':>12} {'--':>6}"
                lines.append(status)
                continue

            # Signal emoji
            sig_map = {
                "bullish": "🟢 BULL",
                "bearish": "🔴 BEAR",
                "conflict": "⚡ CONFLICT",
                "none": "⚪ NONE",
            }
            sig_str = sig_map.get(r.signal, r.signal)

            # Bull/Bear div indicators
            bull_ind = "✅" if r.bullish_div else ("⬆" if r.hidden_bullish else "—")
            bear_ind = "✅" if r.bearish_div else ("⬇" if r.hidden_bearish else "—")

            # Hidden div indicator
            hid_str = f"{r.hidden_count}" if r.hidden_count > 0 else "—"

            # Strength indicator
            str_map = {"strong": "💪", "medium": "👍", "weak": "👎", "": "—"}
            str_ind = str_map.get(r.last_strength, r.last_strength)

            # Change indicator
            chg_str = f"{r.change_pct:+.3f}%"

            # MACD histogram sign
            macd_str = f"{r.macd_hist:+.4f}"

            line = (
                f"  {r.timeframe:<6} {r.close:>10.2f} {chg_str:>8} {macd_str:>9} "
                f"{bull_ind:>8} {bear_ind:>8} {hid_str:>7} {str_ind:>5} {sig_str:>12} {r.bars:>6}"
            )
            lines.append(line)

        # Summary
        lines.append(f"  {'-' * 86}")
        available = [r for r in results if r.available]
        bull_tfs = [r.timeframe for r in available if r.bullish_div]
        bear_tfs = [r.timeframe for r in available if r.bearish_div]
        hidden_bull_tfs = [r.timeframe for r in available if r.hidden_bullish and not r.bullish_div]
        hidden_bear_tfs = [r.timeframe for r in available if r.hidden_bearish and not r.bearish_div]
        conflict_tfs = [r.timeframe for r in available if r.signal == "conflict"]
        resolved_tfs = [r.timeframe for r in available if r.last_resolved]

        if bull_tfs:
            lines.append(f"  🟢 Regular bullish divergence on:    {', '.join(bull_tfs)}")
        else:
            lines.append(f"  🟢 Regular bullish on:                NONE")

        if bear_tfs:
            lines.append(f"  🔴 Regular bearish divergence on:     {', '.join(bear_tfs)}")
        else:
            lines.append(f"  🔴 Regular bearish on:                NONE")

        if hidden_bull_tfs:
            lines.append(f"  ⬆ Hidden bullish (continuation) on:  {', '.join(hidden_bull_tfs)}")
        if hidden_bear_tfs:
            lines.append(f"  ⬇ Hidden bearish (weakening) on:     {', '.join(hidden_bear_tfs)}")

        if conflict_tfs:
            lines.append(f"  ⚡ Conflict zones on:                 {', '.join(conflict_tfs)}")

        lines.append(f"")

        # Resolution summary
        if resolved_tfs:
            lines.append(f"  ✅ Last divergence resolved on: {', '.join(resolved_tfs)}")
        else:
            unresolved = [r.timeframe for r in available if not r.last_resolved and r.signal != "none"]
            if unresolved:
                lines.append(f"  ⚠️ Last divergence UNRESOLVED on: {', '.join(unresolved)}")

        # Overall verdict
        bull_count = sum(1 for r in available if r.signal == "bullish")
        bear_count = sum(1 for r in available if r.signal == "bearish")
        conflict_count = sum(1 for r in available if r.signal == "conflict")

        lines.append("")
        if conflict_count > 2:
            lines.append(f"  📊 VERDICT: MARKET IN TENSION — {conflict_count} timeframes show conflict")
        elif bull_count > bear_count and bull_count >= 3:
            lines.append(f"  📊 VERDICT: BULLISH ALIGNMENT — {bull_count} timeframes bullish, {bear_count} bearish")
        elif bear_count > bull_count and bear_count >= 3:
            lines.append(f"  📊 VERDICT: BEARISH ALIGNMENT — {bear_count} timeframes bearish, {bull_count} bullish")
        else:
            lines.append(f"  📊 VERDICT: MIXED — {bull_count} bull, {bear_count} bear, {conflict_count} conflict")

        lines.append("")
        lines.append(f"{'=' * 80}")

        report = "\n".join(lines)
        print(report)
        return report


# ── CLI entry point ───────────────────────────────────────────────────────────

def main():
    """Run multi-timeframe divergence detection from CLI."""
    import argparse

    parser = argparse.ArgumentParser(description="Multi-Timeframe Divergence Detector")
    parser.add_argument("--symbol", default="NIFTY50", help="Symbol to analyze")
    parser.add_argument("--m15", help="Path to 15m feather file")
    parser.add_argument("--d1", help="Path to 1D feather file")
    parser.add_argument("--m1", help="Path to 1m data (parquet)")
    parser.add_argument("--output", help="Save report to file")
    args = parser.parse_args()

    data_dir = Path(__file__).resolve().parent / "data"

    # Auto-detect paths
    m15_path = args.m15 or data_dir / f"{args.symbol}_15m.feather"
    d1_path = args.d1 or data_dir / f"{args.symbol}_1d.feather"
    m1_path = args.m1 or data_dir / "yahoo_1m_archive" / f"{args.symbol}_NS_1m.parquet"
    if not m1_path.exists():
        m1_path = None

    print(f"\nLoading data for {args.symbol}...")
    det = MultiTFDivergenceDetector(m15_path=m15_path, d1_path=d1_path, m1_path=m1_path)
    results = det.run()
    report = det.print_report(results, symbol=args.symbol)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(report)
        print(f"\nReport saved to: {out_path}")


if __name__ == "__main__":
    main()
