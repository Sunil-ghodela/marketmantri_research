# RESULTS.md — the canonical numbers ledger

Every Sharpe/statistic this project has ever quoted, with **what it measures,
when it was produced, and where it lives** — so no number is ever quoted out
of context again. If a number isn't in this table, don't cite it.

Last updated: **27 Jul 2026** (incl. the Sharpe-annualization restatement).

| # | Number | What it measures | Produced | Artifact | Status |
|---|---|---|---|---|---|
| 1 | ~~Sharpe 6.08~~ | Flagship basket portfolio — **with a look-ahead bug** (backtest peeked one bar ahead) | Jul 2026 (W3) | `docs/PROJECT_STATUS.md` (timeline) | ❌ **INVALID — superseded by #2.** Kept only as the integrity story |
| 2 | **Sharpe 2.998** | Basket-100 portfolio (46 tradeable of 110) after the look-ahead fix, net of fees | 2026-07 (W3, restated everywhere same week) | `docs/PROJECT_STATUS.md` · `_lookahead_compare.py` · `lookahead_compare.csv` (2026-06-18) | ✅ current honest **portfolio** backtest |
| 3 | **Sharpe 2.31** · 918 trades · 58.3% WR · PF 2.37 — ~~3.84~~ **restated 2026-07-27**: original used √252 on per-trade returns (~92 trades/yr actual); correct scaling is √(trades/yr). Only the annualization changed | 10-year NIFTY **divergence study** (2016-07-25 → 2026-07-21, 61,552 15m bars). A separate research study, not the live basket | 2026-07-22, restated 2026-07-27 | `nifty_10yr_combined_results.json` (`sharpe_method` note + year-by-year) | ✅ backtest, standalone study |
| 4 | Sharpe 1.87 net (2.18 gross) | Momentum basket portfolio, V12-off configuration, fee drag 0.31 | 2026-06-15 | `v12_comparison_results.json` | ✅ net-of-fees portfolio backtest |
| 5 | Median per-stock Sharpe ≈ 1.9 (range 1.71–2.37) | Momentum strategy generalization across the stock universe, per-stock, net | 2026-06-17 | `docs/research/momentum_v1_multistock_FINDINGS.md` | ✅ backtest, robustness evidence |
| 6 | Sharpe 2.49 (variants A–C) | 10-yr 1H MACD standalone variant study | 2026-06-14 | `standalone_macd_div_10yr_results.csv` | ✅ backtest, variant exploration |
| 7 | lag-0 1.94 vs lag-5 1.40 | Look-ahead sensitivity check (same strategy, execution lag applied) | 2026-06-18 | `lookahead_compare.csv` | ✅ methodology artifact |
| 8 | **Forward paper: Day 36 — P&L −4.7% of pool · 33% WR · 211 trades** | Live paper momentum basket (90-stock, K=15, ₹5L paper pool, VPS, cron) — the **money-gate** record | snapshot 2026-07-27 | live dashboard · `docs/paper_trading/momentum_basket_LIVE_record.md` | ⏳ **running — edge NOT yet confirmed forward.** Backtest max-DD expectation ~5.1% (#4); currently at its edge. This is exactly why no real capital is deployed |

## How to read this honestly

- **Backtest ≠ live.** Rows 2–7 are backtests; row 8 is the only forward
  evidence and it is currently *in drawdown, within tested bounds*. The
  project's own rule: no capital until the forward record proves the edge.
- **Two self-caught restatements now:** the look-ahead fix (#1→#2) and the
  annualization fix (#3, 3.84→2.31). Both were found in-house, restated
  everywhere, and documented — that is the project's core discipline.
- **#1 → #2 is the most important row pair.** A self-caught look-ahead bug,
  a public restatement, and a permanent regression check — that is the
  project's strongest credibility artifact.
- The NIFTY options paper-track (CE/PE) was **reset on 2026-07-24** after
  early-period instability (divergence tuning + the look-ahead fix); its
  pre-reset trades are archived as reference, not performance. Its fresh
  record starts 24 Jul 2026.
- Numbers were verified against artifacts on 2026-07-26 (framework audit,
  `docs/AUDIT-2026-07-26.md`) and re-verified 2026-07-27 while assembling
  this public snapshot.
