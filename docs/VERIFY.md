# VERIFY.md — don't trust, verify

Every claim this project makes, with a **copy-paste command** and the **exact
output you should see** (all runnable from the repo root, Python 3 only, no
dependencies). If a claim isn't verifiable here, we don't make it.

Last verified: 27 Jul 2026, against commit `b2b71e6`.

---

## C1 — 10-yr NIFTY divergence study: 918 trades · 58.3% WR · PF 2.37 · Sharpe 2.31

```bash
python3 -c "import json;o=json.load(open('nifty_10yr_combined_results.json'))['overall'];print(o['trades'],o['win_rate'],o['profit_factor'],o['sharpe'])"
```
Expected: `918 58.3 2.37 2.31`

## C2 — that Sharpe's method is disclosed inside the artifact itself

```bash
python3 -c "import json;print(json.load(open('nifty_10yr_combined_results.json'))['sharpe_method'])"
```
Expected: the restatement note — per-trade Sharpe annualized by
√(trades/period-years); previously mis-annualized at √252 (3.84), restated
2026-07-27 to 2.31.

## C3 — recompute the Sharpe yourself from the raw stats (one line of math)

```bash
python3 -c "print(round(0.209/0.866*(918/9.99)**0.5,2))"
```
Expected: `2.31` — mean per-trade return ÷ std, scaled by √(918 trades /
9.99 years). The mean and std are in the same JSON (`avg_return`, `std_dev`).

## C4 — the look-ahead bug was caught, fixed and restated (6.08 → 2.998)

```bash
grep -n "6.08" docs/PROJECT_STATUS.md
head -3 lookahead_compare.csv
```
Expected: the Jul-W3 timeline line "Look-ahead bug FIXED. Sharpe 6.08 → 2.998
(honest)", and the lag-comparison CSV whose header is
`lag,window,trades,sharpe_net,...` — the permanent regression check.

## C5 — momentum basket portfolio: Sharpe 1.87 net / 2.18 gross

```bash
python3 -c "import json;v=json.load(open('v12_comparison_results.json'))['V12_OFF'];print(round(v['sharpe'],2),round(v['gross_sharpe'],2))"
```
Expected: `1.87 2.18` (fee drag 0.31 is in the same object).

## C6 — hypothesis volume: 18 catalogued + 34 documented rejections = 52 entries

```bash
grep -cE "^### " docs/RESEARCH_CATALOG.md
grep -cE "^### " docs/REJECTED_HYPOTHESES.md
```
Expected: `18` and `34`. **We quote "50+ hypotheses"** — 52 is the
conservatively countable floor in this snapshot; probe scripts in the private
repo push the informal total higher, but we only claim what you can count here.

## C7 — unit tests exist for the live-engine logic

```bash
ls tests/
```
Expected: 5 test files (portfolio, market phase, ATR trail, multi-TF MACD,
phase log). Running them needs `pip install -r requirements.txt`.

## C8 — the live paper record and its honest state

```bash
head -20 docs/paper_trading/momentum_basket_LIVE_record.md
```
Expected: the forward, timestamped record — started 22 Jun 2026, VPS-deployed
25 Jun. Day-36 snapshot (27 Jul 2026): **−4.7% of pool, 33% WR, 211 trades** —
in drawdown, at the edge of the backtest's ~5.1% max-DD expectation. That is
why the project's own money-gate holds real capital at **zero**.

---

## What is NOT claimed — read this too

- **No live-money performance.** Everything is backtest + forward paper.
- **No forward-confirmed edge yet.** The paper record is the test, and it is
  not passed; capital stays gated until ~3 months of forward proof.
- **Full re-runs need data** (Kite/OpenChart/yfinance) that is not shipped in
  this snapshot — scripts and `requirements.txt` are included; results JSONs
  are the committed evidence in the meantime.
- **Restatement history is deliberate:** Sharpe 6.08→2.998 (look-ahead, Jul
  W3) and 3.84→2.31 (annualization, 27 Jul) were both self-caught and
  restated everywhere. The dated ledger of every number is
  [`RESULTS.md`](RESULTS.md).
