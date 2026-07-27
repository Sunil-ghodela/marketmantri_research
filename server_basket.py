"""Minimal momentum-basket server — for basket.shadowselfwork.com (VPS, unattended).
Serves the momentum dashboard + its 2 data endpoints + a /scan trigger for cron.
Yahoo-only (no Kite). Single process — the engine state is a JSON file on disk, so cron (which calls
/scan every 15 min during market hours) and the web view share the same state. Runs on 127.0.0.1:5000
behind nginx (basket.shadowselfwork.com). Keeps the live paper record updating even with no browser open.
"""
import json
import os
from flask import Flask, jsonify, send_from_directory
import pandas as pd
from core import momentum_portfolio

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__)


@app.route("/")
@app.route("/momentum_portfolio.html")
def page():
    return send_from_directory(HERE, "momentum_portfolio.html")


@app.route("/momentum_portfolio_data")
def mp_data():
    ltp_map, watchlist = {}, []
    try:
        from core import momentum_portfolio_feed as feed
        ltp_map = feed.last_ltp()
        watchlist = list(feed.WATCH)
    except Exception:
        pass
    view = momentum_portfolio.read(ltp_map)
    view["watchlist"] = watchlist
    return jsonify(view)


@app.route("/momentum_universe")
def mp_universe():
    path = os.path.join(HERE, "momentum_breadth_FIXED.csv")
    if not os.path.exists(path):
        return jsonify({"ok": False, "rows": [], "error": "breadth file not found"})
    try:
        df = pd.read_csv(path)
        rows = [{
            "stock": str(r["stock"]), "cap": str(r.get("cap", "")),
            "sharpe_10yr": round(float(r.get("sharpe_10yr", 0)), 2),
            "sharpe_2yr": round(float(r.get("sharpe_2yr", 0)), 2),
            "return_pct": round(float(r.get("return%", 0)), 0),
            "maxdd_pct": round(float(r.get("maxDD%", 0)), 1),
            "win_rate": round(float(r.get("WR%", 0)), 1),
        } for _, r in df.iterrows()]
        return jsonify({"ok": True, "rows": rows})
    except Exception as e:
        return jsonify({"ok": False, "rows": [], "error": str(e)})


@app.route("/scan")
def scan():
    """Cron hits this every 15 min during market hours → updates the basket WITHOUT a browser open."""
    try:
        from core import momentum_portfolio_feed as feed
        try:
            feed.update_open_ltp()
        except Exception:
            pass
        res = feed.scan(force=True)
        return jsonify({"ok": True, "updated": res is not None})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/nifty")
@app.route("/nifty_signal.html")
def nifty_page():
    return send_from_directory(HERE, "nifty_signal.html")


@app.route("/nifty_signal_data")
def nifty_data():
    from core import nifty_signal
    return jsonify(nifty_signal.read())


@app.route("/nifty_archive_data")
def nifty_archive_data():
    """Serve archived NIFTY trades (pre-cleanup) as reference/backtest history."""
    path = os.path.join(HERE, "archive", "nifty_trades_archived_20260724.json")
    if not os.path.exists(path):
        return jsonify({"ok": False, "error": "archive file not found"})
    try:
        with open(path) as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/nifty_chart_data")
def nifty_chart_data():
    """NIFTY candles + trade markers. ?tf=1d|1h|15m (default 1d). Intraday spreads trades out (less congested)."""
    from flask import request
    import datetime as _dt
    from core import nifty_signal
    tf = request.args.get("tf", "1d")
    cfg = {"1d": ("6mo", "1d"), "1h": ("3mo", "60m"), "15m": ("1mo", "15m")}.get(tf, ("6mo", "1d"))
    intraday = tf != "1d"

    def tstamp(s):  # "YYYY-MM-DD HH:MM" (UTC-naive) -> unix sec; daily -> date str
        s = str(s)
        if not intraday:
            return s[:10]
        try:
            return int(_dt.datetime.strptime(s[:16], "%Y-%m-%d %H:%M").replace(tzinfo=_dt.timezone.utc).timestamp())
        except Exception:
            try:
                return int(_dt.datetime.strptime(s[:10], "%Y-%m-%d").replace(tzinfo=_dt.timezone.utc).timestamp())
            except Exception:
                return None

    bars = []
    try:
        import yfinance as yf
        df = yf.download("^NSEI", period=cfg[0], interval=cfg[1], auto_adjust=False, progress=False)
        if df is not None and not df.empty:
            cl = df["Close"].squeeze(); op = df["Open"].squeeze()
            hi = df["High"].squeeze(); lo = df["Low"].squeeze()
            for i, idx in enumerate(df.index):
                t = int(idx.timestamp()) if intraday else str(idx.date())
                bars.append({"time": t, "open": round(float(op.iloc[i]), 2), "high": round(float(hi.iloc[i]), 2),
                             "low": round(float(lo.iloc[i]), 2), "close": round(float(cl.iloc[i]), 2)})
    except Exception:
        pass

    state = nifty_signal.read()
    markers = []
    for t in state.get("closed_trades", []):
        long_ = t.get("dir") == "long"
        de, dx = tstamp(t.get("entry_time", "")), tstamp(t.get("exit_time", ""))
        if de is not None:
            markers.append({"time": de, "position": "belowBar" if long_ else "aboveBar",
                            "color": "#10b981" if long_ else "#f43f5e",
                            "shape": "arrowUp" if long_ else "arrowDown", "text": "Long" if long_ else "Short"})
        if dx is not None:   # exit = small P&L-colored dot, no text (declutter)
            markers.append({"time": dx, "position": "aboveBar" if long_ else "belowBar",
                            "color": "#10b981" if t.get("pnl_pct", 0) >= 0 else "#f43f5e",
                            "shape": "circle", "text": ""})
    pos = state.get("position")
    if pos:
        d = tstamp(pos.get("entry_time", ""))
        if d is not None:
            up = pos.get("dir") == "long"
            markers.append({"time": d, "position": "belowBar" if up else "aboveBar",
                            "color": "#4f46e5", "shape": "arrowUp" if up else "arrowDown",
                            "text": ("LONG open" if up else "SHORT open")})
    markers = [m for m in markers if m["time"] is not None]
    markers.sort(key=lambda m: (m["time"] if isinstance(m["time"], int) else m["time"]))
    return jsonify({"bars": bars, "markers": markers})


@app.route("/nifty_scan")
def nifty_scan():
    """Cron hits this every 15 min during market hours → advances the NIFTY paper engine."""
    try:
        from core import nifty_signal
        res = nifty_signal.scan(force=True)
        return jsonify({"ok": True, "updated": res is not None})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/healthz")
def healthz():
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
