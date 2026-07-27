"""
backtest.py — THE FIXED HARNESS. DO NOT MODIFY.

Equivalent of autotrader/backtest.py for the Indian market research loop.
Loads strategy.py → AgentStrategy, runs backtesting.py against cached
NIFTYBEES 15-min data, applies the right Indian fee model, optionally
force-closes positions at EOD, and prints a standard metrics block.

Usage:
    python backtest.py

Output ends with:
    ---
    sharpe:          X.XXXX
    total_pct:       X.XX
    max_dd_pct:      X.XX
    win_rate:        X.XX
    num_trades:      XXX
    calmar:          X.XXX
    sortino:         X.XXX
    alpha_vs_nifty:  X.XX
    trades_per_day:  X.X
    elapsed_s:       X.X
"""

from __future__ import annotations

import sys
import time
import importlib
from pathlib import Path

import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import session  # noqa: E402
import fees     # noqa: E402

# ── Fixed paths ────────────────────────────────────────────────────────────
DATA_FILE       = HERE / "data" / "NIFTYBEES_15m.feather"
BENCHMARK_FILE  = HERE / "data" / "NIFTY50_15m.feather"
REPORTS_DIR     = HERE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)

# ── Backtest constants ─────────────────────────────────────────────────────
CASH_INR        = 500_000       # starting cash for the backtest
STAKE_INR       = fees.MIN_STAKE_INR  # nominal per-trade stake, used for fee scaling
MIN_TRADES      = 200           # minimum num_trades for results to be meaningful

# Hold-time policy (enforced on every strategy regardless of segment)
# Intraday strategies close positions at EOD via close_eod=True (existing).
# Swing strategies use close_eod=False + max_hold_days<=MAX_ALLOWED_HOLD_DAYS.
# Anything longer than a trading week is rejected at harness load time.
BARS_PER_TRADING_DAY  = 25      # 15-min candles in a 9:15-15:30 IST session
MAX_ALLOWED_HOLD_DAYS = 5       # 1 trading week — hard policy cap


def load_data(path: Path) -> pd.DataFrame:
    """Load a feather file and return a backtesting.py-compatible dataframe."""
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Run `python fetch_data.py` first."
        )
    df = pd.read_feather(path)
    if df["date"].dt.tz is None:
        df["date"] = df["date"].dt.tz_localize("UTC")
    # Drop Muhurat / mock sessions — anything outside regular 09:15–15:30 IST hours
    df = session.filter_trading_hours(df)
    df = session.add_session_columns(df)

    # Build the OHLCV frame backtesting.py wants (datetime index, capitalised columns).
    # Extra columns (SessionFirst, SessionLast, MinutesIntoSession) become
    # accessible to strategies via self.data.SessionLast etc.
    out = pd.DataFrame({
        "Open":               df["open"].values,
        "High":               df["high"].values,
        "Low":                df["low"].values,
        "Close":              df["close"].values,
        "Volume":             df["volume"].values,
        "SessionFirst":       df["session_first"].values.astype(int),
        "SessionLast":        df["session_last"].values.astype(int),
        "MinutesIntoSession": df["minutes_into_session"].values.astype(int),
    }, index=pd.DatetimeIndex(df["date"].values, name="Date"))
    return out


def force_eod_wrapper(StrategyClass):
    """
    Wrap a Strategy class so that if its `close_eod` attribute is True,
    any open position is force-closed on the last candle of each session.
    """
    close_eod = getattr(StrategyClass, "close_eod", False)
    if not close_eod:
        return StrategyClass

    class EODWrapped(StrategyClass):
        def next(self):
            super().next()
            # SessionLast is a user column on self.data; backtesting.py exposes
            # it as an attribute that grows as the simulation advances.
            try:
                is_last = int(self.data.SessionLast[-1]) == 1
            except Exception:
                is_last = False
            if is_last and self.position:
                self.position.close()

    EODWrapped.__name__ = StrategyClass.__name__ + "_EOD"
    return EODWrapped


def resolve_max_hold_bars(StrategyClass) -> int | None:
    """
    Read `max_hold_days` from a strategy class and convert to bars.
    Returns None if not set. Raises ValueError if the value exceeds
    MAX_ALLOWED_HOLD_DAYS (the policy cap).

    max_hold_days only applies to non-EOD (swing) strategies. For
    close_eod=True strategies the EOD wrapper already closes positions
    the same trading day.
    """
    days = getattr(StrategyClass, "max_hold_days", None)
    if days is None:
        return None
    if not isinstance(days, int) or days <= 0:
        raise ValueError(
            f"{StrategyClass.__name__}.max_hold_days must be a positive int or None; got {days!r}"
        )
    if days > MAX_ALLOWED_HOLD_DAYS:
        raise ValueError(
            f"{StrategyClass.__name__}.max_hold_days={days} exceeds the hard policy cap of "
            f"MAX_ALLOWED_HOLD_DAYS={MAX_ALLOWED_HOLD_DAYS}. We never hold longer than a "
            f"trading week. Reduce max_hold_days or switch to close_eod=True for intraday."
        )
    return days * BARS_PER_TRADING_DAY


def force_max_hold_wrapper(StrategyClass, max_hold_bars: int | None):
    """
    Wrap a Strategy class so that any open trade older than `max_hold_bars`
    is force-closed on the current candle. Bars are 15-minute candles during
    regular NSE session only (Muhurat is filtered out upstream).

    This is the swing-strategy equivalent of the EOD wrapper — it caps
    holding time at MAX_ALLOWED_HOLD_DAYS * BARS_PER_TRADING_DAY bars.
    """
    if max_hold_bars is None or max_hold_bars <= 0:
        return StrategyClass

    class MaxHoldWrapped(StrategyClass):
        def next(self):
            super().next()
            now = len(self.data) - 1
            # Iterate over a copy because Trade.close() mutates self.trades
            for trade in list(self.trades):
                if now - trade.entry_bar >= max_hold_bars:
                    trade.close()

    MaxHoldWrapped.__name__ = StrategyClass.__name__ + "_MaxHold"
    return MaxHoldWrapped


def import_strategy():
    """Fresh import of strategy.py so re-runs within same process see latest code."""
    if "strategy" in sys.modules:
        importlib.reload(sys.modules["strategy"])
    import strategy
    return strategy.AgentStrategy


def benchmark_return(start_ts: pd.Timestamp, end_ts: pd.Timestamp) -> float:
    """Return the NIFTY 50 total return (%) over [start_ts, end_ts]."""
    if not BENCHMARK_FILE.exists():
        return float("nan")
    bench = pd.read_feather(BENCHMARK_FILE)
    if bench["date"].dt.tz is None:
        bench["date"] = bench["date"].dt.tz_localize("UTC")
    mask = (bench["date"] >= start_ts) & (bench["date"] <= end_ts)
    bench = bench.loc[mask]
    if len(bench) < 2:
        return float("nan")
    first_close = bench["close"].iloc[0]
    last_close = bench["close"].iloc[-1]
    return (last_close / first_close - 1.0) * 100.0


def print_metric_block(stats, elapsed: float, alpha: float, trades_per_day: float,
                       gross_sharpe: float = float("nan"), fee_drag: float = float("nan")) -> None:
    sharpe = float(stats.get("Sharpe Ratio", float("nan")))
    total_pct = float(stats.get("Return [%]", float("nan")))
    max_dd = abs(float(stats.get("Max. Drawdown [%]", float("nan"))))
    win_rate = float(stats.get("Win Rate [%]", float("nan")))
    num_trades = int(stats.get("# Trades", 0))
    calmar = float(stats.get("Calmar Ratio", float("nan")))
    sortino = float(stats.get("Sortino Ratio", float("nan")))

    print()
    print("---")
    print(f"sharpe:          {sharpe:.4f}")
    print(f"gross_sharpe:    {gross_sharpe:.4f}")
    print(f"fee_drag:        {fee_drag:.4f}")
    print(f"total_pct:       {total_pct:.2f}")
    print(f"max_dd_pct:      {max_dd:.2f}")
    print(f"win_rate:        {win_rate:.2f}")
    print(f"num_trades:      {num_trades}")
    print(f"calmar:          {calmar:.4f}")
    print(f"sortino:         {sortino:.4f}")
    print(f"alpha_vs_nifty:  {alpha:.2f}")
    print(f"trades_per_day:  {trades_per_day:.2f}")
    print(f"elapsed_s:       {elapsed:.1f}")

    # Standard sanity warnings
    if num_trades < MIN_TRADES:
        print()
        print(
            f"WARNING: num_trades ({num_trades}) < MIN_TRADES ({MIN_TRADES}). "
            f"Results are statistically thin; a thin-trade Sharpe should be "
            f"treated as noise."
        )


def save_tearsheet(stats, label: str = "latest") -> None:
    """Save a QuantStats HTML tearsheet from the equity curve."""
    try:
        import quantstats as qs
    except ImportError as e:
        # Loud — IPython is a hidden quantstats dep; if this fails,
        # user should install it rather than silently losing tearsheets
        print(f"(tearsheet skipped: quantstats import failed — {e})")
        return

    equity = stats.get("_equity_curve")
    if equity is None or len(equity) == 0:
        print("(tearsheet skipped: no equity curve in stats)")
        return

    returns = equity["Equity"].pct_change().dropna()
    if len(returns) == 0:
        print("(tearsheet skipped: empty returns series)")
        return

    # quantstats needs a non-localized series for its internal resampling
    if hasattr(returns.index, "tz") and returns.index.tz is not None:
        returns.index = returns.index.tz_localize(None)

    out = REPORTS_DIR / f"{label}.html"
    try:
        qs.reports.html(
            returns,
            output=str(out),
            title=f"autoresearch_india — {label}",
        )
        print(f"Tearsheet: {out}")
    except Exception as e:
        print(f"(tearsheet generation failed: {e})")


def run(strategy_cls=None) -> dict:
    """
    Run a full backtest.

    If called programmatically (e.g. from hyperopt.py), pass a preconfigured
    strategy class with parameter defaults already set.
    """
    t0 = time.time()

    data = load_data(DATA_FILE)
    if strategy_cls is None:
        strategy_cls = import_strategy()

    # Apply policy wrappers (order doesn't matter — both can fire on same bar)
    max_hold_bars = resolve_max_hold_bars(strategy_cls)
    wrapped = force_eod_wrapper(strategy_cls)
    wrapped = force_max_hold_wrapper(wrapped, max_hold_bars)
    commission = fees.per_leg_commission(getattr(strategy_cls, "segment", "intraday"), STAKE_INR)
    margin = float(getattr(strategy_cls, "required_margin", 1.0))

    bt = Backtest(
        data,
        wrapped,
        cash=CASH_INR,
        commission=commission,
        margin=margin,
        trade_on_close=True,
        exclusive_orders=True,
        finalize_trades=True,
    )
    stats = bt.run()

    # Gross Sharpe (no fees) — same run but with 0 commission.
    # Lets us distinguish "signal has no edge" from "edge exists but fees eat it".
    bt_gross = Backtest(
        data,
        wrapped,
        cash=CASH_INR,
        commission=0,
        margin=margin,
        trade_on_close=True,
        exclusive_orders=True,
        finalize_trades=True,
    )
    stats_gross = bt_gross.run()
    gross_sharpe = float(stats_gross.get("Sharpe Ratio", float("nan")))

    elapsed = time.time() - t0

    # Derived metrics
    start_ts = pd.Timestamp(data.index[0])
    end_ts = pd.Timestamp(data.index[-1])
    if start_ts.tz is None:
        start_ts = start_ts.tz_localize("UTC")
    if end_ts.tz is None:
        end_ts = end_ts.tz_localize("UTC")
    bench_ret = benchmark_return(start_ts, end_ts)
    strat_ret = float(stats.get("Return [%]", 0.0))
    alpha = strat_ret - bench_ret if not np.isnan(bench_ret) else float("nan")

    net_sharpe = float(stats.get("Sharpe Ratio", float("nan")))
    fee_drag = gross_sharpe - net_sharpe  # positive = fees are hurting

    num_trades = int(stats.get("# Trades", 0))
    trading_days = max((end_ts - start_ts).days, 1)
    tpd = num_trades / trading_days if trading_days else 0.0

    metrics = {
        "sharpe":         net_sharpe,
        "gross_sharpe":   gross_sharpe,
        "fee_drag":       fee_drag,
        "total_pct":      strat_ret,
        "max_dd_pct":     abs(float(stats.get("Max. Drawdown [%]", float("nan")))),
        "win_rate":       float(stats.get("Win Rate [%]", float("nan"))),
        "num_trades":     num_trades,
        "calmar":         float(stats.get("Calmar Ratio", float("nan"))),
        "sortino":        float(stats.get("Sortino Ratio", float("nan"))),
        "alpha_vs_nifty": alpha,
        "trades_per_day": tpd,
        "elapsed_s":      elapsed,
        "bench_return":   bench_ret,
    }

    print_metric_block(stats, elapsed, alpha, tpd, gross_sharpe, fee_drag)
    save_tearsheet(stats, "latest")
    return metrics


if __name__ == "__main__":
    metrics = run()
    # Exit nonzero if no trades — signals the agent loop to treat as crash
    if metrics["num_trades"] == 0:
        sys.exit(1)
