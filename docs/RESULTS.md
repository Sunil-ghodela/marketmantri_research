# RESULTS.md — the canonical numbers ledger

Every Sharpe/statistic this project has ever quoted, with **what it measures,
when it was produced, and where it lives** — so no number is ever quoted out
of context again. If a number isn't in this table, don't cite it.

Last updated: **28 Jul 2026** — two further self-caught corrections landed today:
the live divergence filter was found to have never run (#9), and the forward
paper record was found partly corrupted by an exit-recording regression and has
been archived and restarted (#8). See also #2's scope note.

| # | Number | What it measures | Produced | Artifact | Status |
|---|---|---|---|---|---|
| 1 | ~~Sharpe 6.08~~ | Flagship basket portfolio — **with a look-ahead bug** (backtest peeked one bar ahead) | Jul 2026 (W3) | `docs/PROJECT_STATUS.md` (timeline) | ❌ **INVALID — superseded by #2.** Kept only as the integrity story |
| 2 | **Sharpe 2.998** | Basket-100 portfolio (46 tradeable of 110) after the look-ahead fix, net of fees. **Scope note added 2026-07-28:** this is an *unconstrained* equal-weight average of all 46 names' trades — no concurrency cap. The live engine caps at **K=15** open positions and the cap binds (the backtest implies ~20–25 concurrent). So 2.998 is valid for what it measures but was previously described as "the REAL deployable number — live trading will match this", which is wrong. See #10 for the K-capped figure | 2026-07 (W3, restated everywhere same week); scoped 2026-07-28 | `docs/PROJECT_STATUS.md` · `_lookahead_compare.py` · `lookahead_compare.csv` (2026-06-18) | ⚠️ valid **portfolio** backtest, **not** the live configuration |
| 3 | **Sharpe 2.31** · 918 trades · 58.3% WR · PF 2.37 — ~~3.84~~ **restated 2026-07-27**: original used √252 on per-trade returns (~92 trades/yr actual); correct scaling is √(trades/yr). Only the annualization changed | 10-year NIFTY **divergence study** (2016-07-25 → 2026-07-21, 61,552 15m bars). A separate research study, not the live basket | 2026-07-22, restated 2026-07-27 | `nifty_10yr_combined_results.json` (`sharpe_method` note + year-by-year) | ✅ backtest, standalone study |
| 4 | Sharpe 1.87 net (2.18 gross) | Momentum basket portfolio, V12-off configuration, fee drag 0.31 | 2026-06-15 | `v12_comparison_results.json` | ✅ net-of-fees portfolio backtest |
| 5 | Median per-stock Sharpe ≈ 1.9 (range 1.71–2.37) | Momentum strategy generalization across the stock universe, per-stock, net | 2026-06-17 | `docs/research/momentum_v1_multistock_FINDINGS.md` | ✅ backtest, robustness evidence |
| 6 | Sharpe 2.49 (variants A–C) | 10-yr 1H MACD standalone variant study | 2026-06-14 | `standalone_macd_div_10yr_results.csv` | ✅ backtest, variant exploration |
| 7 | lag-0 1.94 vs lag-5 1.40 | Look-ahead sensitivity check (same strategy, execution lag applied) | 2026-06-18 | `lookahead_compare.csv` | ✅ methodology artifact |
| 8 | ~~Day 36 — −4.7% of pool · 33% WR · 211 trades~~ → **restated 2026-07-28: 203 trades · 31.0% WR · −₹25,997 (−5.20% of the ₹5L pool)** for the clean window **22 Jun – 22 Jul** | Live paper momentum basket (90-stock, K=15, ₹5L paper pool, VPS, cron) — the **money-gate** record | snapshot 2026-07-27, restated 2026-07-28 | archived: `archive/basket_forward_20260622_20260722.json` · `docs/paper_trading/momentum_basket_LIVE_record.md` | ⚠️ **archived, not deleted.** The 211-trade figure included 8 trades produced *after* an exit-recording regression (22 Jul) that also destroyed 62 positions with no trade written — so the count was incomplete and the P&L understated. Worse, this window never tested the documented strategy at all (see #9). Record **restarted 2026-07-28** on the fixed engine |
| 9 | **Divergence filter: 0 of 2047 evaluations active** (11 Jun → 28 Jul) | Whether the live engines were actually running the V2 bearish-divergence filter that the strategy — and #2 — depend on | discovered + fixed 2026-07-28 | fix commit `11d6e99` (private repo) · measurement over 89 stocks × 23 bars, 23–28 Jul | ❌ **the filter never ran live.** Both engines passed the detector a `RangeIndex` frame while it formats `df.index[...]` with `.strftime()`; every call raised `AttributeError` and a blanket `except` returned `"none"`. After the fix: 30.8% bearish / 20.8% bullish, and **25 of 77 cross-ups (32.5%) blocked**. Counterfactual on the archived record: Σ pnl_pct −78.0% → −36.7%, WR 31.0% → 38.9% — i.e. the missing filter explains **about half** the forward loss, not all of it |

| 10 | **K-concurrency sweep: the K=15 cap is roughly Sharpe-neutral** — fill 95.0% at K=15; Sharpe K=46: 3.456 · K=15: 3.498 · K=5: 3.290 (CAGR/DD scale with 1/K leverage: 16.8%→56.0%→109.5%) | Chronological walk over all 20,480 candidate trades (2016–2026) with a hard concurrency cap, ties in `WATCH` order, one position per stock, portfolio-level loss-cluster sizing | 2026-07-28 | `basket_k15_results.json` · `basket_k15_report.md` | ⚠️ **shape result only — the 3.5 LEVEL is not comparable to #2 and is not a new headline.** This run differs from #2 in three ways: 2x/2.5x/3x portfolio-level sizing (5,790 of 19,460 trades sized; #2 capped at per-stock 2x), a 58-name universe incl. 18 short-history names past the 10-trade floor on ~2 months of data, and 1/K-weight daily returns on a business-day grid. Reconciliation on identical universe/sizing/construction is open. **Also restated:** an earlier estimate that K=15 would cost ~28% of Sharpe (random 15-NAME subsets) answered the wrong question — live has 90 names and 15 SLOTS — and is withdrawn. What survives: the cap costs opportunity, not risk-adjusted return, so the K=15 cap is NOT the explanation for the live gap; the dead divergence filter (#9) and parameter mismatches remain the candidates |

## How to read this honestly

- **Backtest ≠ live.** Rows 2–7 are backtests; row 8 is the only forward
  evidence and it is currently *in drawdown, within tested bounds*. The
  project's own rule: no capital until the forward record proves the edge.
- **Four self-caught corrections now:** the look-ahead fix (#1→#2), the
  annualization fix (#3, 3.84→2.31), the dead divergence filter (#9), and the
  exit-recording regression that corrupted part of the forward record (#8).
  All four were found in-house, restated here, and documented — that is the
  project's core discipline. #9 is the most uncomfortable of them: it means the
  live engine spent seven weeks running a *different* strategy from the one that
  was backtested, so the archived forward record is not a test of #2.
- **Scope discipline (new, from #2's note):** a portfolio Sharpe is only
  comparable to a live record if the portfolio constraints match. 2.998 averages
  46 names with no concurrency cap; the live engine runs 15 slots. Row #10 is the
  apples-to-apples number.
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
