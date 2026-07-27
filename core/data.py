"""Yahoo Finance data fetching, archiving, OHLC processing."""
from __future__ import annotations
import os, sys, time, datetime, random, threading, logging
from typing import Any
import pandas as pd
import yfinance as yf

from core.state import state, get_raw_cache, set_raw_cache
from core.indicators import calc_rsi, calc_adx, calc_ema, calc_ema_series, resample_ohlc
from core.new_moon import fetch_new_moon_state
from core.signals import apply_instruments_eval, check_multi_signals, auto_manage_instrument_trade

import strategy_live

logger = logging.getLogger("baba")

# ── Config ──
PRIMARY_TICKER = strategy_live.PRIMARY_TICKER
CHART_YAHOO = "^NSEI"
CHART_LABEL = "NIFTY 50"
DATA_INTERVAL = "1m"
DATA_PERIOD = "5d"
YAHOO_1M_ARCHIVE_DIR = "data/yahoo_1m_archive"
YAHOO_1M_ARCHIVE_DAYS = 60
DAILY_ARCHIVE_DIR = "data/daily_archive"

# Daily data cache for 1d/1w/1M timeframes
_DAILY_CACHE: dict[str, dict] = {}

CHART_INSTRUMENTS = {
    "NIFTY":     {"yahoo": "^NSEI",     "label": "NIFTY 50"},
    "BANKNIFTY": {"yahoo": "^NSEBANK",  "label": "BANK NIFTY"},
    "NIFTYBEES": {"yahoo": "NIFTYBEES.NS", "label": "NIFTYBEES"},
}

RSI_BUY = 35
RSI_SELL = 65
PAPER_MODE = "strategy_py_4inst"

MARKET_OPEN_HM = (9, 0)
MARKET_CLOSE_HM = (15, 30)

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:
    IST = None


def now_ist():
    if IST is not None:
        return datetime.datetime.now(IST)
    return datetime.datetime.now()


def is_market_open(now=None):
    n = now or now_ist()
    if n.weekday() >= 5:
        return False
    open_dt = n.replace(hour=MARKET_OPEN_HM[0], minute=MARKET_OPEN_HM[1], second=0, microsecond=0)
    close_dt = n.replace(hour=MARKET_CLOSE_HM[0], minute=MARKET_CLOSE_HM[1], second=0, microsecond=0)
    return open_dt <= n <= close_dt


# ── Helpers ──

def df15_to_lists(df15: pd.DataFrame):
    labels, opens, highs, lows, closes, volumes = [], [], [], [], [], []
    for ts, row in df15.iterrows():
        t = pd.Timestamp(ts)
        if t.tz is None:
            t = t.tz_localize("UTC")
        ist = t.tz_convert(IST or "Asia/Kolkata")
        labels.append(ist.strftime("%Y-%m-%d %H:%M"))
        opens.append(float(row["Open"]))
        highs.append(float(row["High"]))
        lows.append(float(row["Low"]))
        closes.append(float(row["Close"]))
        volumes.append(int(row.get("Volume", 0) or 0))
    return labels, opens, highs, lows, closes, volumes


def pack_to_df(pack):
    if not pack:
        return pd.DataFrame()
    labels, opens, highs, lows, closes, volumes = pack
    out = pd.DataFrame({
        "label": [str(v)[:16] for v in labels],
        "open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes,
    })
    out["ts"] = pd.to_datetime(out["label"], errors="coerce")
    return out.dropna(subset=["ts"])


def df_to_pack(df: pd.DataFrame):
    if df is None or df.empty:
        return None
    df = df.sort_values("ts").drop_duplicates("label", keep="last")
    return (
        df["label"].astype(str).tolist(),
        df["open"].astype(float).tolist(),
        df["high"].astype(float).tolist(),
        df["low"].astype(float).tolist(),
        df["close"].astype(float).tolist(),
        df["volume"].fillna(0).astype(int).tolist(),
    )


def merge_ohlc_packs(*packs):
    frames = [pack_to_df(pack) for pack in packs if pack]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return None
    merged = pd.concat(frames, ignore_index=True)
    cutoff = pd.Timestamp(datetime.date.today() - datetime.timedelta(days=YAHOO_1M_ARCHIVE_DAYS))
    merged = merged[merged["ts"] >= cutoff]
    return df_to_pack(merged)


def _daily_archive_file(yahoo_sym: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in yahoo_sym).strip("_")
    return os.path.join(DAILY_ARCHIVE_DIR, f"{safe}_1d.parquet")


def _save_daily_archive(yahoo_sym: str, result: dict) -> None:
    """Persist daily candles to disk, merged with any existing history (dedup by date)."""
    try:
        df = pd.DataFrame({
            "date": result["labels"], "open": result["opens"], "high": result["highs"],
            "low": result["lows"], "close": result["closes"], "volume": result["volumes"],
        })
        if df.empty:
            return
        os.makedirs(DAILY_ARCHIVE_DIR, exist_ok=True)
        path = _daily_archive_file(yahoo_sym)
        if os.path.exists(path):
            df = pd.concat([pd.read_parquet(path), df], ignore_index=True)
        df = df.drop_duplicates("date", keep="last").sort_values("date")
        df.to_parquet(path, index=False)
    except Exception as e:
        logger.warning(f"Daily archive save failed for {yahoo_sym}: {e}")


def _load_daily_archive(yahoo_sym: str) -> dict | None:
    path = _daily_archive_file(yahoo_sym)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path).drop_duplicates("date", keep="last").sort_values("date")
        if df.empty:
            return None
        return {
            "labels": df["date"].astype(str).tolist(),
            "opens": df["open"].tolist(), "highs": df["high"].tolist(),
            "lows": df["low"].tolist(), "closes": df["close"].tolist(),
            "volumes": df["volume"].astype(int).tolist(),
        }
    except Exception as e:
        logger.warning(f"Daily archive load failed for {yahoo_sym}: {e}")
        return None


def fetch_daily_data(yahoo_sym: str, period: str = "2y") -> dict | None:
    """Fetch daily OHLC for a symbol, persist it, and fall back to saved data.

    On a successful live fetch we save to disk (accumulating history). If the live
    fetch fails (yfinance/Yahoo outage), we serve the last-saved daily archive so
    the chart never shows "no data". period: yfinance period (1y, 2y, 5y, max).
    """
    cache_key = f"{yahoo_sym}:{period}"
    if cache_key in _DAILY_CACHE:
        return _DAILY_CACHE.get(cache_key)
    try:
        df = yf.Ticker(yahoo_sym).history(period=period, interval="1d", timeout=8)
        if df is None or df.empty:
            raise ValueError("empty response")
        labels, opens, highs, lows, closes, volumes = [], [], [], [], [], []
        for t in df.index.tolist():
            labels.append(str(t).replace("T", " ")[:10])
            opens.append(float(df["Open"].loc[t]))
            highs.append(float(df["High"].loc[t]))
            lows.append(float(df["Low"].loc[t]))
            closes.append(float(df["Close"].loc[t]))
            volumes.append(int(df["Volume"].loc[t] or 0))
        result = {
            "labels": labels, "opens": opens, "highs": highs,
            "lows": lows, "closes": closes, "volumes": volumes,
        }
        _save_daily_archive(yahoo_sym, result)
        _DAILY_CACHE[cache_key] = result
        return result
    except Exception as e:
        logger.warning(f"Daily fetch failed for {yahoo_sym}: {e} — using saved archive")
        saved = _load_daily_archive(yahoo_sym)
        if saved:
            _DAILY_CACHE[cache_key] = saved
        return saved


def archive_file_for_symbol(yahoo_sym: str) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in yahoo_sym).strip("_")
    return os.path.join(YAHOO_1M_ARCHIVE_DIR, f"{safe}_1m.parquet")


def save_yahoo_1m_archive(yahoo_sym: str, pack) -> None:
    df = pack_to_df(pack)
    if df.empty:
        return
    try:
        os.makedirs(YAHOO_1M_ARCHIVE_DIR, exist_ok=True)
        path = archive_file_for_symbol(yahoo_sym)
        if os.path.exists(path):
            old = pd.read_parquet(path)
            if "ts" in old.columns:
                old["ts"] = pd.to_datetime(old["ts"], errors="coerce")
            df = pd.concat([old, df], ignore_index=True)
        cutoff = pd.Timestamp(datetime.date.today() - datetime.timedelta(days=YAHOO_1M_ARCHIVE_DAYS + 7))
        df = df.dropna(subset=["ts"])
        df = df[df["ts"] >= cutoff]
        df = df.sort_values("ts").drop_duplicates("label", keep="last")
        df.to_parquet(path, index=False)
        logger.info(f"Archived {len(df)} 1m bars for {yahoo_sym} → {path}")
    except Exception as e:
        logger.warning(f"Yahoo 1m archive save failed for {yahoo_sym}: {e}")


def load_yahoo_1m_archive(yahoo_sym: str, days: int = YAHOO_1M_ARCHIVE_DAYS):
    path = archive_file_for_symbol(yahoo_sym)
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_parquet(path)
        if df.empty:
            return None
        df["ts"] = pd.to_datetime(df["ts"], errors="coerce")
        cutoff = pd.Timestamp(datetime.date.today() - datetime.timedelta(days=days))
        df = df.dropna(subset=["ts"])
        df = df[df["ts"] >= cutoff]
        return df_to_pack(df)
    except Exception as e:
        logger.warning(f"Yahoo 1m archive load failed for {yahoo_sym}: {e}")
        return None


def yf_history(yahoo_sym: str):
    """Fetch live + archived 1m data for a symbol. Returns merged pack or None."""
    df = yf.Ticker(yahoo_sym).history(period=DATA_PERIOD, interval=DATA_INTERVAL, timeout=8)
    live_pack = None
    if df is not None and not df.empty and len(df) >= 15:
        labels, opens, highs, lows, closes, volumes = [], [], [], [], [], []
        for t in df.index.tolist():
            labels.append(str(t).replace("T", " ")[:16])
            opens.append(float(df["Open"].loc[t]))
            highs.append(float(df["High"].loc[t]))
            lows.append(float(df["Low"].loc[t]))
            closes.append(float(df["Close"].loc[t]))
            volumes.append(int(df["Volume"].loc[t] or 0))
        live_pack = labels, opens, highs, lows, closes, volumes
        save_yahoo_1m_archive(yahoo_sym, live_pack)
    archived_pack = load_yahoo_1m_archive(yahoo_sym)
    merged = merge_ohlc_packs(archived_pack, live_pack)
    if merged and len(merged[0]) >= 15:
        return merged
    return live_pack


# ── Process candles ──

def process_candles(opens, closes, highs, lows, volumes, labels=None) -> None:
    state["ltp"] = float(closes[-1]) if closes else 0.0
    state["close"] = float(closes[-1]) if closes else 0.0

    if labels:
        last_date = str(labels[-1])[:10]
        today_idxs = [i for i, lbl in enumerate(labels) if str(lbl)[:10] == last_date]
    else:
        today_idxs = list(range(len(closes)))

    if today_idxs:
        state["open"] = float(opens[today_idxs[0]])
        state["high"] = float(max(highs[i] for i in today_idxs))
        state["low"] = float(min(lows[i] for i in today_idxs))
        state["volume"] = int(sum(int(volumes[i]) for i in today_idxs)) if volumes else 0
        prev_idx = today_idxs[0] - 1
        state["prev_close"] = float(closes[prev_idx]) if prev_idx >= 0 else float(opens[today_idxs[0]])
    else:
        state["open"] = float(opens[0]) if opens else 0.0
        state["high"] = float(max(highs[-20:])) if highs else 0.0
        state["low"] = float(min(lows[-20:])) if lows else 0.0
        state["volume"] = int(volumes[-1]) if volumes else 0
        state["prev_close"] = float(closes[0]) if closes else 0.0

    state["change_pct"] = (
        round(((state["close"] - state["open"]) / state["open"]) * 100, 2)
        if state["open"] else 0.0
    )

    if labels:
        state["chart_labels"] = labels
    else:
        state["chart_labels"] = [str(i) for i in range(len(closes))]
    state["chart_closes"] = [round(float(c), 2) for c in closes]
    state["chart_opens"] = [round(float(o), 2) for o in opens]
    state["chart_highs"] = [round(float(h), 2) for h in highs]
    state["chart_lows"] = [round(float(l), 2) for l in lows]
    state["chart_volumes"] = [int(v) for v in volumes]
    state["chart_ema9"] = calc_ema_series([float(c) for c in closes], 9)
    state["chart_ema21"] = calc_ema_series([float(c) for c in closes], 21)

    seen = set()
    sess = []
    for lbl in state["chart_labels"]:
        d = str(lbl)[:10]
        if len(d) == 10 and d not in seen:
            seen.add(d)
            sess.append(d)
    state["session_dates"] = sess

    recent_n = min(200, len(closes))
    recent_c = closes[-recent_n:]
    recent_h = highs[-recent_n:]
    recent_l = lows[-recent_n:]

    state["rsi"] = calc_rsi(recent_c)
    state["adx"] = calc_adx(recent_h, recent_l, recent_c)
    state["ema9"] = calc_ema(recent_c, 9)
    state["ema21"] = calc_ema(recent_c, 21)

    if state["adx"] and state["adx"] > 0:
        if state["adx"] < 25:
            state["regime"] = "CHOPPY"
            state["strategy"] = "RSI Reversal"
            state["target_pct"] = 0.6
            state["stop_pct"] = 0.2
        else:
            state["regime"] = "TREND"
            state["strategy"] = "EMA Pullback"
            state["target_pct"] = 1.2
            state["stop_pct"] = 0.4
    else:
        state["regime"] = "WAITING"
        state["strategy"] = "—"

    state["last_updated"] = datetime.datetime.now().strftime("%H:%M:%S")


# ── Yahoo fetch main ──

def fetch_yahoo() -> None:
    try:
        instruments = {}
        primary_pack = None
        errors = []

        for ticker in strategy_live.INSTRUMENTS:
            ysym = strategy_live.YAHOO_TICKERS[ticker]
            pack = yf_history(ysym)
            if pack is None:
                errors.append(ticker)
                try:
                    warmup = strategy_live.load_warmup_tail(ticker)
                    if len(warmup) >= 100:
                        ev = strategy_live.evaluate_ticker(ticker, warmup)
                        ev["data_source"] = "warmup (yahoo unavailable)"
                        instruments[ticker] = ev
                    else:
                        instruments[ticker] = {"ok": False, "ticker": ticker, "reason": f"no yahoo + warmup {len(warmup)}"}
                except Exception as warmup_err:
                    instruments[ticker] = {"ok": False, "ticker": ticker, "reason": f"no yahoo + warmup error: {str(warmup_err)[:50]}"}
                continue
            labels, opens, highs, lows, closes, volumes = pack
            ev = strategy_live.evaluate_from_1m(ticker, labels, opens, highs, lows, closes, volumes)
            instruments[ticker] = ev
            if ticker == PRIMARY_TICKER:
                primary_pack = pack

        chart_pack = yf_history(CHART_YAHOO)
        if chart_pack is None and primary_pack is not None:
            chart_pack = primary_pack
        if chart_pack is None:
            try:
                warmup_df = strategy_live.load_warmup_tail("NIFTY50")
                if len(warmup_df) >= 20:
                    l15, o15, h15, lo15, c15, v15 = df15_to_lists(warmup_df)
                    process_candles(o15, c15, h15, lo15, v15, l15)
                    state["symbol"] = CHART_LABEL
                    state["data_source"] = "warmup (yahoo unavailable)"
                    logger.info(f"Using NIFTY warmup chart ({len(warmup_df)} bars)")
                else:
                    raise ValueError(f"Warmup too short: {len(warmup_df)}")
            except Exception:
                use_simulated()
                return
        else:
            labels, opens, highs, lows, closes, volumes = chart_pack
            df15 = strategy_live.resample_1m_lists(labels, opens, highs, lows, closes, volumes)
            if len(df15) >= 5:
                l15, o15, h15, lo15, c15, v15 = df15_to_lists(df15)
                process_candles(o15, c15, h15, lo15, v15, l15)
            else:
                process_candles(opens, closes, highs, lows, volumes, labels)
                state["regime"] = "WAITING"
                state["strategy"] = "strategy.py (warming up)"

        if state["regime"] != "ERROR":
            state["symbol"] = CHART_LABEL
            apply_instruments_eval(instruments, len(state.get("chart_closes", [])))

        # ── Multi-instrument chart data ──
        state["instrument_charts"] = {}
        for key, cfg in CHART_INSTRUMENTS.items():
            pack = yf_history(cfg["yahoo"])
            if pack:
                lbls, ops, his, los, cls, vols = pack
                set_raw_cache(key, {"labels": lbls, "opens": ops, "highs": his, "lows": los, "closes": cls, "volumes": vols})
                df15 = strategy_live.resample_1m_lists(lbls, ops, his, los, cls, vols)
                if len(df15) >= 5:
                    l15, o15, h15, lo15, c15, v15 = df15_to_lists(df15)
                    _, _, _, _, _, _ = resample_ohlc(lbls, ops, his, los, cls, vols, 1) if len(lbls) > 50 else (None,) * 6
                    l5, o5, h5, l5o, c5, v5 = resample_ohlc(lbls, ops, his, los, cls, vols, 5)
                    l60, o60, h60, l60o, c60, v60 = resample_ohlc(lbls, ops, his, los, cls, vols, 60)
                    state["instrument_charts"][key] = {
                        "label": cfg["label"],
                        "ltp": round(float(c15[-1]), 2),
                        "change_pct": round((float(c15[-1]) - float(o15[0])) / float(o15[0]) * 100, 2) if o15 else 0,
                        "high": max(h15), "low": min(lo15),
                        "timeframes": {
                            "1m": {"labels": lbls, "opens": ops, "highs": his, "lows": los, "closes": cls, "volumes": vols},
                            "5m": {"labels": l5, "opens": o5, "highs": h5, "lows": l5o, "closes": c5, "volumes": v5},
                            "15m": {"labels": l15, "opens": o15, "highs": h15, "lows": lo15, "closes": c15, "volumes": v15},
                            "60m": {"labels": l60, "opens": o60, "highs": h60, "lows": l60o, "closes": c60, "volumes": v60},
                        }
                    }

        if errors:
            state["error"] = "partial: missing " + ", ".join(errors)
        else:
            state["error"] = None
        state["data_source"] = "yfinance 1m→15m"
        prim = instruments.get(PRIMARY_TICKER, {})
        logger.info(f"OK: {PRIMARY_TICKER} LTP={prim.get('ltp')} | long={[t for t,e in instruments.items() if e.get('in_pos')]} | sig={state.get('signal')}")

    except Exception as e:
        state["error"] = str(e)[:100]
        logger.error(f"Yahoo error: {e}")
        use_simulated()


def use_simulated() -> None:
    random.seed(42)
    base = 24300.0
    sim_o, sim_c, sim_h, sim_l, sim_v, sim_lbl = [], [], [], [], [], []
    today = datetime.date.today()
    days = []
    d = today
    while len(days) < 5:
        if d.weekday() < 5:
            days.append(d)
        d -= datetime.timedelta(days=1)
    days.reverse()
    for day in days:
        for m in range(375):
            hr = 9 + (15 + m) // 60
            mn = (15 + m) % 60
            o = base + random.gauss(0, 5)
            h = o + abs(random.gauss(0, 8))
            l = o - abs(random.gauss(0, 8))
            c = l + (h - l) * random.random()
            sim_o.append(o); sim_c.append(c); sim_h.append(h); sim_l.append(l)
            sim_v.append(random.randint(40000, 250000))
            sim_lbl.append(f"{day.isoformat()} {hr:02d}:{mn:02d}")
            base = c + random.gauss(0, 1.5)
    process_candles(sim_o, sim_c, sim_h, sim_l, sim_v, sim_lbl)
    if "simulat" not in (state.get("error") or "").lower():
        state["error"] = "SIMULATED (yfinance unavailable)"
    state["data_source"] = "simulation"
    instruments = {}
    for ticker in strategy_live.INSTRUMENTS:
        instruments[ticker] = strategy_live.evaluate_from_1m(ticker, sim_lbl, sim_o, sim_h, sim_l, sim_c, sim_v)
    apply_instruments_eval(instruments, len(sim_c))


def rebuild_backtest_trades() -> None:
    """Simulate backtest on current chart data using RSI/ADX/EMA logic."""
    labels = state["chart_labels"]
    opens = state["chart_opens"]
    closes = state["chart_closes"]
    if len(closes) < 30 or not labels:
        return
    sim_trades = []
    pos = None
    for i in range(21, len(closes)):
        recent_c = closes[max(0, i - 200 + 1): i + 1]
        recent_h = state["chart_highs"][max(0, i - 200 + 1): i + 1]
        recent_l = state["chart_lows"][max(0, i - 200 + 1): i + 1]
        rsi = calc_rsi(recent_c)
        adx = calc_adx(recent_h, recent_l, recent_c)
        ema9 = calc_ema(recent_c, 9)
        ema21 = calc_ema(recent_c, 21)
        px = float(closes[i])
        signal = None
        if adx < 25:
            if rsi <= RSI_BUY:
                signal = "BUY"
            elif rsi >= RSI_SELL:
                signal = "SELL"
        else:
            if ema9 is not None and ema21 is not None:
                if ema9 > ema21 and px <= ema9 * 1.001 and px >= ema9 * 0.998:
                    signal = "BUY"
                elif ema9 < ema21 and px >= ema9 * 0.999 and px <= ema9 * 1.003:
                    signal = "SELL"
        if not signal:
            continue
        if pos is None:
            pos = {"side": signal, "entry": px, "idx": i}
            continue
        if pos["side"] == signal:
            continue
        qty = 13
        pnl = (px - pos["entry"]) * qty if pos["side"] == "BUY" else (pos["entry"] - px) * qty
        sim_trades.append({
            "time": str(labels[i])[-8:] if len(str(labels[i])) >= 8 else str(labels[i]),
            "trade_date": str(labels[i])[:10], "chart_time": labels[i], "candle_idx": i,
            "type": pos["side"], "entry": float(pos["entry"]), "exit": px,
            "qty": qty, "pnl": round(float(pnl), 2), "notes": "AUTO-BACKTEST 60d", "regime": "SIM",
        })
        pos = {"side": signal, "entry": px, "idx": i}
    if pos is not None and len(closes) > 0:
        i = len(closes) - 1
        px = float(closes[i])
        qty = 13
        pnl = (px - pos["entry"]) * qty if pos["side"] == "BUY" else (pos["entry"] - px) * qty
        sim_trades.append({
            "time": str(labels[i])[-8:] if len(str(labels[i])) >= 8 else str(labels[i]),
            "trade_date": str(labels[i])[:10], "chart_time": labels[i], "candle_idx": i,
            "type": pos["side"], "entry": float(pos["entry"]), "exit": px,
            "qty": qty, "pnl": round(float(pnl), 2), "notes": "AUTO-BACKTEST 60d final close", "regime": "SIM",
        })
    from core.state import recalc_trade_stats, save_trades
    state["trades"] = sim_trades
    recalc_trade_stats()
    save_trades()


# ── Refresh loop ──

def _scan_momentum_basket() -> None:
    """Advance the momentum-basket paper engine (self-gated to ~15m + market hours). Never raises.
    Also does a light per-cycle (~60s) price refresh of open positions so live P&L moves between scans."""
    try:
        from core import momentum_portfolio_feed
        momentum_portfolio_feed.scan()             # full signal scan — entries/exits (self-gated ~15m)
        momentum_portfolio_feed.update_open_ltp()  # light price refresh for open positions (live P&L)
    except Exception:
        pass


def refresh_loop() -> None:
    fetch_yahoo()
    fetch_new_moon_state()
    _scan_momentum_basket()
    while True:
        sleep_s = 60 if is_market_open() else 300
        time.sleep(sleep_s)
        fetch_yahoo()
        _scan_momentum_basket()
        if sleep_s > 60:
            fetch_new_moon_state()


def start_refresh_thread() -> None:
    threading.Thread(target=refresh_loop, daemon=True).start()
