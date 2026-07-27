from core.multi_tf_macd import macd_state, TF_ORDER


def test_macd_state_uptrend_is_green():
    closes = [100 + i for i in range(60)]          # steadily rising
    r = macd_state(closes)
    assert r["state"] == "green"
    assert r["hist"] > 0


def test_macd_state_downtrend_is_red():
    closes = [200 - i for i in range(60)]           # steadily falling
    r = macd_state(closes)
    assert r["state"] == "red"
    assert r["hist"] < 0


def test_macd_state_insufficient_is_na():
    r = macd_state([100, 101, 102])
    assert r["state"] == "na"


def test_tf_order_is_nine_swing_to_intraday():
    assert TF_ORDER == ["Monthly", "Weekly", "Daily", "3h", "2h", "1h", "45m", "30m", "15m"]
