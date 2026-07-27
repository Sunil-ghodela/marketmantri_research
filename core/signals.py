"""Signal engine — instrument evaluation, strategy allocation, paper trade management."""
from __future__ import annotations
import logging
from typing import Any
from core.state import state

import strategy_live

logger = logging.getLogger("baba")

SIGNAL_COOLDOWN = 4


def apply_instruments_eval(instruments: dict, primary_bars: int) -> None:
    state["instruments"] = instruments
    in_pos = [t for t, e in instruments.items() if e.get("in_pos")]
    state["regime"] = "STRATEGY"
    state["strategy"] = (
        f"strategy.py × {len(strategy_live.INSTRUMENTS)}"
        + (f" | long: {', '.join(in_pos)}" if in_pos else " | flat")
    )
    primary = instruments.get(strategy_live.PRIMARY_TICKER, {})
    pt = primary.get("profit_target_pct") or 5.0
    state["target_pct"] = float(pt)
    state["stop_pct"] = 0.0
    check_multi_signals(instruments, primary_bars)


def check_multi_signals(instruments: dict, candles_count: int) -> None:
    state["signal"] = None
    state["signal_type"] = None
    state["signal_price"] = None
    state["signal_reason"] = ""

    ready = [t for t, e in instruments.items() if e.get("ok")]
    if not ready:
        state["signal_reason"] = "warming up (need 15m history)"
        return

    flat = [t for t in ready if not instruments[t].get("in_pos")]
    longs = [t for t in ready if instruments[t].get("in_pos")]
    state["signal_reason"] = (
        f"hold | long={','.join(longs) or 'none'} | flat={len(flat)}"
    )

    for ticker in strategy_live.INSTRUMENTS:
        ev = instruments.get(ticker) or {}
        if not ev.get("ok"):
            continue
        sig = ev.get("signal")
        if not sig:
            continue
        if "_last_signal_candle" not in state:
            state["_last_signal_candle"] = {}
        last = state["_last_signal_candle"].get(ticker, -999)
        if candles_count - last < SIGNAL_COOLDOWN:
            continue
        price = float(ev.get("ltp") or 0)
        if price <= 0:
            continue
        state["_last_signal_candle"][ticker] = candles_count
        state["signal"] = sig
        state["signal_type"] = sig
        state["signal_price"] = price
        state["signal_reason"] = f"{ticker}: {ev.get('signal_reason', '')}"
        logger.info(f"SIGNAL: {ticker} {sig} @ {price}")
        state["signals_log"].append({
            "type": sig, "symbol": ticker, "price": price,
            "reason": state["signal_reason"], "time": state["last_updated"],
            "regime": state.get("regime", ""), "candle_idx": candles_count,
        })
        state["signals_log"] = state["signals_log"][-50:]
        auto_manage_instrument_trade(ticker, sig, price, candles_count)
        break


def auto_manage_instrument_trade(ticker: str, side: str, price: float, candles_count: int) -> None:
    from core.state import append_trade
    import datetime
    if price <= 0 or not side:
        return
    idx = max(candles_count - 1, 0)
    now_time = state.get("last_updated") or datetime.datetime.now().strftime("%H:%M:%S")
    now_date = datetime.date.today().isoformat()
    chart_time = state["chart_labels"][idx] if idx < len(state["chart_labels"]) else now_time
    stake = 50_000
    qty = max(1, int(stake / max(float(price), 1.0)))

    if "positions" not in state:
        state["positions"] = {}
    pos = state["positions"].get(ticker)

    if pos is None:
        if side == "BUY":
            state["positions"][ticker] = {
                "side": "BUY", "entry": price, "entry_idx": idx,
                "entry_time": now_time, "entry_reason": state.get("signal_reason", ""), "qty": qty,
            }
        return

    if side == "SELL" and pos["side"] == "BUY":
        pnl = (price - pos["entry"]) * pos["qty"]
        append_trade({
            "time": now_time, "trade_date": now_date, "chart_time": chart_time,
            "candle_idx": idx, "symbol": ticker, "type": "BUY",
            "entry": float(pos["entry"]), "exit": float(price),
            "qty": int(pos["qty"]), "pnl": round(float(pnl), 2),
            "notes": f"AUTO paper {ticker} EXIT", "regime": state.get("regime", "—"),
        })
        state["positions"][ticker] = None
    elif side == "BUY" and pos["side"] == "BUY":
        return


def legacy_check_signals(candles_count: int) -> None:
    """Legacy 1m signal engine — kept for /rebuild_backtest compatibility."""
    rsi = state.get("rsi")
    adx = state.get("adx")
    ema9 = state.get("ema9")
    ema21 = state.get("ema21")
    ltp = state.get("ltp")

    if rsi is None or adx is None:
        return

    current_idx = candles_count
    state["signal"] = None
    state["signal_type"] = None
    state["signal_price"] = None
    state["signal_reason"] = ""

    if current_idx - state.get("_legacy_signal_candle", -999) < SIGNAL_COOLDOWN:
        return

    if adx < 25:
        if rsi <= 35:
            state["signal"] = "BUY"
            state["signal_type"] = "BUY"
            state["signal_price"] = ltp
            state["signal_reason"] = f"RSI={rsi} (≤35) Oversold"
            state["_legacy_signal_candle"] = current_idx
            logger.info(f"SIGNAL: BUY @ {ltp}")
        elif rsi >= 65:
            state["signal"] = "SELL"
            state["signal_type"] = "SELL"
            state["signal_price"] = ltp
            state["signal_reason"] = f"RSI={rsi} (≥65) Overbought"
            state["_legacy_signal_candle"] = current_idx
            logger.info(f"SIGNAL: SELL @ {ltp}")
    else:
        if ema9 is not None and ema21 is not None and ltp > 0:
            if ema9 > ema21 and ltp <= ema9 * 1.001 and ltp >= ema9 * 0.998:
                state["signal"] = "BUY"
                state["signal_type"] = "BUY"
                state["signal_price"] = ltp
                state["signal_reason"] = f"EMA9 pullback ({ema9:.2f}) uptrend"
                state["_legacy_signal_candle"] = current_idx
                logger.info(f"SIGNAL: BUY @ {ltp}")
            elif ema9 < ema21 and ltp >= ema9 * 0.999 and ltp <= ema9 * 1.003:
                state["signal"] = "SELL"
                state["signal_type"] = "SELL"
                state["signal_price"] = ltp
                state["signal_reason"] = f"EMA9 pullback ({ema9:.2f}) downtrend"
                state["_legacy_signal_candle"] = current_idx
                logger.info(f"SIGNAL: SELL @ {ltp}")

    if state["signal"]:
        state["signals_log"].append({
            "type": state["signal"], "price": state["signal_price"],
            "reason": state["signal_reason"], "time": state["last_updated"],
            "regime": state.get("regime", ""), "candle_idx": current_idx,
        })
        state["signals_log"] = state["signals_log"][-50:]
