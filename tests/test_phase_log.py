from core import phase_log


def _tf(tf, state):
    return {"tf": tf, "state": state, "hist": 0.0, "hist_slope": 0.0, "cross": "none"}


NINE = ["Monthly", "Weekly", "Daily", "3h", "2h", "1h", "45m", "30m", "15m"]


def _states(default="green", **over):
    return [_tf(t, over.get(t, default)) for t in NINE]


def test_first_update_records_and_sets_since(tmp_path, monkeypatch):
    monkeypatch.setattr(phase_log, "_FILE", str(tmp_path / "p.json"))
    r = phase_log.update("CLEAR-UP", _states("green"), now="2026-06-16 10:00")
    assert r["since"] == "2026-06-16 10:00"
    assert r["prev_phase"] is None


def test_same_phase_keeps_since(tmp_path, monkeypatch):
    monkeypatch.setattr(phase_log, "_FILE", str(tmp_path / "p.json"))
    phase_log.update("CLEAR-UP", _states("green"), now="2026-06-16 10:00")
    r = phase_log.update("CLEAR-UP", _states("green"), now="2026-06-16 11:00")
    assert r["since"] == "2026-06-16 10:00"   # unchanged
    assert r["prev_phase"] is None


def test_phase_change_updates_since_and_prev(tmp_path, monkeypatch):
    monkeypatch.setattr(phase_log, "_FILE", str(tmp_path / "p.json"))
    phase_log.update("CLEAR-UP", _states("green"), now="2026-06-16 10:00")
    r = phase_log.update("CONFUSED", _states("green", **{"15m": "red", "30m": "red", "45m": "red"}),
                         now="2026-06-16 12:00")
    assert r["since"] == "2026-06-16 12:00"
    assert r["prev_phase"] == "CLEAR-UP"


def test_recent_flip_count_counts_tf_changes_in_window(tmp_path, monkeypatch):
    monkeypatch.setattr(phase_log, "_FILE", str(tmp_path / "p.json"))
    phase_log.update("CLEAR-UP", _states("green"), now="2026-06-16 10:00")
    phase_log.update("CONFUSED", _states("green", **{"15m": "red"}), now="2026-06-16 11:00")
    phase_log.update("CONFUSED", _states("green", **{"15m": "green", "30m": "red"}), now="2026-06-16 11:30")
    churn = phase_log.recent_flip_count(window_hours=3, now="2026-06-16 12:00")
    assert churn >= 2


def test_corrupt_file_recovers(tmp_path, monkeypatch):
    f = tmp_path / "p.json"
    f.write_text("{not json")
    monkeypatch.setattr(phase_log, "_FILE", str(f))
    r = phase_log.update("CALM", _states("green"), now="2026-06-16 10:00")
    assert r["since"] == "2026-06-16 10:00"
