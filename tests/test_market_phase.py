from core.market_phase import classify


def _tf(tf, state, hist=0.0, slope=0.0, cross="none"):
    return {"tf": tf, "state": state, "hist": hist, "hist_slope": slope, "cross": cross}


NINE = ["Monthly", "Weekly", "Daily", "3h", "2h", "1h", "45m", "30m", "15m"]


def _all(state):
    return [_tf(t, state) for t in NINE]


def test_all_green_high_adx_is_clear_up():
    r = classify(_all("green"), adx=35.0, churn=0)
    assert r["phase"] == "CLEAR-UP"
    assert r["direction"] == "up"
    assert r["alignment_pct"] == 100.0


def test_all_red_high_adx_is_clear_down():
    r = classify(_all("red"), adx=35.0, churn=0)
    assert r["phase"] == "CLEAR-DOWN"
    assert r["direction"] == "down"


def test_split_swing_up_intraday_down_is_confused():
    # 16-Jun shape: monthly red, weekly+daily green; intraday 3h+2h+1h green, 45m+30m+15m red => 5g/4r
    states = [_tf("Monthly", "red"), _tf("Weekly", "green"), _tf("Daily", "green"),
              _tf("3h", "green"), _tf("2h", "green"), _tf("1h", "green"),
              _tf("45m", "red"), _tf("30m", "red"), _tf("15m", "red")]
    r = classify(states, adx=25.6, churn=1)
    assert r["phase"] == "CONFUSED"
    assert r["green"] == 5 and r["red"] == 4


def test_low_adx_high_churn_is_choppy():
    states = [_tf(t, "green" if i % 2 == 0 else "red") for i, t in enumerate(NINE)]
    r = classify(states, adx=15.0, churn=5)
    assert r["phase"] == "CHOPPY"


def test_aligned_low_adx_low_churn_is_calm():
    # 8 green / 1 red (aligned) but ADX weak and no churn => CALM not CLEAR
    states = _all("green")
    states[0]["state"] = "red"
    r = classify(states, adx=18.0, churn=0)
    assert r["phase"] == "CALM"


def test_too_few_timeframes_is_unknown():
    states = [_tf("Daily", "green"), _tf("1h", "green"), _tf("15m", "na"),
              _tf("30m", "na"), _tf("45m", "na"), _tf("2h", "na"),
              _tf("3h", "na"), _tf("Weekly", "na"), _tf("Monthly", "na")]
    r = classify(states, adx=30.0, churn=0)
    assert r["phase"] == "UNKNOWN"


def test_insight_is_nonempty_string():
    r = classify(_all("green"), adx=35.0, churn=0)
    assert isinstance(r["insight"], str) and len(r["insight"]) > 0
