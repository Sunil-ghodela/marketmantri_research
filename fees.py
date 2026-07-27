"""
fees.py — Indian segmented fee model (Zerodha 2026 approximation).

backtesting.py takes a `commission` parameter which is applied **per leg**
as a fraction of notional. Our real-world Indian costs have two components:

    1. A percentage of notional (STT + stamp + SEBI + exchange + GST)
    2. A flat ₹20 brokerage per order (except delivery which is ₹0)

We fold the flat brokerage into an effective percentage using the expected
stake size (MIN_STAKE). This means the fee model is accurate for realistic
stakes (≥ ₹50,000) but OVERESTIMATES fees for smaller stakes — which is
the safer direction for research (errs on the side of rejecting marginal
strategies that can't cover costs).

Zerodha's actual delivery equity charges break down roughly as:
    STT:                 0.1%  (buy + sell)
    Stamp duty:          0.015% (buy side only)
    Exchange txn:        0.00322%
    SEBI:                0.0001%
    GST (18%):           18% of (brokerage + txn + SEBI)
    Brokerage:           0% for delivery, ₹20 flat for intraday/F&O

Round-trip fractions here are deliberately slightly pessimistic to leave
room for slippage not otherwise modelled.
"""

from __future__ import annotations

# Minimum realistic stake per trade so ₹20 brokerage doesn't dominate
MIN_STAKE_INR = 50_000

SEGMENTS = {
    "delivery": {
        "round_trip_pct": 0.00111,      # ~0.111% — STT dominates
        "flat_brokerage_inr": 0,
    },
    "intraday": {
        "round_trip_pct": 0.000225,     # ~0.0225% — much lower STT on intraday
        "flat_brokerage_inr": 20,
    },
    "futures": {
        "round_trip_pct": 0.00018,      # ~0.018%
        "flat_brokerage_inr": 20,
    },
    "options": {
        "round_trip_pct": 0.00098,      # ~0.098% — STT on options premium is 0.1% sell side
        "flat_brokerage_inr": 20,
    },
}


def per_leg_commission(segment: str, stake_inr: float = MIN_STAKE_INR) -> float:
    """
    Compute an equivalent per-leg commission percentage that folds in the
    flat ₹20 brokerage over the given stake.

    backtesting.py applies commission on each leg (entry and exit) as a
    fraction of the notional, so we return half the round-trip percentage
    plus (flat / stake).
    """
    if segment not in SEGMENTS:
        raise ValueError(f"Unknown segment {segment!r}. Choose from {list(SEGMENTS)}")
    seg = SEGMENTS[segment]
    pct_leg = seg["round_trip_pct"] / 2.0
    flat_leg = seg["flat_brokerage_inr"] / max(stake_inr, 1)
    return pct_leg + flat_leg


def describe(segment: str, stake_inr: float = MIN_STAKE_INR) -> str:
    leg = per_leg_commission(segment, stake_inr)
    rt = leg * 2
    return (
        f"segment={segment!r}  stake=₹{stake_inr:,.0f}  "
        f"per_leg={leg*100:.4f}%  round_trip={rt*100:.4f}%  "
        f"(= ₹{rt * stake_inr:,.2f} on a ₹{stake_inr:,.0f} trade)"
    )


if __name__ == "__main__":
    for seg in SEGMENTS:
        print(describe(seg))
    print()
    print("Stake sensitivity (intraday):")
    for stake in [10_000, 25_000, 50_000, 100_000, 500_000]:
        print("  " + describe("intraday", stake))
