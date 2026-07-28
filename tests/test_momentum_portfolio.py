"""Tests for the momentum portfolio paper engine (core/momentum_portfolio.py).

Engine core is pure logic: given per-stock signals + prices, it manages up to K=15 paper
positions out of a 56-stock watchlist, 1/K sizing on a Rs5L pool, and persists state.
Signal computation / live data is a separate layer — these tests inject signals directly.
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import importlib
import core.momentum_portfolio as mp


def _fresh(tmp_path):
    """Point the engine at a temp state file and reset."""
    mp._FILE = os.path.join(tmp_path, "state.json")
    if os.path.exists(mp._FILE):
        os.remove(mp._FILE)


def sig(cross="none", bar="2026-06-22 10:15", div="none"):
    return {"cross": cross, "bar_time_ist": bar, "div_state": div}


def test_open_on_cross_up(tmp_path):
    _fresh(tmp_path)
    v = mp.scan_and_update({"SBIN": sig("up")}, {"SBIN": 100.0})
    assert "SBIN" in {p["stock"] for p in v["open"]}
    assert v["kpi"]["open_count"] == 1


def test_skip_when_bearish_div(tmp_path):
    _fresh(tmp_path)
    v = mp.scan_and_update({"SBIN": sig("up", div="bearish")}, {"SBIN": 100.0})
    assert v["kpi"]["open_count"] == 0


def test_k_cap_never_exceeds_15(tmp_path):
    _fresh(tmp_path)
    # 20 stocks all fire cross-up on the same bar
    sigs = {f"S{i}": sig("up") for i in range(20)}
    ltp = {f"S{i}": 100.0 for i in range(20)}
    v = mp.scan_and_update(sigs, ltp)
    assert v["kpi"]["open_count"] == 15          # capped
    assert len(v["signal_scan"]) == 5            # 5 skipped (no slot)


def test_sizing_is_pool_over_k(tmp_path):
    _fresh(tmp_path)
    mp.scan_and_update({"SBIN": sig("up")}, {"SBIN": 100.0})
    d = mp._load()
    assert abs(d["open"]["SBIN"]["notional"] - mp.POOL_INR / mp.K) < 1.0


def test_close_on_stop_loss_with_pnl(tmp_path):
    _fresh(tmp_path)
    mp.scan_and_update({"SBIN": sig("up", bar="b1")}, {"SBIN": 100.0})
    # price drops 3% -> below 2% stop, checked every call (no new bar needed)
    v = mp.scan_and_update({"SBIN": sig("none", bar="b1")}, {"SBIN": 97.0})
    assert v["kpi"]["open_count"] == 0
    t = v["trades"][0]
    assert t["exit_reason"] == "Stop Loss"
    assert t["pnl_pct"] < 0
    # 1/K notional ~33,333; -3% -> ~ -1000
    assert abs(t["pnl_abs"] - (mp.POOL_INR / mp.K) * (-3.0) / 100) < 1.0


def test_close_on_macd_cross_down_new_bar(tmp_path):
    _fresh(tmp_path)
    mp.scan_and_update({"SBIN": sig("up", bar="b1")}, {"SBIN": 100.0})
    v = mp.scan_and_update({"SBIN": sig("down", bar="b2")}, {"SBIN": 105.0})
    assert v["kpi"]["open_count"] == 0
    assert v["trades"][0]["exit_reason"] == "MACD Cross"
    assert v["trades"][0]["pnl_pct"] > 0


def test_close_on_bearish_div_new_bar(tmp_path):
    """Bearish divergence must close the position AND record the trade.

    Regression: c7c3c45 over-indented the recording block into the max-hold branch,
    so this exit path silently stopped firing (0 'Bearish Div' exits in 211 live trades).
    """
    _fresh(tmp_path)
    mp.scan_and_update({"SBIN": sig("up", bar="b1")}, {"SBIN": 100.0})
    v = mp.scan_and_update({"SBIN": sig("none", bar="b2", div="bearish")}, {"SBIN": 103.0})
    assert v["kpi"]["open_count"] == 0
    assert v["trades"][0]["exit_reason"] == "Bearish Div"
    assert v["trades"][0]["pnl_pct"] > 0


def test_position_not_silently_deleted_without_exit(tmp_path):
    """A new bar with no exit condition must leave the position OPEN and log no trade.

    Regression: the `del d["open"][stock]` sat outside `if reason and px`, so every
    position was dropped on the next bar with no trade recorded (62 lost live, 23-28 Jul).
    """
    _fresh(tmp_path)
    mp.scan_and_update({"SBIN": sig("up", bar="b1")}, {"SBIN": 100.0})
    v = mp.scan_and_update({"SBIN": sig("none", bar="b2")}, {"SBIN": 101.0})
    assert v["kpi"]["open_count"] == 1, "position vanished without an exit signal"
    assert v["kpi"]["trades"] == 0, "trade recorded without an exit reason"


def test_bearish_div_entry_skip_is_logged(tmp_path):
    """Divergence-blocked entries must be visible in the scan log, not skipped silently."""
    _fresh(tmp_path)
    v = mp.scan_and_update({"SBIN": sig("up", div="bearish")}, {"SBIN": 100.0})
    assert v["kpi"]["open_count"] == 0
    assert any("divergence" in x.get("reason", "").lower() for x in v["signal_scan"]), \
        "bearish-div entry skip was not logged"


def test_idempotent_same_bar_no_double_open(tmp_path):
    _fresh(tmp_path)
    mp.scan_and_update({"SBIN": sig("up", bar="b1")}, {"SBIN": 100.0})
    # same bar repeated -> no new position, still exactly 1
    v = mp.scan_and_update({"SBIN": sig("up", bar="b1")}, {"SBIN": 101.0})
    assert v["kpi"]["open_count"] == 1


def test_freed_slot_allows_new_entry(tmp_path):
    _fresh(tmp_path)
    # fill 15 slots
    mp.scan_and_update({f"S{i}": sig("up", bar="b1") for i in range(15)},
                       {f"S{i}": 100.0 for i in range(15)})
    # one exits on stop, a new one fires next bar -> slot reused
    ltp = {f"S{i}": 100.0 for i in range(15)}
    ltp["S0"] = 97.0  # S0 stops out
    ltp["NEW"] = 100.0
    sigs = {f"S{i}": sig("none", bar="b2") for i in range(15)}
    sigs["NEW"] = sig("up", bar="b2")
    v = mp.scan_and_update(sigs, ltp)
    open_stocks = {p["stock"] for p in v["open"]}
    assert "S0" not in open_stocks
    assert "NEW" in open_stocks
    assert v["kpi"]["open_count"] == 15


def test_state_persists_round_trip(tmp_path):
    _fresh(tmp_path)
    mp.scan_and_update({"SBIN": sig("up", bar="b1")}, {"SBIN": 100.0})
    d = mp._load()
    assert "SBIN" in d["open"]
    assert d["started"]


def test_total_pnl_in_kpi(tmp_path):
    _fresh(tmp_path)
    mp.scan_and_update({"SBIN": sig("up", bar="b1")}, {"SBIN": 100.0})
    v = mp.scan_and_update({"SBIN": sig("down", bar="b2")}, {"SBIN": 110.0})  # +10%
    assert v["kpi"]["total_pnl"] > 0
    assert v["kpi"]["trades"] == 1


# ── feed: signal_1h smoke tests ──
def test_signal_1h_short_series_is_none():
    from core.momentum_portfolio_feed import signal_1h
    out = signal_1h([100.0] * 5, ["2026-06-22 09:15"] * 5)
    assert out["cross"] == "none"


def test_signal_1h_valid_on_long_series():
    from core.momentum_portfolio_feed import signal_1h
    import datetime
    n = 400
    base = datetime.datetime(2026, 5, 1, 9, 15)
    labels = [str(base + datetime.timedelta(minutes=15 * i)) for i in range(n)]
    closes = [100 + i * 0.05 for i in range(n)]   # gentle uptrend
    out = signal_1h(closes, labels)
    assert out["cross"] in ("up", "down", "none")
    assert out["bar_time_ist"] != ""
    assert out["state"] in ("green", "red")


# ── divergence detector must actually run, not fail into a permanent "none" ──
def test_div_state_detector_does_not_silently_fail():
    """The feed must hand the V2 detector a DatetimeIndex.

    Regression: the prep frame was built with a bare RangeIndex while the detector formats
    df.index[...] with .strftime(). Every call raised AttributeError, the blanket except
    turned it into "none", and divergence was dead in the live basket from 11 Jun to 28 Jul
    (measured: 2047/2047 stock-bar evaluations returned "none").
    """
    import io
    import contextlib
    import numpy as np
    import pandas as pd
    from core import momentum_portfolio_feed as FEED

    n = 400
    idx = pd.date_range("2026-06-01 09:15", periods=n, freq="15min", tz="Asia/Kolkata")
    # price grinds up while momentum fades -> the shape a bearish divergence is made of
    t = np.arange(n)
    close = 100 + t * 0.05 + 6 * np.sin(t / 11.0) * np.exp(-t / 900.0)
    df = pd.DataFrame({"Close": close, "High": close * 1.002, "Low": close * 0.998,
                       "Volume": np.full(n, 100000.0)}, index=idx)

    # capture the frame the feed hands the detector — this is the contract that broke
    seen = {}
    real = FEED.detect_divergences_v2

    def spy(frame, **kw):
        seen["index"] = frame.index
        return real(frame, **kw)

    FEED.detect_divergences_v2 = spy
    FEED._DIV_CACHE.clear()
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            state = FEED._compute_div_state(df)
    finally:
        FEED.detect_divergences_v2 = real

    assert isinstance(seen.get("index"), pd.DatetimeIndex), \
        "feed passed a %s — the detector needs timestamps for .strftime()" % type(seen.get("index")).__name__
    assert "detector failed" not in buf.getvalue(), \
        "detector raised and was swallowed: %s" % buf.getvalue().strip()
    assert state in ("bearish", "bullish", "none")


def test_div_prep_frame_carries_timestamps():
    """Guard the specific contract that broke: the detector needs .strftime()-able index."""
    import numpy as np
    import pandas as pd
    from divergence_detector_v2 import detect_divergences_v2

    n = 300
    idx = pd.date_range("2026-06-01", periods=n, freq="15min")
    t = np.arange(n)
    close = 100 + t * 0.04 + 5 * np.sin(t / 9.0)
    prep = pd.DataFrame({"close": close, "high": close * 1.002, "low": close * 0.998,
                         "volume": np.full(n, 1e5), "macd_hist": np.sin(t / 7.0)}, index=idx)
    # must not raise
    detect_divergences_v2(prep, oscillator_col="macd_hist", pivot_left=3, pivot_right=3,
                          min_prominence_pct=0.05, min_price_move_pct=0.12,
                          min_pivot_distance=5, zscore_threshold=1.5,
                          atr_resolution_mult=0.5, min_oscillator_move_pct=0.05,
                          confirmation_bars=2, confirmation_ratio=0.6,
                          include_hidden=True, use_volume_confirmation=False)


# ── decay gate: gated stock must not enter, and is logged ──
def test_gated_stock_skips_entry(tmp_path):
    _fresh(tmp_path)
    s = sig("up"); s["gated"] = True
    v = mp.scan_and_update({"SBIN": s}, {"SBIN": 100.0})
    assert v["kpi"]["open_count"] == 0
    assert any("decay gate" in x.get("reason", "") for x in v["signal_scan"])


def test_non_gated_stock_still_enters(tmp_path):
    _fresh(tmp_path)
    s = sig("up"); s["gated"] = False
    v = mp.scan_and_update({"SBIN": s}, {"SBIN": 100.0})
    assert v["kpi"]["open_count"] == 1
