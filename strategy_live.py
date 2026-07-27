"""
strategy_live.py — Live paper-trading engine for strategy.py on 4 instruments.

Uses AgentStrategy (EMA+UR+PT+regime+filters) with per-ticker params from
robust_ensemble.BASKET. Detects entry/exit on the latest 15m bar via backtest replay.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
from backtesting import Backtest

import backtest as bt_mod
import fees
from robust_ensemble import BASKET, load_data
from strategy import AgentStrategy

HERE = Path(__file__).resolve().parent
WARMUP_BARS = 600

YAHOO_TICKERS = {
    "NIFTYBEES": "NIFTYBEES.NS",
    "GOLDBEES": "GOLDBEES.NS",
    "JUNIORBEES": "JUNIORBEES.NS",
    "LT": "LT.NS",
}


def _ensure_utc_index(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    idx = pd.DatetimeIndex(out.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    out.index = idx
    return out


EXCLUDED_INSTRUMENTS = {"NIFTYAUTO"}
INSTRUMENTS = [ticker for ticker in BASKET if ticker not in EXCLUDED_INSTRUMENTS]
PRIMARY_TICKER = "NIFTYBEES"


def build_strategy_class(ticker: str):
    raw = BASKET[ticker]
    params = {k: v for k, v in raw.items() if k != "source"}

    class LiveStrat(AgentStrategy):
        pass

    for key, val in params.items():
        setattr(LiveStrat, key, val)
    LiveStrat.__name__ = f"AgentStrategy_{ticker}"
    return LiveStrat


def resample_1m_lists(labels, opens, highs, lows, closes, volumes) -> pd.DataFrame:
    if not closes:
        return pd.DataFrame()
    idx = pd.to_datetime(labels, utc=False)
    if idx.tz is None:
        idx = idx.tz_localize("Asia/Kolkata", ambiguous="infer").tz_convert("UTC")
    df = pd.DataFrame(
        {"Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes},
        index=idx,
    )
    out = (
        df.resample("15min", label="left", closed="left")
        .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
        .dropna(subset=["Close"])
    )
    return _ensure_utc_index(out)


def load_warmup_tail(ticker: str, n_bars: int = WARMUP_BARS) -> pd.DataFrame:
    path = HERE / "data" / f"{ticker}_15m.feather"
    if not path.exists():
        return pd.DataFrame()
    return load_data(ticker).tail(n_bars).copy()


def merge_warmup_and_live(live_15m: pd.DataFrame, warmup: pd.DataFrame) -> pd.DataFrame:
    live_15m = _ensure_utc_index(live_15m)
    warmup = _ensure_utc_index(warmup)
    if warmup.empty:
        return live_15m
    if live_15m.empty:
        return warmup
    cut = live_15m.index.min()
    hist = warmup[warmup.index < cut]
    out = pd.concat([hist, live_15m])
    return out[~out.index.duplicated(keep="last")].sort_index()


def _run_trades(df: pd.DataFrame, StrategyCls) -> pd.DataFrame:
    if len(df) < 80:
        return pd.DataFrame()
    commission = fees.per_leg_commission(
        getattr(StrategyCls, "segment", "delivery"), bt_mod.STAKE_INR
    )
    max_hold = bt_mod.resolve_max_hold_bars(StrategyCls)
    wrapped = bt_mod.force_eod_wrapper(StrategyCls)
    wrapped = bt_mod.force_max_hold_wrapper(wrapped, max_hold)
    bt = Backtest(
        df,
        wrapped,
        cash=bt_mod.CASH_INR,
        commission=commission,
        trade_on_close=True,
        exclusive_orders=True,
        finalize_trades=False,
        margin=getattr(StrategyCls, "required_margin", 1.0),
    )
    stats = bt.run()
    tr = stats.get("_trades")
    if tr is None or len(tr) == 0:
        return pd.DataFrame()
    return tr.copy()


def _bar_state(tr: pd.DataFrame, n: int) -> dict:
    if len(tr) == 0 or n < 2:
        return {"in_pos": False, "entered": False, "exited": False}
    last = tr.iloc[-1]
    i = n - 1
    eb, xb = int(last["EntryBar"]), int(last["ExitBar"])
    size = float(last["Size"])
    in_pos = size > 0 and xb > eb and xb >= i
    return {
        "in_pos": in_pos,
        "entered": size > 0 and eb == i,
        "exited": size > 0 and xb == i and xb > eb,
    }


def _diff_state(prev: dict, curr: dict) -> dict:
    return {
        "in_pos": curr["in_pos"],
        "entered": curr["entered"] or (curr["in_pos"] and not prev["in_pos"]),
        "exited": curr["exited"] or (prev["in_pos"] and not curr["in_pos"]),
    }


def evaluate_ticker(ticker: str, df_15m: pd.DataFrame) -> dict:
    n = len(df_15m)
    params = {k: v for k, v in BASKET[ticker].items() if k != "source"}
    # New Moon window check
    new_moon_active = False
    new_moon_info = None
    try:
        from new_moon_integration import get_active_new_moon
        nm = get_active_new_moon(df_15m.index[-1])
        if nm and nm.get("status") == "active":
            new_moon_active = True
            new_moon_info = nm
    except Exception:
        pass

    if n < 100:
        return {
            "ok": False,
            "ticker": ticker,
            "reason": f"need >=100 15m bars, got {n}",
            "signal": None,
            "ltp": None,
            "params": params,
            "new_moon_active": new_moon_active,
            "new_moon_info": new_moon_info,
        }

    Cls = build_strategy_class(ticker)
    tr_full = _run_trades(df_15m, Cls)
    tr_prev = _run_trades(df_15m.iloc[:-1], Cls) if n > 101 else pd.DataFrame()
    st = _diff_state(_bar_state(tr_prev, n - 1), _bar_state(tr_full, n))

    signal = None
    reason_parts = []
    if st["entered"]:
        signal = "BUY"
        reason_parts.append("strategy.py ENTRY")
    elif st["exited"]:
        signal = "SELL"
        reason_parts.append("strategy.py EXIT")

    ltp = float(df_15m["Close"].iloc[-1])
    pt = params.get("profit_target_pct", 0.05)

    return {
        "ok": True,
        "ticker": ticker,
        "yahoo": YAHOO_TICKERS.get(ticker, ticker),
        "signal": signal,
        "signal_type": signal,
        "signal_reason": " | ".join(reason_parts) if reason_parts else (
            "in position" if st["in_pos"] else "flat"
        ),
        "in_pos": st["in_pos"],
        "entered": st["entered"],
        "exited": st["exited"],
        "new_moon_active": new_moon_active,
        "new_moon_info": new_moon_info,
        "ltp": round(ltp, 2),
        "profit_target_pct": round(pt * 100, 1),
        "num_trades": len(tr_full),
        "n_bars_15m": n,
        "last_bar": str(df_15m.index[-1]),
        "params": params,
    }


def evaluate_from_1m(
    ticker: str,
    labels: list,
    opens: list,
    highs: list,
    lows: list,
    closes: list,
    volumes: list,
) -> dict:
    live_15m = resample_1m_lists(labels, opens, highs, lows, closes, volumes)
    warmup = load_warmup_tail(ticker)
    panel = merge_warmup_and_live(live_15m, warmup)
    out = evaluate_ticker(ticker, panel)
    out["live_15m_bars"] = len(live_15m)
    out["warmup_bars"] = len(warmup)
    return out


@lru_cache(maxsize=1)
def basket_meta() -> dict:
    return {
        "instruments": INSTRUMENTS,
        "primary": PRIMARY_TICKER,
        "yahoo": dict(YAHOO_TICKERS),
        "mode": "strategy_py_4inst",
    }
