"""phase_log.py — timestamped append-on-change log for the market phase panel.

Records a snapshot only when the phase OR any TF MACD state flips. Provides
since/prev-phase for the current phase and a recent flip-count for churn.
State persists to phase_log.json (git-ignored, like momentum_paper_trades.json).
'now' is passed in (ISO 'YYYY-MM-DD HH:MM') so the logic stays deterministic/testable.
"""
from __future__ import annotations

import datetime
import json
import os
import threading

_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "phase_log.json")
_LOCK = threading.Lock()
MAX_ENTRIES = 500


def _blank() -> dict:
    return {"current": None, "entries": []}


def _load() -> dict:
    try:
        with open(_FILE) as f:
            d = json.load(f)
        d.setdefault("current", None)
        d.setdefault("entries", [])
        return d
    except Exception:
        return _blank()


def _save(d: dict) -> None:
    try:
        with open(_FILE, "w") as f:
            json.dump(d, f, indent=2)
    except Exception:
        pass


def _tf_map(states: list[dict]) -> dict:
    return {t["tf"]: t.get("state") for t in states}


def update(phase: str, tf_states: list[dict], now: str) -> dict:
    """Record on change. Returns {since, prev_phase, tf_changes}."""
    with _LOCK:
        d = _load()
        cur = d.get("current")
        tf_now = _tf_map(tf_states)
        tf_changes = {}

        if cur is None:
            since, prev_phase = now, None
            d["entries"].append({"t": now, "phase": phase, "kind": "init"})
        else:
            prev_phase = cur["phase"] if cur["phase"] != phase else cur.get("prev_phase")
            since = now if cur["phase"] != phase else cur["since"]
            # detect per-TF flips vs last snapshot
            for tf, st in tf_now.items():
                prev_st = cur.get("tf", {}).get(tf)
                if prev_st in ("green", "red") and st in ("green", "red") and prev_st != st:
                    arrow = "🔴→🟢" if st == "green" else "🟢→🔴"
                    tf_changes[tf] = f"{arrow} {now[-5:]}"
                    d["entries"].append({"t": now, "tf": tf, "flip": arrow})
            if cur["phase"] != phase:
                d["entries"].append({"t": now, "phase": phase, "prev": cur["phase"], "kind": "phase"})

        d["current"] = {"phase": phase, "since": since, "prev_phase": prev_phase, "tf": tf_now}
        d["entries"] = d["entries"][-MAX_ENTRIES:]
        _save(d)
        return {"since": since, "prev_phase": prev_phase, "tf_changes": tf_changes}


def _parse(t: str) -> datetime.datetime:
    return datetime.datetime.strptime(t, "%Y-%m-%d %H:%M")


def recent_flip_count(window_hours: int, now: str) -> int:
    d = _load()
    try:
        cutoff = _parse(now) - datetime.timedelta(hours=window_hours)
    except Exception:
        return 0
    n = 0
    for e in d.get("entries", []):
        if "flip" not in e:
            continue
        try:
            if _parse(e["t"]) >= cutoff:
                n += 1
        except Exception:
            continue
    return n


def recent_entries(limit: int = 8) -> list[dict]:
    return _load().get("entries", [])[-limit:]
