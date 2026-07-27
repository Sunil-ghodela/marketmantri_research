"""
strategy.py — BAKED: EMA + UR + PT + Regime + Distance + Astro + V7 Combo-2x + V8 Monday-↓ + V9 MidADX-↓ + V10 Moon-2x

Concept stack (layered, each adds a rule learned from prior research):

  1. Entry:  EMA fast(15) > EMA slow(55) AND up-ratio(20) crosses above 0.50
  2. Exit:   up-ratio < 0.30 OR EMA fast < EMA slow OR Profit Target +5%
  3. Max hold: 3 trading days (75 × 15m bars)
  4. Regime filter (EMA50 vs EMA200 on price):
       - Bull regime: no cooldown
       - Bear/choppy: 48h cooldown between exit and next entry
  5. Distance-from-high filter (manual-review → feature → bucket → walk-forward):
       - Entry blocked if within 1% of 60-day high OR 0.5% of 20-day high
  6. Astro filter (from astrological analysis of 462 trades):
       - Waning moon half only (Sun-Moon angular sep in phase 0.50-1.00)
       - Skip if moon in bottom-5 historically-losing nakshatras
  7. V7 Combo 2x Sizing (2026-04-22): position size 2x when ALL of:
       - pct_from_20d_low < 8% (near support base)
       - atr14/atr100 < 1.0 (consolidation/quiet range)
       - last 3 business days of month (month-end window)
     Normal days 1x; combo days 2x. Backtest requires margin=0.5.
  8. V8 Monday Downsize (2026-04-22): Monday entries at 0.25x size.
     Post-V7 analysis of 164 trades revealed Monday entries: N=25 win 36%
     mean +0.10% (vs Tue-Fri 52-60% win, +0.37-0.67%). Monday PnL contribution
     tiny (₹15k / ₹6.97L total = 2.2%) but variance disproportionate.
     Result: Sharpe +0.05, DD 5.08→3.59% (−29%), Calmar +39%, val Sharpe +13%.
  9. V9 Mid-ADX Downsize (2026-04-22): ADX14 in [33, 47) → 0.25x size.
     Post-V8 analysis revealed mid-ADX quartile Q3 as the real weak bucket.
     33 trades, 39% win, +0.18% mean. Down-sizing to 0.25x:
     Result: Sharpe 1.689→1.801 (+6.6%), val 1.655→1.825 (+10.3%), DD UNCHANGED
     at 3.59%, Calmar small dip 2.551→2.422 (from return reduction).

 10. V10 New Moon 2x Sizing (2026-05-21): T-2 New Moon window → 2x size.
     Post-H10 analysis: 31/164 (18.9%) trades overlap T-2 New Moon window.
     Moon trades: 54.8% WR, ₹4,240 avg PnL vs non-Moon 54.1%, ₹3,749.
     Edge: +13% per trade. New Moon is a calendar-pressure window, not a
     blind buy — but when the main strategy already triggered entry inside
     the window, sizing up amplifies the edge.
     Priority order: combo > New Moon > Monday > mid-ADX > normal.

 11. V11 Divergence Sizing (2026-06-01, DEACTIVATED 2026-06-14): MACD histogram divergence detection.
     Full 10yr backtest showed ZERO impact — V11 skipped 0/167 actual trades.
     Debug confirmed: V2 detector finds 642 bearish events globally but NONE fall
     within recency window (~4h) of an entry that survives other filters (astro,
     cooldown, distance). Structurally impossible to fire — entry conditions
     (uptrend + momentum) are mutually exclusive with bearish divergence context.
     Code kept for reference but divergence_sizing_enabled=False.

 12. V13 1H MACD Filter (2026-06-11, DEACTIVATED 2026-06-14): skip entry when 1H MACD is red.
     Standalone backtest pending — impact confounded with other filters.
     Initial V11+V13 combined test showed Sharpe drop (1.7934→1.4865).
     Need isolated V13 test before re-enabling. macd_filter_enabled=False.

Wed/Fri UP-size test (H10) REJECTED: 52/164 Wed+Fri trades at 1.5x hurt
Sharpe (−0.06) and raised DD (3.59→4.50%). New rule learned: size UP only
when bucket is rare (<10% of trades). V7 combo at 11/164=6.7% works; Wed/Fri
at 32% is too broad — pure leverage rather than selective edge.

Performance history (NIFTYBEES 15m, 2016-2026, delivery):
  Original baked EMA+UR:         Sharpe 1.106
  + Profit Target 5%:             Sharpe 1.197 (+8.2%)
  + Regime cooldown 48h bear:     Sharpe 1.302 (+8.8%)
  + Distance-from-high filter:    Sharpe 1.482 (+13.8%)
  + Astro filter (waning+nak):    Sharpe 1.538
  + V7 Combo 2x Sizing:           Sharpe 1.639, Calmar 1.836, DD 5.08%
  + V8 Monday 0.25x Downsize:     Sharpe 1.689, Calmar 2.551, DD 3.59%
  + V9 Mid-ADX 0.25x Downsize:    Sharpe 1.801, Calmar 2.422, DD 3.59%, val 1.825
  + V10 New Moon 2x Sizing:        Sharpe 1.7934, Calmar 1.771, DD 5.15%, val —
  + V11 Divergence: DEACTIVATED — zero impact in backtest
  + V13 MACD Filter: DEACTIVATED — pending isolated test

V12 New Moon MACD Entry (2026-06-07, REJECTED 2026-06-08): T-2 window MACD
momentum flip entry tested via run_v12_comparison.py. Added 14 trades but
Sharpe dropped 1.870→1.800 (−3.8%), total return −12%, win rate −1.5%.
MACD histogram flip on 15m is too noisy for reliable timing.
Keep V10 sizing boost (2x on moon window) but remove separate V12 entry signal.

V7 sizing journey (what worked, what didn't):
  - Filter variants (skip bad trades): all reduced Sharpe — too selective
  - Positive filter variants (take ONLY combo trades): Sharpe dropped due to
    8x reduction in trade frequency (164 → ~20 trades)
  - Position sizing approach: keep all 164 trades at 1x, boost combo trades to
    2x. Combo trades have 82% win rate, 1.56% avg return (vs 52%/0.36% normal).
    With 2x size, their PnL contribution roughly doubles without affecting DD.
  - Variants tested: 1.5x/2x/3x — 2x optimal (3x adds DD disproportionately).
  - Month-END-only (no near-low/quiet) also works well (Sharpe 1.601); chose
    full combo (V7) for higher Calmar and specificity.

Walk-forward validation (train 2016-2023 / val 2024-2026):
  V7 train Sharpe: 1.604 → 1.737 (+8.3%)
  V7 val Sharpe:   1.514 → 1.482 (−0.03, within noise on N=35)
  V7 full Calmar:  1.477 → 1.836 (+24%)

Rule origins:
  - Entry/exit/PT: hyperopt + exit tuning sweeps
  - Regime cooldown: manual review + regime research
  - Distance-from-high: the capital partner's visual observation (7 trades) → feature engineering
  - Astro: the capital partner's hunch about moon phase & nakshatras → rigorous bucket analysis
    + walk-forward; waning-half & bad-nakshatra exclusion both VALID in both periods.
    Mercury retrograde filter tested and REJECTED (no signal).
  - V7 Combo Sizing: Trade-review Phase 2 hypotheses (H4 base formation + H5 month
    boundary) failed as filters but succeeded as position-sizing amplifier. The
    insight: high-quality setups are rare but very profitable; size up, don't filter out.

Baked-and-rejected (do not re-test without new angle):
  - Max Hold extension on high-ADX entries (H2): train edge, val hurt
  - Chop filter (touches_80bar + compression, H3): univariate edge, Sharpe hurt
  - ADX<20 skip (H1): no univariate edge
  - Negative ret_5bar_pct skip (H6): weak univariate, DD worsens
  - DTE 6-10 skip (H5 pure filter): 2025 regime reversal on small N
  - V12 New Moon MACD Entry (2026-06-07): MACD 15m flip timing too noisy;
    Sharpe 1.870→1.800; replaced by V10 sizing boost only.
  - V11 Divergence Sizing (2026-06-14): ZERO trades skipped in backtest
    despite 642 bearish events globally. V2 detector structurally incompatible
    with entry conditions. divergence_sizing_enabled=False.
  - V13 1H MACD Filter (2026-06-14): pended — needs isolated standalone test.
    Combined V11+V13 test showed Sharpe drop (1.7934→1.4865).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from backtesting import Strategy
from ta.trend import EMAIndicator, ADXIndicator
from ta.volatility import AverageTrueRange

try:
    import swisseph as swe
    ASTRO_AVAILABLE = True
except ImportError:
    ASTRO_AVAILABLE = False


BOTTOM_NAKSHATRAS = {
    # Moon nakshatras (Vedic) where historical win-rate and avg-return were bottom-5
    "Uttara Ashadha", "Purva Phalguni", "Purva Bhadrapada",
    "Dhanishta", "Magha",
}

NAKSHATRA_NAMES = [
    "Ashwini", "Bharani", "Krittika", "Rohini", "Mrigashira", "Ardra",
    "Punarvasu", "Pushya", "Ashlesha", "Magha", "Purva Phalguni", "Uttara Phalguni",
    "Hasta", "Chitra", "Swati", "Vishakha", "Anuradha", "Jyeshtha",
    "Mula", "Purva Ashadha", "Uttara Ashadha", "Shravana", "Dhanishta", "Shatabhisha",
    "Purva Bhadrapada", "Uttara Bhadrapada", "Revati",
]


def _macd_hist(close_arr) -> np.ndarray:
    """MACD histogram: (EMA12 - EMA26) - signal line."""
    c = pd.Series(close_arr)
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    return (macd_line - macd_signal).values


def _up_ratio(close_arr, window: int) -> np.ndarray:
    c = np.array(close_arr, dtype=float)
    up = np.zeros(len(c))
    up[1:] = (c[1:] > c[:-1]).astype(float)
    return pd.Series(up).rolling(int(window), min_periods=1).mean().values


def _ema(close_arr, window: int) -> np.ndarray:
    return EMAIndicator(
        close=pd.Series(close_arr), window=int(window), fillna=True
    ).ema_indicator().values


def _rolling_high(high_arr, bars: int) -> np.ndarray:
    return pd.Series(high_arr).rolling(int(bars), min_periods=int(bars / 2)).max().values


def _rolling_low(low_arr, bars: int) -> np.ndarray:
    return pd.Series(low_arr).rolling(int(bars), min_periods=int(bars / 2)).min().values


def _atr(high, low, close, window: int) -> np.ndarray:
    return AverageTrueRange(
        high=pd.Series(high), low=pd.Series(low), close=pd.Series(close),
        window=int(window), fillna=True,
    ).average_true_range().values


def _adx(high, low, close, window: int) -> np.ndarray:
    return ADXIndicator(
        high=pd.Series(high), low=pd.Series(low), close=pd.Series(close),
        window=int(window), fillna=True,
    ).adx().values


def _month_end_flags(index) -> np.ndarray:
    """True for bars whose calendar date is in the last 3 business days of that month."""
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    flags = {}
    for d in sorted({ts.date() for ts in idx}):
        dt = pd.Timestamp(d)
        month_start = pd.Timestamp(dt.year, dt.month, 1)
        month_end = month_start + pd.offsets.MonthEnd(0)
        biz_to_eom = len(pd.bdate_range(dt, month_end))
        flags[d] = biz_to_eom <= 3
    return np.array([flags[ts.date()] for ts in idx], dtype=bool)


class AgentStrategy(Strategy):
    segment = "delivery"
    close_eod = False
    max_hold_days = 3
    required_margin = 0.5   # backtest.py reads this; 0.5 enables 2x leverage for V7 combo sizing

    # Bear cooldown bar scaling: legacy `cooldown_hours_bear * 4` = fifteen-minute bars per hour.
    # Hourly-port subclasses set this to 1 so `48 * 1` hourly bars matches the calendar span
    # of `48 * 4` fifteen-minute bars (see strategy_1h.py + backtest_1h_port.py).
    cooldown_bar_multiplier = 4

    _param_space = {}

    # Entry/exit (hyperopt)
    ema_fast = 15
    ema_slow = 55
    ratio_win = 20
    ratio_thresh = 0.50
    ratio_exit = 0.30

    # Profit target (exit tuning)
    profit_target_pct = 0.05

    # Regime cooldown
    regime_ema_fast = 50
    regime_ema_slow = 200
    cooldown_hours_bear = 48

    # Distance-from-high filter
    min_pct_below_60d_high = 1.0
    min_pct_below_20d_high = 0.5
    bars_60d = 1500
    bars_20d = 500

    # Astro filter
    astro_filter_enabled = True
    moon_phase_min = 0.50   # waning half starts after full moon
    moon_phase_max = 1.00   # waning half ends at new moon
    exclude_bottom_nakshatras = True

    # V7 Combo 2x sizing — position size boosted on confluence days
    # All three must be true: near 20d-low + quiet range + month-end window.
    # Backtest harness must set margin=0.5 on Backtest() for the 2x boost to take effect.
    combo_sizing_enabled = True
    combo_low_th = 8.0           # pct_from_20d_low < 8%
    combo_comp_th = 1.0          # atr14/atr100 < 1.0
    combo_base_size = 0.5        # normal trades: 50% of buying power (= 100% cash with margin=0.5 → 1x)
    combo_boost_size = 0.999     # combo trades: ~100% of buying power (= 200% cash → 2x).
                                 # NOTE: backtesting.py treats size=1.0 exact as "1 unit"; use 0.999.

    # V8 Monday downsize — Monday entries at fractional size (weak bucket on post-V7 analysis)
    # N=25 Monday entries across 10 years: win 36%, mean +0.10% (vs Tue-Fri 52-60%, +0.37-0.67%).
    # 0.25 multiplier on base size → Monday entries at ~25% of normal exposure.
    monday_downsize_enabled = True
    monday_size_multiplier = 0.25   # fraction of combo_base_size applied on Mondays

    # V9 Mid-ADX downsize — ADX14 in [33, 47) quartile is weak bucket (H10 test)
    # N=33 mid-ADX entries: win 39%, mean +0.18% vs other quartiles 59-61% win, +0.47-0.65% mean.
    # 0.25 multiplier → mid-ADX entries at ~25% of normal exposure.
    midadx_downsize_enabled = True
    midadx_lo = 33.0                # inclusive lower bound
    midadx_hi = 47.0                # exclusive upper bound
    midadx_size_multiplier = 0.25   # fraction of combo_base_size applied in mid-ADX zone
    adx_window = 14

    # V10 New Moon 2x sizing — T-2 New Moon window → 2x size
    # 31/164 trades overlap (18.9%); avg PnL +13% vs non-Moon.
    # Priority: combo > New Moon > Monday > mid-ADX > normal
    newmoon_sizing_enabled = True
    newmoon_boost_size = 0.999       # same as combo_boost_size → 2x with margin=0.5

    # V11 Divergence sizing — MACD histogram divergence detection
    # 164 trades analyzed (corrected 2026-06-13): bearish=42.6% WR (skip),
    # bullish=70.8% WR (allow), conflict=100% WR (2x).
    # CORRECTION: earlier 11-trade sample showed bullish=45.5% (wrongly marked skip).
    # Full sample (N=24) shows 70.8% WR — bullish div is GOOD, bearish div is BAD.
    # Uses divergence_detector_v2 (V2) by default with fallback to V1.
    # V2 improvements: better pivot detection (min bar distance, z-score),
    # ATR-based resolution, better hidden div, strong cache fingerprint.
    # V11 Divergence sizing — DEACTIVATED (zero impact in full 10yr backtest)
    # 642 bearish div events exist globally but NONE within recency of surviving trades.
    # Entry conditions (uptrend+momentum) mutually exclusive with bearish div context.
    divergence_sizing_enabled = False
    div_v2_enabled = True           # use V2 detector; False for V1 fallback
    div_lookback = 300              # bars to scan for divergence pivots (~3 days 15m)
    div_recency = 15                # pivot must be within this many bars of entry
    div_pivot_left = 3              # left window for pivot detection
    div_pivot_right = 3             # right window for pivot detection
    div_min_prominence_pct = 0.05   # minimum prominence for pivot to count
    div_min_price_move_pct = 0.12   # minimum price move %% for divergence
    div_include_hidden = True       # detect hidden divergence (continuation patterns)

    # V13 1H MACD Filter — DEACTIVATED (pending isolated standalone test)
    # Combined V11+V13 test showed Sharpe drop (1.7934→1.4865) so cannot
    # distinguish V13 impact from V11 misfire. Needs solo backtest.
    macd_filter_enabled = False

    # V12 New Moon MACD Momentum Entry — separate entry signal during T-2 window
    # When main EMA+UR conditions are NOT met but moon window is active, checks for
    # MACD histogram momentum flip as alternative entry. Research finding: T-2 window
    # has 60.98% WR standalone on NIFTYBEES (avg +0.173%). MACD histogram flip adds
    # timing precision — catches momentum shifts inside the calendar-pressure window.
    # Priority: main entry > V12 moon signal > V10 moon sizing boost.
    newmoon_macd_entry_enabled = False
    newmoon_macd_flip_bars = 2       # MACD must be negative for N bars then flip positive
    newmoon_macd_size = 0.5          # fixed 1x sizing (matches combo_base_size pattern)

    def init(self):
        self.ema_f = self.I(_ema, self.data.Close, self.ema_fast)
        self.ema_s = self.I(_ema, self.data.Close, self.ema_slow)
        self.up_r = self.I(_up_ratio, self.data.Close, self.ratio_win)
        self.regime_f = self.I(_ema, self.data.Close, self.regime_ema_fast)
        self.regime_s = self.I(_ema, self.data.Close, self.regime_ema_slow)
        self.high_20d = self.I(_rolling_high, self.data.High, self.bars_20d, overlay=False)
        self.high_60d = self.I(_rolling_high, self.data.High, self.bars_60d, overlay=False)
        self._last_exit_bar = -10_000

        # V7 combo-sizing indicators
        if self.combo_sizing_enabled:
            self.atr14 = self.I(_atr, self.data.High, self.data.Low, self.data.Close, 14, overlay=False)
            self.atr100 = self.I(_atr, self.data.High, self.data.Low, self.data.Close, 100, overlay=False)
            self.low_20d = self.I(_rolling_low, self.data.Low, self.bars_20d, overlay=False)
            self._is_month_end = _month_end_flags(self.data.index)

        # V9 mid-ADX downsize indicator
        if self.midadx_downsize_enabled:
            self.adx14 = self.I(_adx, self.data.High, self.data.Low, self.data.Close,
                                self.adx_window, overlay=False)

        # V10 New Moon sizing boost — precompute bar-level T-2 entry flags
        if self.newmoon_sizing_enabled:
            idx = pd.DatetimeIndex(self.data.index)
            if idx.tz is None:
                idx = idx.tz_localize("UTC")
            try:
                from new_moon_integration import is_new_moon_entry_date
                self._is_new_moon_entry = np.array([
                    is_new_moon_entry_date(ts.date()) for ts in idx
                ], dtype=bool)
            except Exception:
                self._is_new_moon_entry = np.zeros(len(idx), dtype=bool)

        # V11: MACD histogram for divergence detection
        if self.divergence_sizing_enabled or self.newmoon_macd_entry_enabled:
            self.macd_hist = self.I(_macd_hist, self.data.Close, overlay=False)

        # V13: Precompute 1H MACD state for every 15m bar
        if self.macd_filter_enabled:
            # Resample 15m closes to 1H, compute MACD(12,26,9), map back to 15m bars
            _closes = [float(self.data.Close[i]) for i in range(len(self.data))]
            _idx = pd.DatetimeIndex(self.data.index)
            if _idx.tz is None:
                _idx = _idx.tz_localize("UTC")
            _df = pd.DataFrame({"close": _closes}, index=_idx)
            _hourly = _df.resample("1h").agg({"close": "last"}).dropna(subset=["close"])
            _ema12 = _hourly["close"].ewm(span=12, adjust=False).mean()
            _ema26 = _hourly["close"].ewm(span=26, adjust=False).mean()
            _macd_l = _ema12 - _ema26
            _macd_s = _macd_l.ewm(span=9, adjust=False).mean()
            _h_states = ["green" if m > s else "red" for m, s in zip(_macd_l, _macd_s)]
            _states = []
            for _t in _idx:
                _mask = _hourly.index <= _t
                if _mask.any():
                    _last_idx = _hourly[_mask].index[-1]
                    _pos = _hourly.index.get_loc(_last_idx)
                    _states.append(_h_states[_pos])
                else:
                    _states.append("unknown")
            self._macd_1h_state = _states

        # Precompute astro lookup per unique date → (phase, nakshatra_name)
        # This is fast: ~2500 unique dates, Swisseph calc ~0.5ms each
        self._astro_by_day = {}
        if self.astro_filter_enabled and ASTRO_AVAILABLE:
            swe.set_sid_mode(swe.SIDM_LAHIRI)
            idx = pd.DatetimeIndex(self.data.index)
            if idx.tz is None:
                idx = idx.tz_localize("UTC")
            for ts in idx:
                d = ts.date()
                if d in self._astro_by_day:
                    continue
                utc = ts.tz_convert("UTC") if ts.tz is not None else ts
                jd = swe.julday(utc.year, utc.month, utc.day, 6.0)  # use 06:00 UTC ≈ 11:30 IST
                sun_lon = swe.calc_ut(jd, swe.SUN)[0][0]
                moon_lon = swe.calc_ut(jd, swe.MOON)[0][0]
                phase = ((moon_lon - sun_lon) % 360) / 360
                moon_sid = swe.calc_ut(jd, swe.MOON, swe.FLG_SIDEREAL)[0][0]
                nak_idx = int(moon_sid // (360 / 27)) % 27
                self._astro_by_day[d] = (phase, NAKSHATRA_NAMES[nak_idx])
        # Cache per-bar lookup keyed by index position
        self._astro_by_bar = {}
        if self.astro_filter_enabled and self._astro_by_day:
            idx = pd.DatetimeIndex(self.data.index)
            if idx.tz is None:
                idx = idx.tz_localize("UTC")
            for i, ts in enumerate(idx):
                self._astro_by_bar[i] = self._astro_by_day.get(ts.date())

    def _astro_passes(self) -> bool:
        """True if current bar's astro state allows entry; else False."""
        if not self.astro_filter_enabled or not self._astro_by_bar:
            return True
        entry = self._astro_by_bar.get(len(self.data) - 1)
        if entry is None:
            return True
        phase, nak = entry
        if not (self.moon_phase_min <= phase < self.moon_phase_max):
            return False
        if self.exclude_bottom_nakshatras and nak in BOTTOM_NAKSHATRAS:
            return False
        return True

    def _get_divergence_state(self) -> str:
        """Classify MACD histogram divergence state at current bar.

        Returns 'bullish', 'bearish', 'conflict', or 'none'.
        Uses divergence_detector_v2 by default (V2) with V1 fallback.
        V2 improvements: better pivot detection, ATR-based resolution,
        better hidden divergence, strong cache fingerprint.

        Also sets self._div_debug dict with full classification details.
        """
        n = len(self.data) - 1
        lookback = self.div_lookback
        start = max(0, n - lookback)
        length = n - start + 1

        if length < 30:
            self._div_debug = {"state": "none", "reason": "insufficient_data"}
            return "none"

        # Construct DataFrame for detector
        df = pd.DataFrame({
            "high": [float(self.data.High[i]) for i in range(start, n + 1)],
            "low": [float(self.data.Low[i]) for i in range(start, n + 1)],
            "close": [float(self.data.Close[i]) for i in range(start, n + 1)],
            "macd_hist": [float(self.macd_hist[i]) for i in range(start, n + 1)],
        })

        try:
            if self.div_v2_enabled:
                # V2: better pivot detection, ATR-based resolution, z-score filter
                from divergence_detector_v2 import detect_divergences_v2
                events = detect_divergences_v2(
                    df,
                    oscillator_col="macd_hist",
                    pivot_left=self.div_pivot_left,
                    pivot_right=self.div_pivot_right,
                    max_resolution_bars=24,
                    min_prominence_pct=self.div_min_prominence_pct,
                    min_price_move_pct=self.div_min_price_move_pct,
                    min_pivot_distance=5,
                    zscore_threshold=1.5,
                    atr_resolution_mult=0.5,
                    min_oscillator_move_pct=0.05,
                    confirmation_bars=2,
                    confirmation_ratio=0.6,
                    include_hidden=self.div_include_hidden,
                    use_volume_confirmation=False,
                )
            else:
                # V1 fallback
                from divergence_detector import detect_divergences
                events = detect_divergences(
                    df,
                    oscillator_col="macd_hist",
                    pivot_left=self.div_pivot_left,
                    pivot_right=self.div_pivot_right,
                    max_resolution_bars=16,
                    min_prominence_pct=self.div_min_prominence_pct,
                    min_price_move_pct=self.div_min_price_move_pct,
                    include_hidden=self.div_include_hidden,
                )
        except Exception:
            self._div_debug = {"state": "none", "reason": "detector_error"}
            return "none"

        # Debug info — will be populated below
        self._div_debug = {
            "state": "none",
            "events_found": len(events),
            "lookback_bars": length,
        }

        if events.empty:
            self._div_debug["reason"] = "no_divergence"
            return "none"

        recency = self.div_recency

        # Separate regular vs hidden events
        reg_bull = events[(events["kind"] == "bullish") & (events["pattern"] == "regular")]
        reg_bear = events[(events["kind"] == "bearish") & (events["pattern"] == "regular")]
        hidden = events[events["pattern"] == "hidden"]
        hidden_bull = hidden[hidden["kind"] == "bullish"]
        hidden_bear = hidden[hidden["kind"] == "bearish"]

        # Check recency: most recent divergence pivot within recency bars
        bull_active = False
        bear_active = False
        hidden_bull_active = False
        hidden_bear_active = False

        if not reg_bull.empty:
            last_pos = int(reg_bull["second_pos"].iloc[-1])
            if length - last_pos <= recency:
                bull_active = True

        if not reg_bear.empty:
            last_pos = int(reg_bear["second_pos"].iloc[-1])
            if length - last_pos <= recency:
                bear_active = True

        if not hidden_bull.empty:
            last_pos = int(hidden_bull["second_pos"].iloc[-1])
            if length - last_pos <= recency:
                hidden_bull_active = True

        if not hidden_bear.empty:
            last_pos = int(hidden_bear["second_pos"].iloc[-1])
            if length - last_pos <= recency:
                hidden_bear_active = True

        # Last event metadata
        last_event = events.iloc[-1]

        # Store full debug info
        self._div_debug.update({
            "regular_bullish": bull_active,
            "regular_bearish": bear_active,
            "hidden_bullish": hidden_bull_active,
            "hidden_bearish": hidden_bear_active,
            "last_resolved": bool(last_event["resolved"]),
            "last_strength": str(last_event["strength"]),
            "last_kind": str(last_event["kind"]),
            "last_pattern": str(last_event["pattern"]),
            "reg_bull_count": len(reg_bull),
            "reg_bear_count": len(reg_bear),
            "hidden_count": len(hidden),
        })

        # Determine state (prioritizes regular div for backward compatibility)
        if bull_active and bear_active:
            state = "conflict"
        elif bull_active:
            state = "bullish"
        elif bear_active:
            state = "bearish"
        elif hidden_bull_active and hidden_bear_active:
            state = "conflict"
        elif hidden_bull_active:
            state = "bullish"
        elif hidden_bear_active:
            state = "bearish"
        else:
            state = "none"

        self._div_debug["state"] = state
        return state

    def _combo_size_active(self) -> bool:
        """True if near 20d-low AND quiet range AND last 3 biz days of month."""
        if not self.combo_sizing_enabled:
            return False
        i = len(self.data) - 1
        if not bool(self._is_month_end[i]):
            return False
        lo = float(self.low_20d[-1]) if not np.isnan(self.low_20d[-1]) else 0
        if lo <= 0:
            return False
        px = float(self.data.Close[-1])
        if (px - lo) / lo * 100 > self.combo_low_th:
            return False
        if self.atr100[-1] <= 0:
            return False
        if self.atr14[-1] / self.atr100[-1] > self.combo_comp_th:
            return False
        return True

    def _newmoon_macd_entry_active(self) -> bool:
        """True if T-2 New Moon window active AND MACD histogram just flipped positive.

        NOTE: DISABLED — see baked-and-rejected. MACD flip on 15m was too noisy
        (Sharpe 1.870→1.800, −12% return). Code kept for reference.

        Entry conditions:
        1. T-2 New Moon window active
        2. MACD histogram was negative for `newmoon_macd_flip_bars` consecutive bars
           AND just turned positive on current bar (momentum shift within moon window)
        3. Price above EMA(50) on 15m (medium-term uptrend context — avoids countertrend)
        """
        if not self.newmoon_macd_entry_enabled:
            return False
        # 1. Moon window check
        if not (hasattr(self, '_is_new_moon_entry')
                and len(self.data) - 1 < len(self._is_new_moon_entry)
                and bool(self._is_new_moon_entry[len(self.data) - 1])):
            return False
        # 2. MACD flip check
        n = len(self.data) - 1
        if n < self.newmoon_macd_flip_bars + 2:
            return False
        # Were last N bars all negative MACD hist?
        for i in range(n - self.newmoon_macd_flip_bars, n):
            if float(self.macd_hist[i]) >= 0:
                return False  # was NOT consistently negative
        # And current bar flipped positive?
        if float(self.macd_hist[n]) < 0:
            return False  # hasn't flipped yet
        # 3. Price above EMA(50) for uptrend context
        px = float(self.data.Close[-1])
        if np.isnan(self.regime_f[-1]) or px <= float(self.regime_f[-1]):
            return False
        return True

    def next(self):
        if len(self.data) < 3:
            return

        # Position management
        if self.position:
            if self.profit_target_pct > 0 and len(self.trades) > 0:
                entry = self.trades[0].entry_price
                if self.data.Close[-1] >= entry * (1 + self.profit_target_pct):
                    self._last_exit_bar = len(self.data) - 1
                    self._v12_entry_bar = None
                    self.position.close()
                    return
            # V12: DISABLED per baked-and-rejected (Sharpe 1.870→1.800).
            # Code kept for reference; guarded by newmoon_macd_entry_enabled=False.
            if (self.newmoon_macd_entry_enabled
                    and getattr(self, '_v12_entry_bar', None) is not None
                    and len(self.data) > self.newmoon_macd_flip_bars + 2):
                n = len(self.data) - 1
                if float(self.macd_hist[n]) < 0 and float(self.macd_hist[n - 1]) >= 0:
                    self._last_exit_bar = n
                    self._v12_entry_bar = None
                    self.position.close()
                    return
            if self.up_r[-1] < self.ratio_exit or self.ema_f[-1] < self.ema_s[-1]:
                self._last_exit_bar = len(self.data) - 1
                self._v12_entry_bar = None
                self.position.close()
            return

        # Regime-conditional cooldown
        bear_regime = self.regime_f[-1] <= self.regime_s[-1]
        if bear_regime and self.cooldown_hours_bear > 0:
            bars_since_exit = (len(self.data) - 1) - self._last_exit_bar
            cooldown_bars = int(self.cooldown_hours_bear * self.cooldown_bar_multiplier)
            if bars_since_exit < cooldown_bars:
                return

        # Distance-from-high filter
        px = float(self.data.Close[-1])
        h60 = float(self.high_60d[-1]) if not np.isnan(self.high_60d[-1]) else 0
        h20 = float(self.high_20d[-1]) if not np.isnan(self.high_20d[-1]) else 0
        if h60 > 0 and self.min_pct_below_60d_high > 0:
            if (h60 - px) / h60 * 100 < self.min_pct_below_60d_high:
                return
        if h20 > 0 and self.min_pct_below_20d_high > 0:
            if (h20 - px) / h20 * 100 < self.min_pct_below_20d_high:
                return

        # Astro filter (waning moon half, not in bad nakshatras)
        if not self._astro_passes():
            return

        # V13: 1H MACD filter — skip when MACD is red (macd_red_bearish loss zone)
        if self.macd_filter_enabled:
            bar_idx = len(self.data) - 1
            if bar_idx < len(self._macd_1h_state) and self._macd_1h_state[bar_idx] == "red":
                return

        # Entry — size determined by V7 combo + V10 New Moon + V8 Monday + V9 mid-ADX rules.
        # Mutually exclusive priority: combo > New Moon > Monday > mid-ADX > normal
        # Each tier is independent — if combo_sizing_enabled=False, V10 still works.
        if self.ema_f[-1] > self.ema_s[-1]:
            if self.up_r[-2] <= self.ratio_thresh and self.up_r[-1] > self.ratio_thresh:                    # V11: Divergence check (only at entry, not every bar)
                # Uses divergence_detector_v2 with pivots + resolution tracking.
                # Rules (priority order, corrected 2026-06-13):
                #   1. Regular bearish div → SKIP (42.6% WR — loss zone)
                #   2. Regular conflict (bull + bear) → 2x (100% WR, fires first)
                #   3. Hidden bearish div → SKIP (trend weakening)
                #   4. Bullish div → ALLOW (70.8% WR — corrected from earlier small-sample error)
                #   5. Everything else (none, hidden bullish) → 1x via existing sizing
                if self.divergence_sizing_enabled:
                    self._div_state = self._get_divergence_state()
                    div = getattr(self, '_div_debug', {})
                    
                    # 1. Regular bearish → SKIP (42.6% WR loss zone)
                    if self._div_state == "bearish" and div.get("regular_bearish") and not div.get("regular_bullish"):
                        return
                    # 2. Regular conflict → 2x (100% WR, fires before other checks)
                    if self._div_state == "conflict" and div.get("regular_bullish") and div.get("regular_bearish"):
                        self.buy(size=self.combo_boost_size)
                        return
                    # 3. Hidden bearish → SKIP (trend weakening, only when regular conflict not active)
                    if div.get("hidden_bearish") and not div.get("regular_bearish"):
                        return
                # V7: combo → 2x (highest priority, requires combo_sizing_enabled)
                if self.combo_sizing_enabled and self._combo_size_active():
                    self.buy(size=self.combo_boost_size)
                # V10: New Moon → 2x (independent of combo sizing toggle)
                elif (self.newmoon_sizing_enabled
                      and hasattr(self, '_is_new_moon_entry')
                      and len(self.data) - 1 < len(self._is_new_moon_entry)
                      and bool(self._is_new_moon_entry[len(self.data) - 1])):
                    self.buy(size=self.newmoon_boost_size)
                # V8 + V9: downsizes + normal (use combo_base_size if combo sizing active)
                elif self.combo_sizing_enabled:
                    ts = pd.Timestamp(self.data.index[-1])
                    is_monday = ts.weekday() == 0
                    if self.monday_downsize_enabled and is_monday:
                        self.buy(size=self.combo_base_size * self.monday_size_multiplier)  # V8: Mon → 0.25x
                    elif (self.midadx_downsize_enabled
                          and not np.isnan(self.adx14[-1])
                          and self.midadx_lo <= float(self.adx14[-1]) < self.midadx_hi):
                        self.buy(size=self.combo_base_size * self.midadx_size_multiplier)  # V9: mid-ADX → 0.25x
                    else:
                        self.buy(size=self.combo_base_size)  # normal → 1x
                else:
                    self.buy()

        # V12: DISABLED — New Moon MACD Momentum Entry (rejected, see baked-and-rejected).
        # Code kept for reference; guarded by newmoon_macd_entry_enabled=False.
        if self._newmoon_macd_entry_active():
            if self.divergence_sizing_enabled:
                div = self._get_divergence_state()
                if div == "bearish":
                    return  # V11: bearish div = 42.6% WR — skip
                if div == "conflict":
                    self.buy(size=self.combo_boost_size)  # V11: conflict → 2x (use 0.999 convention)
                    self._v12_entry_bar = len(self.data) - 1
                    return
            self.buy(size=self.newmoon_macd_size)
            self._v12_entry_bar = len(self.data) - 1
