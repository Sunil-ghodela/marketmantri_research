"""
backtest_macd_momentum.py — Backtest harness for MacdMomentumStrategy.

Precomputes V2 divergence state and adds it as a 'DivState' data column
(0=none, 1=bullish, 2=bearish, 3=conflict). Runs full 10yr or subset.

Usage:
    python backtest_macd_momentum.py [--2yr] [--debug] [--dir long|both]
"""

from __future__ import annotations

import sys
import time
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import session
import fees
from strategy_macd_momentum import MacdMomentumStrategy
from divergence_detector_v2 import detect_divergences_v2

DATA_FILE = HERE / "data" / "NIFTYBEES_15m.feather"
CASH_INR = 500_000
STAKE_INR = fees.MIN_STAKE_INR

# Look-ahead fix: a divergence pivot needs pivot_right(3) + confirmation_bars(2) = 5 bars to its
# RIGHT before it is actually detectable. Activate the divergence state only from p2 + CONFIRM_LAG,
# not from the pivot bar p2 (which would let the strategy "see" it ~5 bars early). Set to 0 to
# reproduce the old (look-ahead-biased) behaviour for comparison.
CONFIRM_LAG = 5

# Exit Lab (2026-06-19): how many bars a divergence stays "active" for the exit, after CONFIRM_LAG.
# Tuned on the 59-stock median + pre-2024/2024+ OOS split — recency 6 beats the old 15 on BOTH halves
# (full median Sharpe 1.44→1.55, holdout 1.48→1.76, DD flat). Shorter window = the bearish-div exit
# fires on a FRESHER pivot and stops cutting winners prematurely. See momentum_v1_exit_lab_FINDINGS.md.
DIV_RECENCY = 6


def compute_div_state(m15_prep: pd.DataFrame, recency: int = DIV_RECENCY) -> np.ndarray:
    """Run V2 ONCE and return per-bar divergence state array.
    0=none, 1=bullish, 2=bearish, 3=conflict
    """
    n = len(m15_prep)
    state = np.zeros(n, dtype=int)

    print("  Running V2 divergence detection...", flush=True)
    t1 = time.time()
    events = detect_divergences_v2(
        m15_prep.reset_index().rename(columns={"index": "date"}),
        oscillator_col="macd_hist",
        pivot_left=3, pivot_right=3,
        min_prominence_pct=0.05, min_price_move_pct=0.12,
        min_pivot_distance=5, zscore_threshold=1.5,
        atr_resolution_mult=0.5, min_oscillator_move_pct=0.05,
        confirmation_bars=2, confirmation_ratio=0.6,
        include_hidden=True, use_volume_confirmation=False,
    )
    elapsed_v2 = time.time() - t1
    print(f"  V2: {len(events)} events in {elapsed_v2:.1f}s", flush=True)

    if not events.empty:
        reg_bull = np.zeros(n, dtype=bool)
        reg_bear = np.zeros(n, dtype=bool)
        h_bull = np.zeros(n, dtype=bool)
        h_bear = np.zeros(n, dtype=bool)

        for _, ev in events.iterrows():
            p2 = int(ev["second_pos"])
            kind = str(ev["kind"])
            pattern = str(ev["pattern"])
            # Look-ahead fix: only act once the pivot is confirmable (p2 + CONFIRM_LAG),
            # and only while still within the relevance window (p2 + recency).
            start = min(n, p2 + CONFIRM_LAG)
            end = min(n, p2 + recency + 1)
            if start >= end:
                continue
            if kind == "bullish" and pattern == "regular":
                reg_bull[start:end] = True
            elif kind == "bearish" and pattern == "regular":
                reg_bear[start:end] = True
            elif kind == "bullish" and pattern == "hidden":
                h_bull[start:end] = True
            elif kind == "bearish" and pattern == "hidden":
                h_bear[start:end] = True

        for i in range(n):
            if reg_bull[i] and reg_bear[i]:
                state[i] = 3
            elif reg_bull[i]:
                state[i] = 1
            elif reg_bear[i]:
                state[i] = 2
            elif h_bull[i] and h_bear[i]:
                state[i] = 3
            elif h_bull[i]:
                state[i] = 1
            elif h_bear[i]:
                state[i] = 2

    bear_cnt = (state == 2).sum()
    bull_cnt = (state == 1).sum()
    con_cnt = (state == 3).sum()
    print(f"  Div states: none={(state==0).sum()} bullish={bull_cnt} bearish={bear_cnt} conflict={con_cnt}", flush=True)
    return state


def load_data(use_2yr: bool = False, debug: bool = False):
    """Load 15m data and add DivState column."""
    print("Loading data...", flush=True)
    df = pd.read_feather(DATA_FILE)
    if df["date"].dt.tz is None:
        df["date"] = df["date"].dt.tz_localize("UTC")
    df = session.filter_trading_hours(df)
    df = session.add_session_columns(df)

    if use_2yr:
        cutoff = pd.Timestamp("2024-06-01", tz="UTC")
        df = df[df["date"] >= cutoff].reset_index(drop=True)
        print(f"  2-year subset: {len(df)} bars", flush=True)
    else:
        print(f"  Full data: {len(df)} bars", flush=True)

    print(f"  Range: {df['date'].iloc[0]} → {df['date'].iloc[-1]}", flush=True)

    # Compute MACD hist on 15m (needed for V2)
    idx_raw = pd.DatetimeIndex(df["date"])
    c = pd.Series(df["close"].values.astype(float), index=idx_raw)
    e12 = c.ewm(span=12, adjust=False).mean()
    e26 = c.ewm(span=26, adjust=False).mean()
    macd_hist = (e12 - e26 - (e12 - e26).ewm(span=9, adjust=False).mean()).values

    # Compute divergence state
    m15_prep = pd.DataFrame({
        "close": df["close"].values.astype(float),
        "high": df["high"].values.astype(float),
        "low": df["low"].values.astype(float),
        "volume": df["volume"].values.astype(float),
        "macd_hist": macd_hist,
    }, index=idx_raw)

    div_state = compute_div_state(m15_prep, recency=DIV_RECENCY)

    # Build output DataFrame with DivState column
    out = pd.DataFrame({
        "Open":               df["open"].values,
        "High":               df["high"].values,
        "Low":                df["low"].values,
        "Close":              df["close"].values,
        "Volume":             df["volume"].values,
        "SessionFirst":       df["session_first"].values.astype(int),
        "SessionLast":        df["session_last"].values.astype(int),
        "MinutesIntoSession": df["minutes_into_session"].values.astype(int),
        "DivState":           div_state.astype(int),
    }, index=pd.DatetimeIndex(df["date"].values, name="Date"))

    if debug:
        print(f"  DivState column: min={div_state.min()} max={div_state.max()} "
              f"nonzero={int((div_state>0).sum())}", flush=True)

    return out


def _run_backtest(data, strategy_class, direction: str, label: str):
    """Run net + gross backtest for given direction and return stats dict."""
    # Set direction on strategy class
    strategy_class.direction = direction

    # Reset exit reasons
    strategy_class.exit_reasons = []

    commission = fees.per_leg_commission(strategy_class.segment, STAKE_INR)

    bt = Backtest(
        data,
        strategy_class,
        cash=CASH_INR,
        commission=commission,
        trade_on_close=True,
        exclusive_orders=True,
        finalize_trades=True,
    )

    print(f"\n── {label}: Running net backtest...", flush=True)
    stats = bt.run()
    exit_reasons = list(getattr(strategy_class, 'exit_reasons', []))

    # Gross
    strategy_class.exit_reasons = []
    bt_gross = Backtest(
        data,
        strategy_class,
        cash=CASH_INR,
        commission=0,
        trade_on_close=True,
        exclusive_orders=True,
        finalize_trades=True,
    )
    print(f"  {label}: Running gross backtest...", flush=True)
    stats_gross = bt_gross.run()

    result = {
        'label': label,
        'direction': direction,
        'trades': int(stats.get('# Trades', 0)),
        'sharpe_net': float(stats.get('Sharpe Ratio', 0)),
        'sharpe_gross': float(stats_gross.get('Sharpe Ratio', 0)),
        'return_pct': float(stats.get('Return [%]', 0)),
        'max_dd': abs(float(stats.get('Max. Drawdown [%]', 0))),
        'win_rate': float(stats.get('Win Rate [%]', 0)),
        'profit_factor': float(stats.get('Profit Factor', 0)),
        'calmar': float(stats.get('Calmar Ratio', 0)),
        'sortino': float(stats.get('Sortino Ratio', 0)),
        'exit_reasons': exit_reasons,
        '_stats': stats,
        '_stats_gross': stats_gross,
    }

    return result


def print_result(result: dict, period: str):
    """Pretty-print a backtest result."""
    d = result['direction']
    print(f"\n{'='*65}")
    print(f"  MACD MOMENTUM — {period} | direction={d} | {result['label']}")
    print(f"{'='*65}")
    print(f"  Sharpe (net):    {result['sharpe_net']:.4f}")
    print(f"  Sharpe (gross):  {result['sharpe_gross']:.4f}")
    print(f"  Fee drag:        {result['sharpe_gross'] - result['sharpe_net']:.4f}")
    print(f"  Total Return:    {result['return_pct']:.2f}%")
    print(f"  Max DD:          {result['max_dd']:.2f}%")
    print(f"  Win Rate:        {result['win_rate']:.2f}%")
    print(f"  Trades:          {result['trades']}")
    print(f"  Profit Factor:   {result['profit_factor']:.4f}")
    print(f"  Calmar:          {result['calmar']:.4f}")
    print(f"  Sortino:         {result['sortino']:.4f}")
    if result['exit_reasons']:
        from collections import Counter
        reasons = Counter(result['exit_reasons'])
        print(f"  Exit reasons:    {dict(reasons)}")
    print(f"{'='*65}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--twoyr", action="store_true", help="Run on 2-year subset")
    parser.add_argument("--debug", action="store_true", help="Verbose debug output")
    parser.add_argument("--dir", type=str, default=None,
                        help="Direction: 'long' (default) or 'both'. Omit to run both and compare.")
    args = parser.parse_args()

    t0 = time.time()
    data = load_data(use_2yr=args.twoyr, debug=args.debug)
    period = "2YR" if args.twoyr else "10YR"

    if args.dir:
        # Single direction run
        result = _run_backtest(data, MacdMomentumStrategy, args.dir,
                               f"Direction={args.dir}")
        print_result(result, period)
        # Save trades
        try:
            trades = result['_stats']['_trades'].copy()
            if len(result['exit_reasons']) == len(trades):
                trades['Tag'] = result['exit_reasons']
            trades_csv = HERE / f"macd_momentum_trades_{args.dir}.csv"
            trades.to_csv(trades_csv, index=False)
            # Compatibility: save long-only to default filename for dashboard
            if args.dir == 'long':
                default_csv = HERE / "macd_momentum_trades.csv"
                trades.to_csv(default_csv, index=False)
            print(f"  Trades saved: {trades_csv}", flush=True)
        except Exception as e:
            print(f"  Trades save skipped: {e}", flush=True)
        return

    # ── COMPARE long vs both ──
    print(f"\n{'='*75}")
    print(f"  MACD MOMENTUM — {period} | LONG vs BOTH COMPARISON")
    print(f"{'='*75}")

    results = []
    for direction in ['long', 'both']:
        r = _run_backtest(data, MacdMomentumStrategy, direction,
                          f"Direction={direction}")
        results.append(r)
        print_result(r, period)

    # Summary table
    print(f"\n{'='*85}")
    print(f"  COMPARISON: LONG-ONLY vs BIDIRECTIONAL")
    print(f"{'='*85}")
    print(f"{'Mode':<10} {'Trades':>7} {'WR%':>7} {'Sharpe(N)':>10} {'Sharpe(G)':>10} "
          f"{'Ret%':>8} {'DD%':>8} {'PF':>7} {'Calmar':>8}")
    print(f"{'-'*85}")

    for r in results:
        print(f"  {r['direction']:<8} {r['trades']:>7} {r['win_rate']:>6.1f}% "
              f"{r['sharpe_net']:>10.4f} {r['sharpe_gross']:>10.4f} "
              f"{r['return_pct']:>7.2f}% {r['max_dd']:>7.2f}% "
              f"{r['profit_factor']:>7.2f} {r['calmar']:>8.4f}")

    elapsed = time.time() - t0
    print(f"\n  Total elapsed: {elapsed:.1f}s")

    # Save trades
    for r in results:
        try:
            trades = r['_stats']['_trades'].copy()
            if len(r['exit_reasons']) == len(trades):
                trades['Tag'] = r['exit_reasons']
            trades_csv = HERE / f"macd_momentum_trades_{r['direction']}.csv"
            trades.to_csv(trades_csv, index=False)
            print(f"  Trades saved: {trades_csv}", flush=True)
            # Compatibility: save long-only to default filename for dashboard
            if r['direction'] == 'long':
                default_csv = HERE / "macd_momentum_trades.csv"
                trades.to_csv(default_csv, index=False)
                print(f"  Compat copy: {default_csv}", flush=True)
        except Exception as e:
            print(f"  Trades save skipped: {e}", flush=True)

    print(f"  ✅ {period} comparison complete")


if __name__ == "__main__":
    from collections import Counter  # import here for exit_reasons display
    main()
