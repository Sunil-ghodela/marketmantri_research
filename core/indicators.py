"""Pure indicator functions — no app state dependency."""
from __future__ import annotations
import pandas as pd


def calc_rsi(closes: list[float], n: int = 14) -> float:
    if len(closes) < n + 1:
        return 50.0
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(d if d > 0 else 0.0)
        losses.append(-d if d < 0 else 0.0)
    if not gains:
        return 50.0
    ag = sum(gains[:n]) / n
    al = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
    return 100.0 if al == 0 else round(100.0 - 100.0 / (1.0 + ag / al), 1)


def calc_adx(highs: list[float], lows: list[float], closes: list[float], n: int = 14) -> float:
    if len(highs) < n + 1:
        return 20.0
    pdm, mdm, trs = [], [], []
    for i in range(1, len(highs)):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
        trs.append(
            max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
        )
    if len(trs) < n:
        return 20.0
    atr = sum(trs[-n:]) / n
    ap = sum(pdm[-n:]) / n
    am = sum(mdm[-n:]) / n
    if atr == 0 or (ap + am) == 0:
        return 20.0
    return round(
        100.0 * abs(100.0 * ap / atr - 100.0 * am / atr)
        / (100.0 * ap / atr + 100.0 * am / atr), 1
    )


def calc_ema(values: list[float], n: int) -> float | None:
    if len(values) < n:
        return None
    mult = 2.0 / (n + 1)
    ema = values[0]
    for v in values[1:]:
        ema = (v * mult) + (ema * (1 - mult))
    return round(float(ema), 2)


def calc_ema_series(values: list[float], n: int) -> list[float | None]:
    """Per-candle EMA. Pads with None until enough warm-up candles."""
    if not values:
        return []
    out: list[float | None] = [None] * len(values)
    if len(values) < n:
        return out
    mult = 2.0 / (n + 1)
    seed = sum(values[:n]) / n
    out[n - 1] = round(float(seed), 2)
    ema = seed
    for i in range(n, len(values)):
        ema = (values[i] * mult) + (ema * (1 - mult))
        out[i] = round(float(ema), 2)
    return out


def calc_macd_hourly_state(closes: list[float], labels: list[str]) -> dict:
    """Compute 1H MACD from 15m closes and return current state.

    Returns dict with:
      - state: 'green' (MACD > signal) or 'red' (MACD < signal)
      - macd: current MACD value
      - signal: current signal line value
      - hist: MACD histogram value
      - hist_slope: histogram slope
      - bar_time_ist: latest 1H bar timestamp
    """
    if len(closes) < 30 or not labels:
        return {"state": "unknown", "macd": 0, "signal": 0, "hist": 0, "hist_slope": 0, "bar_time_ist": ""}
    
    # Build DataFrame with timestamps
    idx = pd.to_datetime(labels, errors="coerce")
    df = pd.DataFrame({"close": closes, "ts": idx})
    df = df.dropna(subset=["ts"]).sort_values("ts")
    
    if df.empty or len(df) < 10:
        return {"state": "unknown", "macd": 0, "signal": 0, "hist": 0, "hist_slope": 0, "bar_time_ist": ""}
    
    # Resample to 1H
    df = df.set_index("ts")
    if df.index.tz is None:
        try:
            df.index = df.index.tz_localize("Asia/Kolkata", ambiguous="infer")
        except Exception:
            df.index = df.index.tz_localize("UTC").tz_convert("Asia/Kolkata")
    
    hourly = (
        df.resample("1h")
        .agg({"close": "last"})
        .dropna(subset=["close"])
    )
    
    if len(hourly) < 30:
        return {"state": "unknown", "macd": 0, "signal": 0, "hist": 0, "hist_slope": 0, "bar_time_ist": ""}
    
    c = hourly["close"]
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - macd_signal
    hist_slope = hist.diff()
    
    latest = hourly.iloc[-1]
    latest_macd = float(macd_line.iloc[-1])
    latest_signal = float(macd_signal.iloc[-1])
    latest_hist = float(hist.iloc[-1])
    latest_slope = float(hist_slope.iloc[-1]) if not pd.isna(hist_slope.iloc[-1]) else 0.0
    
    return {
        "state": "green" if latest_macd > latest_signal else "red",
        "macd": round(latest_macd, 2),
        "signal": round(latest_signal, 2),
        "hist": round(latest_hist, 2),
        "hist_slope": round(latest_slope, 4),
        "bar_time_ist": str(hourly.index[-1].strftime("%Y-%m-%d %H:%M")),
    }


def calc_macd_momentum_signal(closes: list[float], labels: list[str]) -> dict:
    """Compute 1H MACD momentum signal from 15m closes.

    Returns dict with:
      - state: 'green' (MACD > signal) or 'red' (MACD < signal)
      - cross: 'up' (just crossed above), 'down' (just crossed below), 'none' (no cross)
      - macd: current MACD value
      - signal: current signal line value
      - hist: current histogram
      - hist_slope: histogram slope
      - state_prev: previous bar state
      - cross_bars: bars since last crossover
      - bar_time_ist: latest 1H bar
    """
    if len(closes) < 30 or not labels:
        return {"state": "unknown", "cross": "none", "macd": 0, "signal": 0,
                "hist": 0, "hist_slope": 0, "state_prev": "unknown",
                "cross_bars": 0, "bar_time_ist": ""}

    idx = pd.to_datetime(labels, errors="coerce")
    df = pd.DataFrame({"close": closes, "ts": idx})
    df = df.dropna(subset=["ts"]).sort_values("ts")

    if df.empty or len(df) < 10:
        return {"state": "unknown", "cross": "none", "macd": 0, "signal": 0,
                "hist": 0, "hist_slope": 0, "state_prev": "unknown",
                "cross_bars": 0, "bar_time_ist": ""}

    df = df.set_index("ts")
    if df.index.tz is None:
        try:
            df.index = df.index.tz_localize("Asia/Kolkata", ambiguous="infer")
        except Exception:
            df.index = df.index.tz_localize("UTC").tz_convert("Asia/Kolkata")

    hourly = df.resample("1h").agg({"close": "last"}).dropna(subset=["close"])

    if len(hourly) < 30:
        return {"state": "unknown", "cross": "none", "macd": 0, "signal": 0,
                "hist": 0, "hist_slope": 0, "state_prev": "unknown",
                "cross_bars": 0, "bar_time_ist": ""}

    c = hourly["close"]
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    macd_line = ema12 - ema26
    macd_signal = macd_line.ewm(span=9, adjust=False).mean()
    hist = macd_line - macd_signal
    hist_slope = hist.diff()

    states = ["green" if m > s else "red" for m, s in zip(macd_line, macd_signal)]

    latest = hourly.iloc[-1]
    latest_macd = float(macd_line.iloc[-1])
    latest_signal = float(macd_signal.iloc[-1])
    latest_hist = float(hist.iloc[-1])
    latest_slope = float(hist_slope.iloc[-1]) if not pd.isna(hist_slope.iloc[-1]) else 0.0

    # Detect cross up/down
    current_state = states[-1] if len(states) > 1 else "unknown"
    prev_state = states[-2] if len(states) > 2 else "unknown"

    cross = "none"
    cross_bars = 0
    if prev_state != "unknown" and current_state != "unknown":
        if prev_state == "red" and current_state == "green":
            cross = "up"
        elif prev_state == "green" and current_state == "red":
            cross = "down"

        # Count bars since last cross
        for i in range(len(states) - 2, -1, -1):
            if i > 0 and states[i] != states[i - 1]:
                cross_bars = len(states) - 1 - i
                break

    return {
        "state": current_state,
        "cross": cross,
        "macd": round(latest_macd, 2),
        "signal": round(latest_signal, 2),
        "hist": round(latest_hist, 2),
        "hist_slope": round(latest_slope, 4),
        "state_prev": prev_state,
        "cross_bars": cross_bars,
        "bar_time_ist": str(hourly.index[-1].strftime("%Y-%m-%d %H:%M")),
    }


def resample_ohlc(labels, opens, highs, lows, closes, volumes, freq_min: int):
    """Resample OHLC 1m lists to target frequency (minutes).
    Returns (labels, opens, highs, lows, closes, volumes) as lists.
    """
    if not labels or not closes or len(closes) < 2:
        return [], [], [], [], [], []
    idx = pd.to_datetime(labels, utc=False)
    if idx.tz is None:
        idx = idx.tz_localize("Asia/Kolkata", ambiguous="infer").tz_convert("UTC")
    df = pd.DataFrame({
        "Open": opens, "High": highs, "Low": lows, "Close": closes, "Volume": volumes
    }, index=idx)
    freq = f"{freq_min}min"
    out = (df.resample(freq, label="left", closed="left")
           .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"})
           .dropna(subset=["Close"]))
    new_labels = [str(ts) for ts in out.index]
    return (new_labels,
            out["Open"].tolist(), out["High"].tolist(),
            out["Low"].tolist(), out["Close"].tolist(),
            out["Volume"].astype(int).tolist())
