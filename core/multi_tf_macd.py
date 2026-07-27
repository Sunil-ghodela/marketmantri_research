"""multi_tf_macd.py — MACD state across 9 timeframes (15m → monthly) for the phase panel.

Pure data in / data out. Intraday TFs from the live 15m series (resample_ohlc);
swing TFs from a daily close series (pandas resample). Returns per-TF dicts:
  {"tf","state"("green"|"red"|"na"),"hist","hist_slope","cross"("bull"|"bear"|"none")}
"""
from __future__ import annotations

import pandas as pd

from core.indicators import resample_ohlc

TF_ORDER = ["Monthly", "Weekly", "Daily", "3h", "2h", "1h", "45m", "30m", "15m"]
_INTRADAY_MIN = {"15m": 15, "30m": 30, "45m": 45, "1h": 60, "2h": 120, "3h": 180}
_MIN_BARS = 35  # need >= slow+signal for a meaningful MACD


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def macd_state(closes: list[float], fast: int = 12, slow: int = 26, sig: int = 9) -> dict:
    if closes is None or len(closes) < _MIN_BARS:
        return {"state": "na", "hist": 0.0, "hist_slope": 0.0, "cross": "none"}
    c = pd.Series([float(x) for x in closes])
    macd = _ema(c, fast) - _ema(c, slow)
    signal = _ema(macd, sig)
    hist = macd - signal
    mv, sv = float(macd.iloc[-1]), float(signal.iloc[-1])
    hv, hp = float(hist.iloc[-1]), float(hist.iloc[-2])
    cross = "none"
    for i in (-1, -2, -3):
        if i - 1 < -len(macd):
            break
        a1, a0 = float(macd.iloc[i]), float(macd.iloc[i - 1])
        b1, b0 = float(signal.iloc[i]), float(signal.iloc[i - 1])
        if a1 > b1 and a0 <= b0:
            cross = "bull"
        elif a1 < b1 and a0 >= b0:
            cross = "bear"
    return {"state": "green" if mv > sv else "red",
            "hist": round(hv, 1), "hist_slope": round(hv - hp, 2), "cross": cross}


def _resample_daily(closes_d: pd.Series, rule: str) -> list[float]:
    return list(closes_d.resample(rule).last().dropna().values)


def compute(intraday_15m: dict, daily: dict) -> list[dict]:
    """intraday_15m: {labels,opens,highs,lows,closes,volumes} (15m bars).
       daily: {index: list[datetime-like], closes: list[float]}.
       Returns 9 per-TF dicts in TF_ORDER."""
    out = {}

    # --- intraday TFs from the 15m series ---
    base = intraday_15m
    for tf, fmin in _INTRADAY_MIN.items():
        if fmin == 15:
            closes = base["closes"]
        else:
            # resample_ohlc returns (labels, opens, highs, lows, closes, volumes)
            res = resample_ohlc(base["labels"], base["opens"], base["highs"],
                                base["lows"], base["closes"], base["volumes"], fmin)
            closes = res[4]
        out[tf] = {**macd_state(closes), "tf": tf}

    # --- swing TFs from the daily series ---
    try:
        idx = pd.DatetimeIndex(pd.to_datetime(daily["index"]))
        dc = pd.Series([float(x) for x in daily["closes"]], index=idx).sort_index()
        out["Daily"] = {**macd_state(list(dc.values)), "tf": "Daily"}
        out["Weekly"] = {**macd_state(_resample_daily(dc, "W")), "tf": "Weekly"}
        out["Monthly"] = {**macd_state(_resample_daily(dc, "ME")), "tf": "Monthly"}
    except Exception:
        for tf in ("Daily", "Weekly", "Monthly"):
            out.setdefault(tf, {"tf": tf, "state": "na", "hist": 0.0, "hist_slope": 0.0, "cross": "none"})

    return [out[tf] for tf in TF_ORDER]
