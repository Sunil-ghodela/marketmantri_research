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
research discipline actually looks like. (It happened twice: on 27 Jul the
10-yr study's Sharpe was restated 3.84 → 2.31 after catching a √252
annualization on ~92-trades/yr data — `docs/RESULTS.md` has the ledger.)

## Verified results (artifact-linked)

| Result | Numbers | Artifact |
|---|---|---|
| 10-yr NIFTY divergence study (2016–2026, 61k bars) | 918 trades · 58.3% WR · profit factor 2.37 · **Sharpe 2.31** (restated 27 Jul from a mis-annualized 3.84; backtest) | `nifty_10yr_combined_results.json` |
| MACD-momentum basket (59–90 stock universe) | median per-stock Sharpe ≈ 1.9 **net of fees** (backtest; cross-checks on NASDAQ & Hang Seng) | `v12_comparison_results.json` |
| Look-ahead audit | Sharpe restated 6.08 → 2.998 | `_lookahead_compare.py` · `docs/PROJECT_STATUS.md` |
| Live paper engine (VPS, cron) | 90-stock universe · K=15 equal-weight · decay gate · loss-cluster sizing · daily forward record since 22 Jun 2026 — **Day 36 snapshot (27 Jul): −4.7% of pool, within backtest DD bounds; edge not yet confirmed forward — hence zero real capital** | `docs/paper_trading/momentum_basket_LIVE_record.md` |

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
