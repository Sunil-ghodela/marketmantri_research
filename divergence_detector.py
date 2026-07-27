"""
Detect simple price/oscillator divergence around Amavasya research windows.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
TRADING_TZ = "Asia/Kolkata"


def _ensure_utc_datetime(series: pd.Series) -> pd.Series:
    out = pd.to_datetime(series)
    if out.dt.tz is None:
        return out.dt.tz_localize("UTC")
    return out.dt.tz_convert("UTC")


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
    df["macd"] = df["close"].ewm(span=fast, adjust=False).mean() - df["close"].ewm(
        span=slow, adjust=False
    ).mean()
    df["macd_signal"] = df["macd"].ewm(span=signal, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]
    return df


def _pivot_positions(
    values: pd.Series,
    mode: str,
    left: int,
    right: int,
    min_prominence_pct: float,
) -> list[int]:
    positions: list[int] = []
    vals = values.reset_index(drop=True)
    for pos in range(left, len(vals) - right):
        window = vals.iloc[pos - left : pos + right + 1]
        current = vals.iloc[pos]
        surrounding = window.drop(window.index[left])
        if mode == "low" and current == window.min() and (window == current).sum() == 1:
            prominence_pct = (float(surrounding.min()) / float(current) - 1.0) * 100.0
            if prominence_pct < min_prominence_pct:
                continue
            positions.append(pos)
        elif mode == "high" and current == window.max() and (window == current).sum() == 1:
            prominence_pct = (float(current) / float(surrounding.max()) - 1.0) * 100.0
            if prominence_pct < min_prominence_pct:
                continue
            positions.append(pos)
    return positions


def _resolution_for(
    df: pd.DataFrame,
    kind: str,
    second_pos: int,
    max_resolution_bars: int,
) -> tuple[bool, int | None, str]:
    second = df.iloc[second_pos]
    future_end = min(len(df), second_pos + max_resolution_bars + 1)
    future = df.iloc[second_pos + 1 : future_end]
    if future.empty:
        return False, None, ""

    if kind == "bullish":
        hits = future[future["close"] > float(second["high"])]
    else:
        hits = future[future["close"] < float(second["low"])]

    if hits.empty:
        return False, None, ""
    resolution_label = hits.index[0].strftime("%Y-%m-%d %H:%M")
    return True, int(df.index.get_loc(hits.index[0])), resolution_label


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
    """Detect bullish/bearish divergence between consecutive pivot lows/highs."""
    required = {"high", "low", "close", oscillator_col}
    missing = required - set(data.columns)
    if missing:
        raise ValueError(f"missing divergence columns: {sorted(missing)}")

    df = data.copy()
    if "date" in df.columns:
        df["date"] = _ensure_utc_datetime(df["date"])
        df = df.sort_values("date").set_index("date")
        df.index = df.index.tz_convert(TRADING_TZ)

    rows: list[dict[str, object]] = []
    low_positions = _pivot_positions(df["low"], "low", pivot_left, pivot_right, min_prominence_pct)
    high_positions = _pivot_positions(
        df["high"], "high", pivot_left, pivot_right, min_prominence_pct
    )

    for first_pos, second_pos in zip(low_positions, low_positions[1:]):
        first = df.iloc[first_pos]
        second = df.iloc[second_pos]
        price_move_pct = _price_move_pct(float(first["low"]), float(second["low"]))
        if price_move_pct < min_price_move_pct:
            continue
        regular = float(second["low"]) < float(first["low"]) and float(
            second[oscillator_col]
        ) > float(first[oscillator_col])
        hidden = include_hidden and float(second["low"]) > float(first["low"]) and float(
            second[oscillator_col]
        ) < float(first[oscillator_col])
        if regular or hidden:
            resolved, resolution_pos, resolution_time = _resolution_for(
                df, "bullish", second_pos, max_resolution_bars
            )
            rows.append(
                _event_row(
                    df,
                    "bullish",
                    first_pos,
                    second_pos,
                    oscillator_col,
                    resolved,
                    resolution_pos,
                    resolution_time,
                    "regular" if regular else "hidden",
                    price_move_pct,
                )
            )

    for first_pos, second_pos in zip(high_positions, high_positions[1:]):
        first = df.iloc[first_pos]
        second = df.iloc[second_pos]
        price_move_pct = _price_move_pct(float(first["high"]), float(second["high"]))
        if price_move_pct < min_price_move_pct:
            continue
        regular = float(second["high"]) > float(first["high"]) and float(
            second[oscillator_col]
        ) < float(first[oscillator_col])
        hidden = include_hidden and float(second["high"]) < float(first["high"]) and float(
            second[oscillator_col]
        ) > float(first[oscillator_col])
        if regular or hidden:
            resolved, resolution_pos, resolution_time = _resolution_for(
                df, "bearish", second_pos, max_resolution_bars
            )
            rows.append(
                _event_row(
                    df,
                    "bearish",
                    first_pos,
                    second_pos,
                    oscillator_col,
                    resolved,
                    resolution_pos,
                    resolution_time,
                    "regular" if regular else "hidden",
                    price_move_pct,
                )
            )

    out = pd.DataFrame(rows)
    if out.empty:
        return out
    return out.sort_values("second_time_ist").reset_index(drop=True)


def _event_row(
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
    first = df.iloc[first_pos]
    second = df.iloc[second_pos]
    oscillator_delta = float(second[oscillator_col]) - float(first[oscillator_col])
    return {
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
    }


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


def _window_bounds(
    row: pd.Series, lookback_days: int, lookahead_days: int
) -> tuple[pd.Timestamp, pd.Timestamp]:
    start = pd.Timestamp(str(row["buy_date"]), tz=TRADING_TZ) - pd.Timedelta(days=lookback_days)
    end = (
        pd.Timestamp(f"{row['sell_date']} 23:59", tz=TRADING_TZ)
        + pd.Timedelta(days=lookahead_days)
    )
    return start, end


def attach_divergence_to_feedback(
    feedback: pd.DataFrame,
    intraday: pd.DataFrame,
    oscillator_col: str = "macd_hist",
    lookback_days: int = 2,
    lookahead_days: int = 2,
    pivot_left: int = 3,
    pivot_right: int = 3,
    min_prominence_pct: float = 0.03,
    min_price_move_pct: float = 0.08,
    include_hidden: bool = True,
    buffer_days: int = 5,
) -> pd.DataFrame:
    """Attach divergence counts and latest event info around each feedback trade."""
    prepared = prepare_intraday(intraday) if oscillator_col == "macd_hist" else _to_ist_index(intraday)
    prepared = _slice_to_feedback_window(
        prepared,
        feedback,
        lookback_days=lookback_days,
        lookahead_days=lookahead_days,
        buffer_days=buffer_days,
    )
    events = detect_divergences(
        prepared,
        oscillator_col=oscillator_col,
        pivot_left=pivot_left,
        pivot_right=pivot_right,
        min_prominence_pct=min_prominence_pct,
        min_price_move_pct=min_price_move_pct,
        include_hidden=include_hidden,
    )

    rows = []
    for _, row in feedback.iterrows():
        start, end = _window_bounds(row, lookback_days, lookahead_days)
        enriched = row.to_dict()
        if events.empty:
            window_events = events
        else:
            second_ts = pd.to_datetime(events["second_time_ist"]).dt.tz_localize(TRADING_TZ)
            window_events = events[(second_ts >= start) & (second_ts <= end)]

        bullish = window_events[window_events["kind"] == "bullish"]
        bearish = window_events[window_events["kind"] == "bearish"]
        hidden = window_events[window_events["pattern"] == "hidden"]
        strong = window_events[window_events["strength"] == "strong"]
        last = window_events.iloc[-1] if not window_events.empty else None
        # For a close-entry research row, an intraday resolution before 15:30 is still
        # actionable because it can confirm the setup before the fixed close.
        buy_ts = pd.Timestamp(str(row["buy_date"]), tz=TRADING_TZ)
        resolution_after_entry = _has_resolution_after(window_events, buy_ts)
        avoid_long = bool(
            not bearish.empty
            and (
                bullish.empty
                or bearish.iloc[-1]["second_time_ist"] > bullish.iloc[-1]["second_time_ist"]
            )
        )

        enriched.update(
            {
                "bullish_divergence_count": int(len(bullish)),
                "bearish_divergence_count": int(len(bearish)),
                "hidden_divergence_count": int(len(hidden)),
                "strong_divergence_count": int(len(strong)),
                "last_divergence_kind": "" if last is None else str(last["kind"]),
                "last_divergence_pattern": "" if last is None else str(last["pattern"]),
                "last_divergence_strength": "" if last is None else str(last["strength"]),
                "last_divergence_time_ist": "" if last is None else str(last["second_time_ist"]),
                "last_divergence_resolved": False if last is None else bool(last["resolved"]),
                "last_resolution_time_ist": "" if last is None else str(last["resolution_time_ist"]),
                "resolution_after_entry": bool(resolution_after_entry),
                "avoid_long_flag": avoid_long,
            }
        )
        rows.append(enriched)
    return pd.DataFrame(rows)


def _to_ist_index(data: pd.DataFrame) -> pd.DataFrame:
    if "date" not in data.columns:
        return data.copy()
    df = data.copy()
    df["date"] = _ensure_utc_datetime(df["date"])
    df = df.sort_values("date").set_index("date")
    df.index = df.index.tz_convert(TRADING_TZ)
    return df


def _slice_to_feedback_window(
    data: pd.DataFrame,
    feedback: pd.DataFrame,
    lookback_days: int,
    lookahead_days: int,
    buffer_days: int,
) -> pd.DataFrame:
    if feedback.empty or not isinstance(data.index, pd.DatetimeIndex):
        return data

    starts = []
    ends = []
    for _, row in feedback.iterrows():
        start, end = _window_bounds(row, lookback_days, lookahead_days)
        starts.append(start)
        ends.append(end)

    start_ts = min(starts) - pd.Timedelta(days=buffer_days)
    end_ts = max(ends) + pd.Timedelta(days=buffer_days)
    return data.loc[(data.index >= start_ts) & (data.index <= end_ts)]


def _has_resolution_after(events: pd.DataFrame, buy_ts: pd.Timestamp) -> bool:
    if events.empty:
        return False
    for _, event in events.iterrows():
        if not bool(event["resolved"]) or not event["resolution_time_ist"]:
            continue
        resolution_ts = pd.Timestamp(str(event["resolution_time_ist"]), tz=TRADING_TZ)
        if resolution_ts >= buy_ts:
            return True
    return False


def main() -> None:
    feedback_path = HERE / "docs" / "research" / "amavasya_manual_feedback_macd_2025_2026.csv"
    intraday_path = HERE / "data" / "NIFTY50_15m.feather"
    out_path = HERE / "docs" / "research" / "amavasya_manual_feedback_divergence_2025_2026.csv"

    feedback = pd.read_csv(feedback_path)
    intraday = pd.read_feather(intraday_path)
    enriched = attach_divergence_to_feedback(feedback, intraday)
    enriched.to_csv(out_path, index=False)
    print(f"wrote {len(enriched)} rows to {out_path.relative_to(HERE)}")


if __name__ == "__main__":
    main()
