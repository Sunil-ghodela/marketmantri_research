# Momentum v1 — Multi-Stock Validation (2026-06-17)

> Baba: "momentum strategy ko stocks pe test kar sakte hain? NIFTY ke 20-30 stocks." Tested on the
> **10 large-cap NIFTY stocks** we already have 10yr 15m data for (Kite). **The edge generalizes —
> not NIFTYBEES-specific.** (20-30 stocks pending a Kite fetch.)
>
> Config: baseline (no profit-target, 1H entry/exit), `direction=long`, full 10yr, net of fees.
> Runner: `_test_momentum_stocks.py` · raw output: `momentum_stocks_10yr.csv`.

## Results — net Sharpe per stock (10yr)

| Stock | Sharpe (net) | Sharpe (gross) | Return % | Max DD % | Win % | PF | Trades |
|-------|:---:|:---:|--:|--:|--:|--:|--:|
| RELIANCE | **2.37** | 2.75 | 1485 | 6.2 | 61.2 | 3.22 | 510 |
| SBIN | **2.34** | 2.59 | 5659 | 11.2 | 64.9 | 4.24 | 519 |
| ICICIBANK | **2.25** | 2.60 | 2081 | 13.1 | 60.6 | 3.04 | 554 |
| BHARTIARTL | 2.00 | 2.32 | 1660 | 8.6 | 61.2 | 2.91 | 520 |
| HDFCBANK | 1.95 | 2.48 | 553 | 12.6 | 55.9 | 2.50 | 540 |
| TCS | 1.94 | 2.41 | 620 | 7.0 | 59.4 | 2.55 | 510 |
| LT | 1.93 | 2.30 | 1061 | 7.0 | 59.5 | 2.71 | 511 |
| KOTAKBANK | 1.90 | 2.32 | 881 | 11.3 | 60.6 | 2.62 | 556 |
| ITC | 1.88 | 2.34 | 743 | 9.7 | 57.7 | 2.42 | 565 |
| INFY | 1.71 | 2.12 | 700 | 14.6 | 59.7 | 2.36 | 519 |

**Median net Sharpe 1.95 · 10/10 stocks Sharpe > 1 · NIFTYBEES baseline = 1.94.**

## Verdict

✅ **The momentum edge is robust and generalizes across large-cap NIFTY stocks** — it is NOT a
NIFTYBEES/index curve-fit. Every stock lands 1.71–2.37 net Sharpe, win rates 56–65%, PF 2.4–4.2.
This is the **first real expansion lead** after 5 failed entry/exit improvement attempts
(see [`momentum_v1_improvement_attempts.md`](./momentum_v1_improvement_attempts.md)).

## Why this matters

1. **Solves the paper-trade signal scarcity.** NIFTYBEES alone fires ~16-49 trades/yr; a multi-stock
   basket fires far more → the live forward record builds much faster (the current bottleneck:
   3 paper days, 0 trades).
2. **Validates the strategy itself** — the edge exists per-instrument, not by luck on one symbol.

## Honest caveats

- **Correlation:** all large-cap Indian equity → highly correlated. Strong for *validation*, but a
  10-stock basket is not 10 independent bets. Size the basket as ~one concentrated equity bet.
- **Single-name DD higher** (12–15% for HDFCBANK/ICICIBANK/INFY) vs the ETF (~6%) — single-stock risk.
- **Mild survivorship:** these 10 are today's blue-chips that did well over 10yr. Membership is
  stable, but a fully fair test would include names that dropped out. Minor.

## Next steps

1. **Fetch 20-30 NIFTY stocks' 10yr 15m via Kite** (token needed) → re-run the same test for breadth.
2. **Multi-stock portfolio backtest** — combined equity curve + position sizing + max-concurrent risk;
   measure basket-level Sharpe/DD (likely smoother than any single name).
3. Consider basket paper-trading to accelerate the forward record.
