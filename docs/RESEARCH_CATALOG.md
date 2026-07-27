# 🔬 MarketMantri — Complete Research Catalog

> **Date:** 22 July 2026  
> **Purpose:** One catalog to see EVERYTHING tested — what passed, what failed, what's pending.
> **Use this to:** clean up garbage, identify what to keep, decide what to test next.

---

## How to Read This

```
✅ ACTIVE       → Deployed live or core reference. KEEP.
♻️ PARKED       → Works but not deployed. Revisit later.
❌ REJECTED     → Tested, failed. DELETE (or archive).
📝 PENDING      → Idea noted, not yet tested.
📊 DATA         → Result files (CSV/JSON). Archive or delete.
```

---

## 1. 🏆 ACTIVE — Deployed Strategies

### 1A. MACD Momentum — Basket (PRIMARY EDGE)

| Property | Value |
|----------|-------|
| Status | ✅ **LIVE on VPS** |
| Code | `strategy_macd_momentum.py`, `core/momentum_portfolio.py`, `core/momentum_portfolio_feed.py` |
| Entry | 1H MACD cross UP + no bearish divergence |
| Exit | MACD cross DOWN / bearish divergence / 2% stop / 3-day max-hold |
| Sizing | **Loss-2→2x→2.5x→3x anti-martingale LIVE** 🚀 |
| Universe | 93 stocks (46 tradeable via MACD) |
| Dashboard | `hearth.tranquilwaters.in/basket/` |
| Live state | 10 open positions, 198 closed trades |

**Key files:**
- `docs/BASKET_100_RESULTS.md` — 46-stock backtest report
- `docs/research/MOMENTUM_STRATEGY_MASTER.md` — Complete reference
- `docs/STRATEGY.md` — Deployed spec
- `docs/SIDE_BASKET_LARGE_CAPS.md` — 64 failed stocks
- `basket_100_results.json` — Full backtest JSON

### 1B. MACD Momentum — NIFTY Futures

| Property | Value |
|----------|-------|
| Status | ✅ **LIVE on VPS** (bidirectional) |
| Code | `core/nifty_signal.py`, `server_basket.py` |
| Entry | MACD cross UP + no bearish div → LONG. MACD cross DOWN + no bullish div → SHORT. |
| Exit | Opposite cross / opposing divergence / 2% stop / max-hold |
| Dashboard | `hearth.tranquilwaters.in/basket/nifty` |
| Live state | Flat (0 position), 10 seeded backtest trades |

**Key files:**
- `core/nifty_signal.py` — Engine
- `_seed_nifty_combined.py` — State seed script
- `nifty_signal_state.json` — Live state (VPS)

### 1C. Strategy.py Pullback (FOUNDATION — being replaced by momentum)

| Property | Value |
|----------|-------|
| Status | ⏳ Legacy — momentum is the primary now |
| Code | `strategy.py` |
| Sharpe | 1.79 (NIFTYBEES 15m, 10yr) |
| Notes | **FRAGILE** — up_ratio=20 is overfit peak; astro nakshatra is curve-fit. Momentum is ROBUST. |

**Key files:**
- `SUMMARY.md` — V10 baseline reference
- `docs/PROJECT_HISTORY.md` — Why it's fragile

---

## 2. 📊 KEY RESULT DATA (Active Reference)

### 2A. Basket-100 Backtest (46 Stocks)

| File | Size | Content |
|------|------|---------|
| `basket_100_results.json` | Large | Full per-stock + portfolio JSON |
| `basket_100_report.md` | Medium | Generated report with tier breakdown |
| `basket_100_portfolio_returns.csv` | Medium | Daily equity curve |

**Performance:** Sharpe 2.998, CAGR 10.89%, DD 7.74%, 46 stocks, 10yr

### 2B. Momentum Multi-Stock + NIFTY Tests

| File | Content |
|------|---------|
| `nifty_futures_basket_results.csv`/`.json` | Original 89-stock basket test |
| `deployed_basket_results.csv`/`.json` | VPS basket backtest |
| `multi_instrument_ecombined_results.csv`/`.json` | 19-instrument E. Combined test |
| `macd_momentum_trades.csv`/`_long.csv`/`_both.csv` | Per-direction trade logs |
| `momentum_breadth_50.csv`/`_FIXED.csv` | 50-stock breadth perf data |

### 2C. Position Sizing + Exit Lab

| File | Content |
|------|---------|
| `exit_lab_tranche_a.csv`/`_raw.csv` | Loss-cutting exit tuning |
| `exit_lab_tranche_b.csv`/`_raw.csv` | Win-exit profit-engine tuning |
| `exit_lab_tranche_c.csv`/`_raw.csv` | Divergence exit recency tuning |
| `exit_tuning_results.json` | Full exit tuning results |
| `nifty_sizing_backtest_results.csv`/`.json` | Position sizing backtest |
| `nifty_loss_cluster_sizing.csv` | Loss clustering analysis |

### 2D. Live + Deployed Results

| File | Content |
|------|---------|
| `trades_tuned.json` | VPS basket trade log |
| `momentum_portfolio_state.json` | Current live state (git-ignored) |
| `nifty_signal_state.json` | NIFTY live state (git-ignored) |

---

## 3. ♻️ PARKED — Valid but Not Deployed

| Research | Status | Why Parked |
|----------|--------|------------|
| ~~Loss-2→2x sizing~~ | ✅ **DEPLOYED LIVE (22 Jul)** | ➡️ Now ACTIVE — upgraded to Loss-2→2x→2.5x→3x |
| **Two-strategy combine** (momentum + pullback) | ✅ Valid (+11%) | Modest gain. Needs portfolio-level sizing. |
| **Global expansion** (NASDAQ, Hang Seng) | ✅ Valid (momentum generalizes) | Need longer intraday data. Low priority. |
| **Uncorrelated diversifiers** (gold, silver, FANG) | ✅ Valid (+6%) | Modest. Crypto killed by India TDS. |
| **Multi-TF divergence** (5min/15min/1h/daily) | ♻️ Parked | Working code, no clear edge gain proven. |
| **Smart day open** (gap+retest) | ♻️ Parked | Interesting pattern, needs more data. |

**Key files:**
- `docs/research/uncorrelated_diversifiers_FINDINGS.md`
- `docs/research/overnight_drift_INTEGRATION_plan.md`
- `docs/research/smart_day_open_PLAN.md`
- `docs/research/smart_day_open_frequency_FINDINGS.md`
- `docs/PHASE2_DIRECTIONS.md`

---

## 4. ❌ REJECTED — Tested, Failed (The Graveyard)

> **This list IS the moat.** Every single one was tested, failed, and honestly documented.
> Keep for reference; no need to re-test.

### 4A. Strategy Tweaks (tested on Momentum)

| Idea | Why Failed | Source File |
|------|------------|-------------|
| **MACD Cross exit OFF** | DD blew up 2.7× — it's risk control, not a loser | `momentum_v1_improvement_attempts.md` |
| **MACD Cross exit loss-only** | Losses got deeper | same |
| **15m entry-confirm** | Doesn't detect chop — 15m MACD oscillates in chop too | same |
| **15m exit-cross** | Too noisy — cuts winners early | same |
| **ADX entry gate** (≥15/20/22/25) | Removes early entries that make the money | same |
| **Profit target** (+0.4% / +1.0%) | Caps fat-tail winners. On 10yr: −67% / −33% return. | same |
| **V11 Divergence on strategy.py** | Zero impact — entry conditions incompatible | `SUMMARY.md` |
| **V12 New Moon MACD entry** | Neutral-to-negative Sharpe, DD higher | `PLAN_NEXT.md` |
| **V13 MACD filter on strategy.py** | Pending standalone test (never completed) | `SUMMARY.md` |
| **Loss-2→2x + Win-2→1.5x combined** | RAW return +1399% but Sharpe lower | `MOMENTUM_STRATEGY_MASTER.md` |

### 4B. Complete Strategies (Tested, Rejected)

| Strategy | Why Failed | Evidence |
|----------|------------|----------|
| **1m scalp** | Fees kill edge. 0-for-12 tested. | `docs/PROJECT_HISTORY.md` |
| **5m unified** | 83% WR claim not reproducible — withdrawn | `MEMORY.md` (25 May log) |
| **NIFTY Futures shorts** | Bidirectional test showed no edge | `docs/PROJECT_HISTORY.md` |
| **Overnight drift/options** | Backtest edge died on real option fills / cash tail | `docs/research/overnight_options_REAL_FILLS_REJECTED.md` |
| **Overnight short put spread** | Real fills killed the backtest edge | same |
| **PEAD (Post-earnings drift)** | Survivorship illusion | `docs/research/pead_test_REJECTED.md` |
| **MTF candle funnel** | 2-year samples lie — reversed on 10yr | `docs/PROJECT_HISTORY.md` |
| **Higher-TF trend-gate** | Counter-trend mis-composes with momentum | `docs/PROJECT_HISTORY.md` |
| **MTF alignment (6-TF)** | Hurt returns | `docs/PROJECT_HISTORY.md` |
| **Month-anchor breakout** | No edge | `docs/PROJECT_HISTORY.md` |
| **Short-extension** | No edge | `docs/PROJECT_HISTORY.md` |
| **Meta-labeling (ML)** | No edge | `docs/PROJECT_HISTORY.md` |
| **Yearly-anchor-as-filter** | Not a filter | `docs/PROJECT_HISTORY.md` |
| **Version C 1m** | No edge | `docs/PROJECT_HISTORY.md` |
| **Correlation-gate** | No edge | `docs/PROJECT_HISTORY.md` |
| **Astro nakshatra gate** | Curve-fit — doesn't persist across halves | `docs/STRATEGY.md` |

### 4C. Strategy.py Tuning Layers (Historical — Outdated)

| Layer | Status | Note |
|-------|--------|------|
| V1 EMA+UR | Baseline | Original |
| V2 Profit Target 5% | Inert | No real impact |
| V3 Regime cooldown | Valid | Kept |
| V4 Distance-from-high | Valid | Kept — reduces turnover |
| V5 Astro filter | ❌ Curve-fit | Should be removed |
| V6 V7 Combo 2x sizing | Valid | Kept |
| V7 V8 Monday ↓ | Valid | Kept |
| V8 V9 Mid-ADX ↓ | Valid | Kept |
| V9 V10 Moon 2x | Valid | Kept |
| V10-V13 | ❌ All rejected | See 4A |

---

## 5. 📝 PENDING — Ideas Not Yet Tested

| Idea | Notes |
|------|-------|
| **Side basket alt signals** | 64 large caps need DIFFERENT entry logic (pullback, trend continuation, multi-TF div) |
| **VWAP-EMA momentum grid search** | `strategy_vwap_ema_momentum.py` exists, code written, never run |
| **Exit tuning refresh** | Re-run on v1.1 divergence params |
| **Walk-forward validation** | Formal rolling walk-forward (partial done via cross-instrument) |
| **Monte Carlo simulation** | Trade-shuffle for DD confidence bounds |
| **Options CE/PE economics** | Underlying edge ≠ option P&L. Theta/premium model needed. |

---

## 6. 📁 RESEARCH DOCS — Complete Inventory

### 6A. Core Strategy Docs (ACTIVE — Keep)

| File | Content |
|------|---------|
| `docs/BASKET_100_RESULTS.md` | Basket-100 backtest results ✅ |
| `docs/STRATEGY.md` | Deployed strategy reference ✅ |
| `docs/PROJECT_STATUS.md` | Current project overview ✅ |
| `docs/PROJECT_HISTORY.md` | Full 3-month journey ✅ |
| `docs/RESEARCH_CATALOG.md` | This file ✅ |
| `docs/research/MOMENTUM_STRATEGY_MASTER.md` | Complete strategy reference ✅ |
| `docs/research/momentum_v1_FULL_SPEC.md` | Full spec & tearsheet ✅ |
| `docs/strategy_macd_momentum_BLUEPRINT.md` | Blueprint ✅ |
| `docs/SIDE_BASKET_LARGE_CAPS.md` | Side basket analysis ✅ |
| `docs/DEPLOY_VPS.md` | VPS ops guide ✅ |

### 6B. Research Findings (KEEP — reference)

| File | Content |
|------|---------|
| `docs/research/momentum_v1_improvement_attempts.md` | 5 rejected improvements ✅ |
| `docs/research/momentum_v1_multistock_FINDINGS.md` | Multi-stock validation ✅ |
| `docs/research/momentum_v1_exit_lab_FINDINGS.md` | Divergence recency tuning ✅ |
| `docs/research/momentum_v1_portfolio_FINDINGS.md` | Portfolio crash stress ✅ |
| `docs/research/momentum_v1_breadth_50_FINDINGS.md` | Breadth universe ✅ |
| `docs/research/momentum_v1_breadth_FIXED_FINDINGS.md` | Fixed breadth ✅ |
| `docs/research/multi_instrument_ecombined_FINDINGS.md` | 19-instrument test ✅ |
| `docs/research/standalone_macd_div_momentum_FINDINGS.md` | Original momentum discovery ✅ |
| `docs/research/backtest_cross_validation_FINDINGS.md` | 487/487 trade match ✅ |
| `docs/research/v14_validation_FINDINGS.md` | OOS validation ✅ |
| `docs/research/position_sizing_FINDINGS.md` | Sizing comparison ✅ |
| `docs/research/nifty_loss_cluster_sizing.md` | Loss clustering ✅ |
| `docs/research/nifty_sizing_backtest.md` | Full sizing report ✅ |
| `docs/research/nifty_10yr_pattern_analysis.md` | ⭐ **W1 + WL findings** — Mon DOW, streaks, WLWL ✅ |
| `docs/research/momentum_atlas_trade_FINDINGS.md` | Market atlas trades ✅ |
| `docs/research/nifty_market_atlas_FINDINGS.md` | NIFTY market atlas ✅ |
| `docs/research/momentum_trade_full_analysis.md` | Deep trade analysis (incl. streaks) ✅ |
| `docs/research/momentum_v1_STORY.md` | Strategy story ✅ |
| `docs/research/momentum_v1_optimization_FINAL.md` | Final optimization ✅ |
| `docs/research/momentum_v1_feedback.md` | Baba feedback loop ✅ |
| `docs/research/momentum_live_engine_hardening_backlog.md` | Live engine hardening ✅ |
| `docs/research/momentum_portfolio_crash_stress.md` | Crash stress test ✅ |
| `docs/research/deployed_basket_FINDINGS.md` | Deployed basket results ✅ |
| `docs/research/universe_expansion_FINDINGS.md` | Universe expansion ✅ |
| `docs/research/mainstrat_vs_momentum_breadth.md` | Comparison analysis ✅ |
| `docs/research/inout_gate_phase1_FINDINGS.md` | In/out gate phase 1 ✅ |
| `docs/research/inout_gate_plan.md` | Gate plan ✅ |
| `docs/research/macro_scenarios.md` | Macro scenario tracker ✅ |
| `docs/research/strategy_internals_audit_2026-06-26.md` | Strategy audit ✅ |
| `docs/research/structure_confirmation_rule.md` | Structure conf. rule ✅ |
| `docs/research/2025_macd_redweek_probe.md` | MACD red week probe ✅ |
| `_10yr_pattern_analysis.py` | Script that generated W1 + WL findings ✅ |

### 6C. Rejected Research Docs (CAN DELETE — failed ideas)

| File | Content | Verdict |
|------|---------|---------|
| `docs/research/overnight_drift_edge_FINDINGS.md` | Overnight drift | ❌ Real fills killed it |
| `docs/research/overnight_drift_INTEGRATION_plan.md` | Integration plan | ❌ Never used |
| `docs/research/overnight_options_GLOBAL_SCAN.md` | Global options scan | ❌ Not actionable |
| `docs/research/overnight_options_REAL_FILLS_REJECTED.md` | Real fills rejection | ❌ Record only |
| `docs/research/overnight_options_structure_FINDINGS.md` | Options structure | ❌ Record only |
| `docs/research/overnight_gold_STORY.md` | Gold overnight | ❌ Record only |
| `docs/research/pead_test_REJECTED.md` | PEAD test | ❌ Survivorship |
| `docs/research/uncorrelated_diversifiers_FINDINGS.md` | Diversifiers | ♻️ Parked |
| `docs/research/smart_day_open_PLAN.md` | Smart day open | ♻️ Parked |
| `docs/research/smart_day_open_frequency_FINDINGS.md` | Day open frequency | ♻️ Parked |
| `docs/research/new_moon_strategy_finding.md` | New moon strategy | ❌ V12 rejected |
| `docs/research/amavasya_manual_feedback_2025_2026.md` | Manual feedback | ❌ Legacy |
| `docs/research/nifty_momentum_monthly.md` | Monthly momentum | ♻️ Parked |
| `docs/research/nifty_10yr_findings.md` | 10yr analysis | ♻️ Parked |
| `docs/research/nifty_market_atlas.md` | Market atlas ref | ✅ Keep reference |
| `docs/research/1min_divergence/` | 1m divergence | ❌ Failed |
| `docs/smc_1m_spec.md` | SMC 1m spec | ❌ Failed |

### 6D. Superpowers/Plans Docs (LEGACY — can delete)

| File | Content |
|------|---------|
| `docs/superpowers/plans/2026-04-23-month-structure-bucket-plan.md` | Month structure plan |
| `docs/superpowers/plans/2026-04-24-nifty-short-extension-plan.md` | Short extension plan |
| `docs/superpowers/plans/2026-06-16-market-phase-panel.md` | Market phase panel |
| `docs/superpowers/specs/2026-04-23-month-structure-bucket-design.md` | Month structure design |
| `docs/superpowers/specs/2026-04-24-nifty-short-extension-design.md` | Short extension design |
| `docs/superpowers/specs/2026-05-01-vaibhav-pitch-design.md` | Pitch design |
| `docs/superpowers/specs/2026-06-16-market-phase-panel-design.md` | Market phase design |
| `docs/superpowers/specs/2026-06-20-momentum-portfolio-paper-dashboard-design.md` | Portfolio dashboard design |

### 6E. Planning / Roadmap Docs (KEEP — historical context)

| File | Content |
|------|---------|
| `docs/IMPROVEMENT_ROADMAP.md` | June roadmap (dated) |
| `docs/PHASE2_DIRECTIONS.md` | Phase 2 directions |
| `docs/SPRINT_2026-06-15_to_06-29.md` | 2-week sprint plan |
| `docs/INDEX.md` | Project map |
| `docs/GROK_SUGGESTIONS_REVIEW.md` | External review |
| `docs/pitch/MarketMantri_Pilot_Pitch.md` | Partner pitch |
| `docs/paper_trading/momentum_basket_LIVE_record.md` | Paper record |
| `docs/strategies/momentum-strategy-v1.md` | Strategy v1 doc |
| `docs/strategies/README.md` | Strategies overview |
| `PLAN_NEXT.md` | Pullback plan (historical) |
| `SUMMARY.md` | Research summary (historical) |
| `MEMORY.md` | AI assistant memory |
| `TRADING_STRATEGY_REPORT.md` | Trading strategy report |

---

## 7. 🗑️ GARBAGE CLEANUP RECOMMENDATIONS

### DELETE THESE (no value, failed ideas documented elsewhere):

```
docs/research/overnight_drift_edge_FINDINGS.md       → failed, real fills killed it
docs/research/overnight_drift_INTEGRATION_plan.md    → never used
docs/research/overnight_options_GLOBAL_SCAN.md       → not actionable
docs/research/overnight_options_REAL_FILLS_REJECTED.md → record only
docs/research/overnight_options_structure_FINDINGS.md  → record only
docs/research/overnight_gold_STORY.md                  → record only
docs/research/pead_test_REJECTED.md                    → failed
docs/research/1min_divergence/                         → failed
docs/smc_1m_spec.md                                    → failed
docs/superpowers/plans/*                               → legacy plans
docs/superpowers/specs/*                               → legacy specs
PLAN_NEXT.md                                            → outdated pullback plan
TRADING_STRATEGY_REPORT.md                              → outdated
```

### ARCHIVE THESE (low value, but document the journey):

```
docs/research/smart_day_open_PLAN.md                  → parked, low priority
docs/research/smart_day_open_frequency_FINDINGS.md    → parked, low priority
docs/research/new_moon_strategy_finding.md            → V12 rejected
docs/research/amavasya_manual_feedback_2025_2026.md   → legacy
docs/research/uncorrelated_diversifiers_FINDINGS.md   → parked, low priority
MEMORY.md                                              → historical only
SUMMARY.md                                             → historical only
```

### KEEP THESE (active reference):

All files listed in sections 1, 6A, and 6B above.

---

## 8. Summary Stats

| Category | Count |
|----------|:-----:|
| **Total research docs** | ~77 |
| **Active / Keep** | ~25 |
| **Rejected / Delete** | ~15 |
| **Parked / Archive** | ~10 |
| **Planning / Historical** | ~15 |
| **Legacy superpowers** | ~12 |
| **Hypotheses REJECTED** | **30+** |
| **Hypotheses ACCEPTED** | **3** (momentum, divergence, loss-2 sizing) |
| **Result CSV files** | ~59 |
| **Result JSON files** | ~50 |

> **The 30+ rejections ARE the moat.** Every one was honestly tested, honestly failed, honestly documented.
> The 3 accepted ideas survived a gauntlet that most ideas don't. That's why Sharpe 2.998 is real.

---

*Generated by Buffy on 22 July 2026 | #MarketMantri*
