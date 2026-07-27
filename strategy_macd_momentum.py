"""
strategy_macd_momentum.py — MACD + Divergence Momentum Strategy (Long + Short).

STANDALONE strategy, independent of strategy.py V10 pullback system.

Direction modes:
  - direction='long':  Entry on 1H MACD cross UP + no bearish divergence (original)
  - direction='both':  Entry on cross UP (long) OR cross DOWN (short) + divergence filter

Entry (long):   1H MACD(12,26,9) line crosses above signal line
Filter (long):  Skip if 15m bearish divergence active (V2 detector, recency ~4h)
Exit (long):    1H MACD cross below, bearish divergence, max hold, stop loss

Entry (short):  1H MACD line crosses below signal line
Filter (short): Skip if 15m bullish divergence active
Exit (short):   1H MACD cross above, bullish divergence, max hold, stop loss (upside)

Sharpe (long):  2.71 gross | WR 56.9% | 492 trades (10yr NIFTYBEES)

NOTE: Divergence state is precomputed in the backtest harness and added as
a custom data column 'DivState' (0=none, 1=bullish, 2=bearish, 3=conflict).
This avoids running the expensive V2 detector inside backtesting.py's init().
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from backtesting import Strategy


def chandelier_long_stop(hwm: float, atr: float, mult: float) -> float:
    """Chandelier (ATR-trailing) stop for a long: high-water-mark minus mult*ATR.

    mult=0 disables the trail (stop sits at the HWM, i.e. never below price).
    """
    return hwm - mult * atr


class MacdMomentumStrategy(Strategy):
    """MACD + Divergence Momentum — breakout/momentum system (long + short).

    Direction modes:
      'long' — long-only (classic). Entry on MACD cross UP + no bearish div.
      'both' — bidirectional. Long on cross UP, short on cross DOWN.

    Requires data column: DivState (0=none, 1=bullish, 2=bearish, 3=conflict)
    """

    segment = "delivery"
    close_eod = False
    max_hold_days = 3
    required_margin = 1.0

    # Direction mode: 'long' or 'both'
    # Direction mode: 'long', 'short', or 'both'
    direction = 'long'

    # MACD parameters
    macd_fast = 12
    macd_slow = 26
    macd_signal_window = 5     # Entry Loop (2026-06-20): 9→5 lifts 59-stock median 1.55→1.97, OOS-robust
                               # (train+holdout both up) AND survives 3x fees. Faster signal = enter trends
                               # earlier. sig3/4 score higher but turnover-trap; 5 = robust. See findings doc.

    # Max hold in bars (75 = ~3 trading days × 25 bars/day on 15m)
    max_hold_bars = 75

    # Divergence filter
    divergence_filter_enabled = True
    div_recency = 6            # bars a divergence stays active (Exit Lab 2026-06-19: 6 beats 15, OOS-robust).
                               # NOTE: vestigial here — actual recency is baked into DivState by
                               # backtest_macd_momentum.DIV_RECENCY; kept in sync for clarity.
    macd_cross_exit_enabled = True   # exit #3: 1H MACD cross-back. Laggy/whipsaw-prone — toggle for A/B test.
    macd_cross_exit_loss_only = False  # if True, cross-exit fires only when trade is in loss (cut losers, let winners run)
    entry_15m_confirm = False        # entry only if 15m MACD > signal (chop filter — skip flat/chop entries)
    exit_15m_cross = False           # exit #3 uses faster 15m MACD cross instead of laggy 1H
    entry_adx_min = 0.0              # entry only if 15m ADX >= this (trend filter; 0 = off). Skip chop.
    entry_trend_gate = False         # entry only if data col TrendUp==1 (higher-TF daily/weekly/monthly trend; falling-knife filter — A/B only, default off, no live effect)
    profit_target_pct = 0.0          # exit at +this% (capture MFE before reversal; 0 = off)
    atr_trail_mult = 0.0             # chandelier ATR-trailing stop: exit if Close <= HWM - mult*ATR (0 = off, long-only)

    # Stop loss
    stop_loss_pct = 2.0        # 2% below entry for long, above entry for short

    def init(self):
        """Precompute 1H MACD indicators from 15m data."""
        n = len(self.data)
        closes = np.asarray(self.data.Close, dtype=float)
        idx = pd.DatetimeIndex(self.data.index)
        if idx.tz is None:
            idx = idx.tz_localize("UTC")

        df = pd.DataFrame({"close": closes}, index=idx)

        # Resample to 1H, compute MACD
        hourly = df.resample("1h").agg({"close": "last"}).dropna(subset=["close"])
        h_close = hourly["close"]

        h_macd = (h_close.ewm(span=self.macd_fast, adjust=False).mean()
                  - h_close.ewm(span=self.macd_slow, adjust=False).mean())
        h_signal = h_macd.ewm(span=self.macd_signal_window, adjust=False).mean()

        h_macd_series = pd.Series(h_macd.values, index=hourly.index)
        h_signal_series = pd.Series(h_signal.values, index=hourly.index)

        # Cross-up: previous bar MACD <= signal, current bar MACD > signal
        h_cross_up = ((h_macd_series.shift(1) <= h_signal_series.shift(1))
                      & (h_macd_series > h_signal_series))
        # Cross-down: previous bar MACD > signal, current bar MACD <= signal
        h_cross_down = ((h_macd_series.shift(1) > h_signal_series.shift(1))
                        & (h_macd_series <= h_signal_series))

        # Forward-fill to 15m bars (vectorized; values identical to the old per-bar loop —
        # any pre-first-bar NaN falls inside the n<30 warmup guard in next(), so never trades)
        def _ffill_bool(h_series: pd.Series) -> np.ndarray:
            aligned = h_series.reindex(idx, method="ffill")
            return aligned.fillna(False).to_numpy(dtype=bool)

        self._h1_cross_up = _ffill_bool(h_cross_up)
        self._h1_cross_down = _ffill_bool(h_cross_down)

        # 15m MACD (native timeframe) — faster than 1H; used for chop-filter entry + faster exit
        m_macd = (df["close"].ewm(span=12, adjust=False).mean()
                  - df["close"].ewm(span=26, adjust=False).mean())
        m_sig = m_macd.ewm(span=9, adjust=False).mean()
        self._m15_above = (m_macd > m_sig).to_numpy(dtype=bool)
        m_cu = (m_macd.shift(1) <= m_sig.shift(1)) & (m_macd > m_sig)
        m_cd = (m_macd.shift(1) > m_sig.shift(1)) & (m_macd <= m_sig)
        self._m15_cross_up = m_cu.fillna(False).to_numpy(dtype=bool)
        self._m15_cross_down = m_cd.fillna(False).to_numpy(dtype=bool)

        # 15m ADX(14) — trend-strength / chop detector (Wilder)
        highs = pd.Series(np.asarray(self.data.High, dtype=float), index=idx)
        lows = pd.Series(np.asarray(self.data.Low, dtype=float), index=idx)
        cl = df["close"]
        up_move = highs.diff(); dn_move = -lows.diff()
        plus_dm = ((up_move > dn_move) & (up_move > 0)) * up_move
        minus_dm = ((dn_move > up_move) & (dn_move > 0)) * dn_move
        tr = pd.concat([highs - lows, (highs - cl.shift()).abs(), (lows - cl.shift()).abs()], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/14, adjust=False).mean()
        pdi = 100 * plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr
        mdi = 100 * minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr
        dx = 100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, 1e-9)
        adx = dx.ewm(alpha=1/14, adjust=False).mean()
        self._adx = np.nan_to_num(adx.to_numpy(dtype=float), nan=0.0)
        self._atr = np.nan_to_num(atr.to_numpy(dtype=float), nan=0.0)   # for chandelier ATR-trail exit

        # Track entry for max-hold and stop-loss
        self._entry_bar = -1
        self._entry_price = -1.0
        self._pos_dir = None  # 'long' or 'short'
        self._hwm = -1.0      # high-water-mark since entry (for chandelier ATR-trail, long-only)

        # Track exit reasons via class-level list (backtesting.py doesn't serialize position.tag)
        self.__class__.exit_reasons = []

    def _close_with_reason(self, reason: str):
        self.position.close()
        self.__class__.exit_reasons.append(reason)
        self._pos_dir = None
        self._hwm = -1.0

    def next(self):
        n = len(self.data) - 1
        if n < 30:
            return

        price = float(self.data.Close[-1])

        # Read divergence state from custom data column
        # DivState: 0=none, 1=bullish, 2=bearish, 3=conflict
        div_state = int(self.data.DivState[-1]) if hasattr(self.data, 'DivState') else 0

        # ── IN POSITION: check exits ──
        if self.position:
            is_short = self._pos_dir == 'short'

            if is_short:
                # --- SHORT EXITS ---
                # 1. Stop loss (upside)
                if self.stop_loss_pct > 0 and self._entry_price > 0:
                    stop_price = self._entry_price * (1 + self.stop_loss_pct / 100)
                    if price >= stop_price:
                        self._close_with_reason("Stop Loss (Short)")
                        return
                # 2. Max hold
                if n - self._entry_bar >= self.max_hold_bars:
                    self._close_with_reason("Max Hold (Short)")
                    return
                # 3. MACD cross UP (bullish reversal)
                if self.macd_cross_exit_enabled and n < len(self._h1_cross_up) and self._h1_cross_up[n]:
                    if (not self.macd_cross_exit_loss_only) or (self._entry_price > 0 and price > self._entry_price):
                        self._close_with_reason("MACD Cross (Short)")
                        return
                # 4. Bullish divergence appears (potential bottom)
                if self.divergence_filter_enabled and div_state == 1:
                    self._close_with_reason("Bullish Div (Short)")
                    return
                return
            else:
                # --- LONG EXITS (original logic) ---
                # Update high-water-mark for the chandelier trail (uses intrabar High)
                high = float(self.data.High[-1])
                if high > self._hwm:
                    self._hwm = high
                # 0. Profit target (capture favorable move before reversal)
                if self.profit_target_pct > 0 and self._entry_price > 0:
                    if price >= self._entry_price * (1 + self.profit_target_pct / 100):
                        self._close_with_reason("Profit Target")
                        return
                # 1. Stop loss (downside)
                if self.stop_loss_pct > 0 and self._entry_price > 0:
                    stop_price = self._entry_price * (1 - self.stop_loss_pct / 100)
                    if price <= stop_price:
                        self._close_with_reason("Stop Loss")
                        return
                # 1b. Chandelier ATR-trailing stop (long-only): exit if Close <= HWM - mult*ATR
                if self.atr_trail_mult > 0 and self._hwm > 0 and n < len(self._atr):
                    trail = chandelier_long_stop(self._hwm, self._atr[n], self.atr_trail_mult)
                    if price <= trail:
                        self._close_with_reason("ATR Trail")
                        return
                # 2. Max hold
                if n - self._entry_bar >= self.max_hold_bars:
                    self._close_with_reason("Max Hold")
                    return
                # 3. MACD cross below (1H, or faster 15m if exit_15m_cross)
                _cross_dn = (self._m15_cross_down[n] if self.exit_15m_cross
                             else (n < len(self._h1_cross_down) and self._h1_cross_down[n]))
                if self.macd_cross_exit_enabled and _cross_dn:
                    if (not self.macd_cross_exit_loss_only) or (self._entry_price > 0 and price < self._entry_price):
                        self._close_with_reason("MACD Cross")
                        return
                # 4. Bearish divergence appears
                if self.divergence_filter_enabled and div_state == 2:
                    self._close_with_reason("Bearish Div")
                    return
                return

        # ── NOT IN POSITION: check entry ──

        long_ok = self.direction in ('long', 'both')
        short_ok = self.direction in ('short', 'both')

        # Check LONG entry: 1H MACD cross UP
        if long_ok and n < len(self._h1_cross_up) and self._h1_cross_up[n]:
            # Filter: bearish divergence active → skip
            if not (self.divergence_filter_enabled and div_state == 2):
                # Chop filters: 15m MACD confirm + ADX trend-strength (skip chop entries)
                _confirm_ok = (not self.entry_15m_confirm) or self._m15_above[n]
                _adx_ok = (self.entry_adx_min <= 0) or (self._adx[n] >= self.entry_adx_min)
                _trend_ok = (not self.entry_trend_gate) or (not hasattr(self.data, 'TrendUp')) or (int(self.data.TrendUp[-1]) == 1)
                if _confirm_ok and _adx_ok and _trend_ok:
                    self._entry_bar = n
                    self._entry_price = price
                    self._pos_dir = 'long'
                    self._hwm = float(self.data.High[-1])   # seed HWM for chandelier trail
                    self.buy(size=0.999)
                    return

        # Check SHORT entry: 1H MACD cross DOWN
        if short_ok and n < len(self._h1_cross_down) and self._h1_cross_down[n]:
            # Filter: bullish divergence active → skip (potential reversal up)
            if not (self.divergence_filter_enabled and div_state == 1):
                self._entry_bar = n
                self._entry_price = price
                self._pos_dir = 'short'
                self.sell(size=0.999)
