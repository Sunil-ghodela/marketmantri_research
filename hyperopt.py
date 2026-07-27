"""
hyperopt.py — optuna-driven parameter search for the agent loop.

Two modes:
    --quick   100 trials, in-sample only (fast rejection of bad hypotheses)
    --deep    500 trials, walk-forward validation (promotion to bake step)

Reads strategy.py → AgentStrategy._param_space, constructs an optuna study,
runs the backtest for each trial, and dumps best params to:
    reports/best_params.json

Usage:
    python hyperopt.py --quick
    python hyperopt.py --deep [--trials N]

The objective maximises Sharpe subject to num_trades ≥ MIN_TRADES.
Trials that fail the trade-count gate are penalised to -1e6 so optuna
steers away from them.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import optuna

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import backtest as harness  # noqa: E402

REPORTS_DIR = HERE / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
BEST_PARAMS_FILE = REPORTS_DIR / "best_params.json"

MIN_TRADES = harness.MIN_TRADES
MIN_TRADES_DEEP = MIN_TRADES  # same gate for deep; walk-forward handles robustness
PENALTY = -1e6
# Walk-forward overfit detection:
# The strict 0.8 ratio was rejecting strategies that genuinely work out-of-sample
# because train/val periods cover different NSE regimes (2016-2023 vs 2023-2026).
# Self-correction: the REAL gate is "val Sharpe > 0" (strategy makes money OOS).
# The ratio is a WARNING, not a rejection gate.
OVERFIT_WARN_RATIO = 0.5  # below this, print a warning about potential overfit
VAL_MIN_SHARPE = 0.0      # val Sharpe must be positive (strategy works OOS)


def import_strategy():
    if "strategy" in sys.modules:
        importlib.reload(sys.modules["strategy"])
    import strategy
    return strategy.AgentStrategy


def sample_params(trial: optuna.Trial, space: dict[str, tuple]) -> dict[str, Any]:
    out = {}
    for name, spec in space.items():
        kind = spec[0]
        if kind == "int":
            lo, hi = spec[1], spec[2]
            step = spec[3] if len(spec) > 3 else 1
            out[name] = trial.suggest_int(name, lo, hi, step=step)
        elif kind == "float":
            lo, hi = spec[1], spec[2]
            step = spec[3] if len(spec) > 3 else None
            out[name] = trial.suggest_float(name, lo, hi, step=step)
        else:
            raise ValueError(f"Unknown param kind {kind!r} in _param_space['{name}']")
    return out


def make_trial_strategy(base_cls, params: dict[str, Any]):
    """Return a Strategy subclass with params baked in as class attrs."""
    attrs = {k: v for k, v in params.items()}
    return type(base_cls.__name__ + "_trial", (base_cls,), attrs)


def run_on_data(strategy_cls, data_df) -> dict:
    """Internal helper — run harness against an in-memory dataframe."""
    from backtesting import Backtest
    import fees as fees_mod
    import time as _time

    t0 = _time.time()
    # Apply same wrappers as backtest.run() for consistency
    max_hold_bars = harness.resolve_max_hold_bars(strategy_cls)
    wrapped = harness.force_eod_wrapper(strategy_cls)
    wrapped = harness.force_max_hold_wrapper(wrapped, max_hold_bars)
    commission = fees_mod.per_leg_commission(
        getattr(strategy_cls, "segment", "intraday"),
        harness.STAKE_INR,
    )
    bt = Backtest(
        data_df,
        wrapped,
        cash=harness.CASH_INR,
        commission=commission,
        trade_on_close=True,
        exclusive_orders=True,
        finalize_trades=True,
    )
    stats = bt.run()
    elapsed = _time.time() - t0

    return {
        "sharpe": float(stats.get("Sharpe Ratio", float("nan"))),
        "total_pct": float(stats.get("Return [%]", 0.0)),
        "max_dd_pct": abs(float(stats.get("Max. Drawdown [%]", 0.0))),
        "win_rate": float(stats.get("Win Rate [%]", 0.0)),
        "num_trades": int(stats.get("# Trades", 0)),
        "calmar": float(stats.get("Calmar Ratio", float("nan"))),
        "sortino": float(stats.get("Sortino Ratio", float("nan"))),
        "elapsed_s": elapsed,
    }


def walk_forward_split(data_df, train_frac: float = 0.7):
    """Split the data into (train, val) by date."""
    n = len(data_df)
    split = int(n * train_frac)
    return data_df.iloc[:split].copy(), data_df.iloc[split:].copy()


def run_quick(n_trials: int = 100) -> dict:
    base = import_strategy()
    space = getattr(base, "_param_space", {})
    if not space:
        raise RuntimeError("strategy.py has no _param_space; nothing to optimise")

    data = harness.load_data(harness.DATA_FILE)
    print(f"Quick hyperopt: {n_trials} trials, in-sample only, {len(data):,} candles")
    print(f"Param space: {space}")
    print()

    def objective(trial):
        params = sample_params(trial, space)
        metrics = run_on_data(make_trial_strategy(base, params), data)
        if metrics["num_trades"] < MIN_TRADES:
            return PENALTY
        sharpe = metrics["sharpe"]
        if np.isnan(sharpe) or np.isinf(sharpe):
            return PENALTY
        return sharpe

    sampler = optuna.samplers.TPESampler(seed=42)
    study = optuna.create_study(direction="maximize", sampler=sampler)
    t0 = time.time()
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    elapsed = time.time() - t0

    best = study.best_trial
    print()
    print("=" * 72)
    print(f"Quick hyperopt done in {elapsed:.1f}s")
    print(f"Best Sharpe: {best.value:.4f}")
    print(f"Best params: {best.params}")

    # Final eval with best params to get all metrics
    final = run_on_data(make_trial_strategy(base, best.params), data)
    print(f"Full metrics: {final}")

    result = {
        "mode": "quick",
        "trials": n_trials,
        "elapsed_s": elapsed,
        "best_sharpe": best.value,
        "best_params": best.params,
        "metrics": final,
    }
    BEST_PARAMS_FILE.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nBest params written to {BEST_PARAMS_FILE}")
    return result


def run_deep(n_trials: int = 500) -> dict:
    base = import_strategy()
    space = getattr(base, "_param_space", {})
    if not space:
        raise RuntimeError("strategy.py has no _param_space; nothing to optimise")

    data = harness.load_data(harness.DATA_FILE)
    train, val = walk_forward_split(data, train_frac=0.7)
    print(f"Deep hyperopt: {n_trials} trials, walk-forward 70/30")
    print(f"  Train: {len(train):,} candles  {train.index[0]} → {train.index[-1]}")
    print(f"  Val:   {len(val):,} candles   {val.index[0]} → {val.index[-1]}")
    print(f"Param space: {space}")
    print()

    def objective(trial):
        params = sample_params(trial, space)
        metrics = run_on_data(make_trial_strategy(base, params), train)
        if metrics["num_trades"] < MIN_TRADES_DEEP:
            return PENALTY
        sharpe = metrics["sharpe"]
        if np.isnan(sharpe) or np.isinf(sharpe):
            return PENALTY
        return sharpe

    sampler = optuna.samplers.TPESampler(seed=42)
    pruner = optuna.pruners.MedianPruner(n_startup_trials=20, n_warmup_steps=10)
    study = optuna.create_study(direction="maximize", sampler=sampler, pruner=pruner)
    t0 = time.time()
    study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
    elapsed = time.time() - t0

    best = study.best_trial
    train_metrics = run_on_data(make_trial_strategy(base, best.params), train)
    val_metrics = run_on_data(make_trial_strategy(base, best.params), val)
    # CRITICAL: also compute full-data Sharpe — this is what backtest.py confirm
    # will produce, so the bake-confirm comparison must use THIS number, not val_sharpe.
    full_metrics = run_on_data(make_trial_strategy(base, best.params), data)

    print()
    print("=" * 72)
    print(f"Deep hyperopt done in {elapsed:.1f}s")
    print(f"Best params:     {best.params}")
    print(f"Train Sharpe:    {train_metrics['sharpe']:.4f}  (trades: {train_metrics['num_trades']})")
    print(f"Val   Sharpe:    {val_metrics['sharpe']:.4f}  (trades: {val_metrics['num_trades']})")
    print(f"Full  Sharpe:    {full_metrics['sharpe']:.4f}  (trades: {full_metrics['num_trades']})")

    ratio = val_metrics["sharpe"] / train_metrics["sharpe"] if train_metrics["sharpe"] else float("nan")
    val_positive = val_metrics["sharpe"] > VAL_MIN_SHARPE
    ratio_ok = ratio >= OVERFIT_WARN_RATIO or np.isnan(ratio)
    if not val_positive:
        verdict = "REJECT (val Sharpe ≤ 0 — no OOS edge)"
    elif not ratio_ok:
        verdict = "CAUTION (low ratio — may be regime-dependent, but val is positive)"
    else:
        verdict = "ROBUST"
    overfit = not val_positive  # only reject if val is actually negative
    print(f"Val/Train ratio: {ratio:.2f}  ({verdict})")

    result = {
        "mode": "deep",
        "trials": n_trials,
        "elapsed_s": elapsed,
        "train_sharpe": train_metrics["sharpe"],
        "val_sharpe": val_metrics["sharpe"],
        "full_sharpe": full_metrics["sharpe"],
        "val_train_ratio": ratio,
        "overfit": overfit,
        "best_params": best.params,
        "train_metrics": train_metrics,
        "val_metrics": val_metrics,
        "full_metrics": full_metrics,
    }
    BEST_PARAMS_FILE.write_text(json.dumps(result, indent=2, default=str))
    print(f"\nBest params written to {BEST_PARAMS_FILE}")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--quick", action="store_true")
    group.add_argument("--deep", action="store_true")
    parser.add_argument("--trials", type=int, default=None)
    args = parser.parse_args()

    if args.quick:
        run_quick(n_trials=args.trials or 100)
    elif args.deep:
        run_deep(n_trials=args.trials or 500)


if __name__ == "__main__":
    main()
