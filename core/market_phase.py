"""market_phase.py — classify NIFTY into a market 'phase' from multi-TF MACD + ADX.

Read-only descriptive label (NOT a trade signal). See
docs/superpowers/specs/2026-06-16-market-phase-panel-design.md.
"""
from __future__ import annotations

# Tunable heuristics (not optimized parameters — descriptive thresholds)
ALIGN_PCT = 75.0     # >= this % of available TFs same color => "aligned"
ADX_TREND = 25.0     # >= => trending
ADX_CHOP = 20.0      # < => choppy/no-trend
CHURN_HIGH = 4       # >= flips in the recent window => whipsaw
MIN_TFS = 5          # fewer available TFs => UNKNOWN

SWING = {"Monthly", "Weekly", "Daily"}
INTRADAY = {"3h", "2h", "1h", "45m", "30m", "15m"}


def classify(tf_states: list[dict], adx: float, churn: int) -> dict:
    avail = [t for t in tf_states if t.get("state") in ("green", "red")]
    n = len(avail)
    na = len(tf_states) - n
    if n < MIN_TFS:
        return {"phase": "UNKNOWN", "direction": "none", "green": 0, "red": 0,
                "na": na, "total": len(tf_states), "alignment_pct": 0.0,
                "adx": round(adx, 1), "insight": "Warming up — not enough timeframe data yet."}

    green = sum(1 for t in avail if t["state"] == "green")
    red = n - green
    dominant = max(green, red)
    alignment_pct = round(100.0 * dominant / n, 1)

    # Resolution order: CLEAR -> CHOPPY -> CONFUSED -> CALM
    if alignment_pct >= ALIGN_PCT and adx >= ADX_TREND:
        phase, direction = ("CLEAR-UP", "up") if green >= red else ("CLEAR-DOWN", "down")
    elif adx < ADX_CHOP and churn >= CHURN_HIGH:
        phase, direction = "CHOPPY", "mixed"
    elif alignment_pct < ALIGN_PCT:
        phase, direction = "CONFUSED", "mixed"
    else:
        phase, direction = "CALM", ("up" if green >= red else "down")

    insight = _insight(phase, direction, avail, adx)
    return {"phase": phase, "direction": direction, "green": green, "red": red,
            "na": na, "total": len(tf_states), "alignment_pct": alignment_pct,
            "adx": round(adx, 1), "insight": insight}


def _net(states: list[dict], group: set[str]) -> int:
    """+ve => group leans green, -ve => leans red."""
    g = sum(1 for t in states if t["tf"] in group and t["state"] == "green")
    r = sum(1 for t in states if t["tf"] in group and t["state"] == "red")
    return g - r


def _insight(phase: str, direction: str, states: list[dict], adx: float) -> str:
    swing = _net(states, SWING)
    intra = _net(states, INTRADAY)
    if phase == "CLEAR-UP":
        return "All timeframes aligned UP with a real trend (ADX strong) — direction is clear."
    if phase == "CLEAR-DOWN":
        return "All timeframes aligned DOWN with a real trend — clear downtrend, don't fade."
    if phase == "CHOPPY":
        return "Low ADX + frequent flips — whipsaw/mara-mari. Edges are unreliable; stay light."
    if phase == "CALM":
        return "Aligned but quiet (weak ADX) — range-bound drift; wait for expansion."
    # CONFUSED
    if swing > 0 and intra < 0:
        return "Swing up, intraday cooling — early-bounce split. Watch lower TFs reclaim to re-align."
    if swing < 0 and intra > 0:
        return "Swing down, intraday bouncing — counter-trend pop inside a larger down-leg. Suspect."
    return "Timeframes disagree — no consensus direction. Let the split resolve before acting."
