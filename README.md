# MarketMantri — systematic trading research on NSE (independent)

> **This is a curated public snapshot** of a private research repo (Apr–Jul
> 2026, 345+ commits). Full history, data files and live-engine state stay
> private; happy to walk through them in an interview.

A 4-month, hypothesis-driven research program on Indian equities: an
end-to-end platform (data → event-driven backtests → Bayesian hyperopt with
walk-forward splits → live paper engine with dashboards), built and operated
by one person.

> **Honest status, up front:** everything here is **backtest + forward paper
> trading**. No real money has been deployed — that is a deliberate gate
> ("no capital until the forward record proves the edge"), not an accident.
> Every number below traces to a results artifact in this repo.

---

## The headline story: the day my Sharpe fell from 6.08 to 2.998

Mid-research, the flagship basket strategy showed Sharpe **6.08**. A
systematic look-ahead check (`_lookahead_compare.py`) revealed the backtest
was peeking one bar into the future. Fixing it cut the Sharpe to an honest
**2.998** — and the number was restated everywhere, in writing
(`docs/PROJECT_STATUS.md`, timeline Jul-W3).

Most research portfolios only contain wins. This repo's most valuable
artifact is a documented, self-caught failure — because that is what
research discipline actually looks like.

It has now happened **four times**, each restated in `docs/RESULTS.md`:

1. **Look-ahead bias** (Jul W3) — Sharpe 6.08 → **2.998**.
2. **Annualization** (27 Jul) — the 10-yr study used √252 on ~92-trades/yr
   data; restated 3.84 → **2.31**.
3. **The divergence filter had never actually run live** (28 Jul). Both live
   engines handed the V2 detector a `RangeIndex` frame while it formats
   `df.index[...]` with `.strftime()`, so every call raised `AttributeError`
   and a blanket `except` returned `"none"`. Measured: **0 of 2047**
   stock-bar evaluations were active before the fix; after it, **25 of 77
   cross-ups (32.5%) blocked**. For seven weeks the live engine was running a
   *different strategy* from the backtested one.
4. **The forward record was partly corrupted** (28 Jul). A sizing deploy on
   22 Jul over-indented the trade-recording block into the max-hold branch, so
   stop-loss / MACD-cross / divergence exits stopped recording and 62 positions
   were dropped with no trade written. The clean window was archived
   (`archive/basket_forward_20260622_20260722.json`) and the record restarted.

The fourth one is the least flattering and the most useful: four existing unit
tests were **already failing** on the branch that shipped, and nobody ran them.
The fix commit adds a regression test that fails against the old code.

## Verified results (artifact-linked)

| Result | Numbers | Artifact |
|---|---|---|
| 10-yr NIFTY divergence study (2016–2026, 61k bars) | 918 trades · 58.3% WR · profit factor 2.37 · **Sharpe 2.31** (restated 27 Jul from a mis-annualized 3.84; backtest) | `nifty_10yr_combined_results.json` |
| MACD-momentum basket (59–90 stock universe) | median per-stock Sharpe ≈ 1.9 **net of fees** (backtest; cross-checks on NASDAQ & Hang Seng) | `v12_comparison_results.json` |
| Look-ahead audit | Sharpe restated 6.08 → 2.998 | `_lookahead_compare.py` · `docs/PROJECT_STATUS.md` |
| **Scope note on 2.998** | it averages all 46 names with **no concurrency cap**; the live engine runs **K=15** slots and the cap binds (the backtest implies ~20–25 concurrent). Not "the number live will match" — the K-capped figure is the comparable one | `basket_k15_report.md` · `docs/RESULTS.md` #10 |
| Forward paper record, **22 Jun – 22 Jul (archived)** | **203 trades · 31.0% WR · −₹25,997 (−5.20% of the ₹5L pool)**. Loss concentrated in stop-loss (−₹31.4k, 0% WR, −2.69% avg on a 2.0% stop) and MACD-cross exits (−₹16.8k, 21% WR); max-hold was the only green bucket (+₹22.2k). **This window did not test the documented strategy — the divergence filter was inactive throughout** | `archive/basket_forward_20260622_20260722.json` · `docs/VERIFY.md` C8/C9 |
| Live paper engine (VPS, cron) | 90-stock universe · K=15 equal-weight · decay gate · loss-cluster sizing · **record restarted 28 Jul 2026** on the fixed engine, divergence filter live for the first time. Money-gate clock restarts with it — **zero real capital** | `docs/paper_trading/momentum_basket_LIVE_record.md` |

An independent, framework-based evidence audit of this repo — what is
verified, what is not — lives at **`docs/AUDIT-2026-07-26.md`**. The
canonical, dated ledger of every number ever quoted (including the invalid
ones) is **`docs/RESULTS.md`** — start there. To check any claim yourself with
one copy-paste command, use **`docs/VERIFY.md`**.

## Research process

- **50+ hypotheses** tested and written down: 18 catalogued in
  `docs/RESEARCH_CATALOG.md`, **34 documented rejections** in
  `docs/REJECTED_HYPOTHESES.md` — rejections are data too. Count them
  yourself: `docs/VERIFY.md` has the commands.
- Walk-forward / out-of-sample discipline via `optuna` splits; fee-aware
  net results; unit tests in `tests/`.
- Research runs in an AI-agent-assisted workflow: agents draft code and
  analysis; a human gates every deploy.

## Stack

| Layer | Tool | Purpose |
|---|---|---|
| Data (primary) | `kiteconnect` | Official NSE data via Zerodha API |
| Data (fallback) | `openchart` | Free NSE scraper |
| Data (emergency) | `yfinance` | Daily bars, last resort |
| Backtest engine | `backtesting.py` | Event-driven class-based strategies |
| Indicators | `pandas-ta` | 130+ indicators |
| Hyperopt | `optuna` | Bayesian TPE with walk-forward splits |
| Reports | `quantstats` | HTML tearsheets |
| Live engine | Python + cron on VPS | State-file driven, HTML dashboards |

## Repo map

- `strategy*.py`, `backtest*.py` — strategy families and engines
- `_*.py` — research probes (one hypothesis per file; results JSON/CSV beside it)
- `docs/` — `PROJECT_STATUS.md` (honest review) · `RESEARCH_CATALOG.md` ·
  `REJECTED_HYPOTHESES.md` · `DEPLOY_VPS.md` · `AUDIT-2026-07-26.md`
- `docs/paper_trading/` — the forward, timestamped paper record
- `tests/` — unit tests (portfolio, indicators, phase logic)

## Disclaimer

Research and educational code only. Nothing here is investment advice, and
no live-capital performance is claimed anywhere in this repository.
