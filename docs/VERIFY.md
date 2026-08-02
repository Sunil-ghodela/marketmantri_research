# VERIFY.md — don't trust, verify

Every claim this project makes, with a **copy-paste command** and the **exact
output you should see** (all runnable from the repo root, Python 3 only, no
dependencies). If a claim isn't verifiable here, we don't make it.

Last verified: **28 Jul 2026** — C1–C10 all re-run against their stated output.
C8–C10 are new (the two defects found on 28 Jul); C4 now carries the scope note that
2.998 is the unconstrained 46-name portfolio, not the live K=15 configuration.

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

**Scope note (28 Jul 2026):** 2.998 is the *unconstrained* 46-name portfolio — an
equal-weight average of every name's trades with no concurrency limit. The live
engine runs **K=15** slots and the cap binds (the backtest implies ~20–25
concurrent positions). It was previously described as "the REAL deployable number
— live trading will match this"; that description is withdrawn. Check the
constraint yourself:

```bash
python3 -c "import re;s=open('core/momentum_portfolio.py').read();print('live K =',re.search(r'^K = (\d+)',s,re.M).group(1))"
```
Expected: `live K = 15`. The K-capped backtest figure is `RESULTS.md` row #10.

## C5 — momentum basket portfolio: Sharpe 1.87 net / 2.18 gross

```bash
python3 -c "import json;v=json.load(open('v12_comparison_results.json'))['V12_OFF'];print(round(v['sharpe'],2),round(v['gross_sharpe'],2))"
```
Expected: `1.87 2.18` (fee drag 0.31 is in the same object).

## C6 — hypothesis volume: 18 catalogued + 35 documented rejections = 53 entries

```bash
grep -cE "^### " docs/RESEARCH_CATALOG.md
python3 -c "import json;d=json.load(open('site/graveyard.json'));print(sum(1 for x in d if x.get('s','rejected')=='rejected'), len(d))"
```
Expected: `18`, then `35 39`. **We quote "50+ hypotheses"** — 53 is the
conservatively countable floor in this snapshot; probe scripts in the private
repo push the informal total higher, but we only claim what you can count here.

**Which file is the count?** `site/graveyard.json` — it is the live ledger and
the one the public graveyard page renders, so the number on the site and the
number you can count here are the same object. `docs/REJECTED_HYPOTHESES.md` is
the long-form prose archive and stops at 22 Jul 2026 (34 entries); it is kept
for the detail, not for the count. If the two ever disagree, the JSON wins.

**Why 35 rejections but 39 entries?** Four entries on that page are *not*
rejections and are excluded from the headline number — they carry
`"s"` = `kept` / `abandoned` / `fixed` and render in a separate "Not rejections"
block: two filters that **passed** and are still in the strategy (Regime
Cooldown, Distance-from-High), one idea that was **never tested** (V13 1H MACD
filter), and one **defect we fixed** (the DIV-V2 look-ahead), which is a bug
report, not a hypothesis. They stay published — a count is only honest if its
exclusions are visible too.

*Drift caught 2 Aug 2026, before the first public post:* the site said **41**,
this file said **34**, and the BRAIN log was counting a third way — three
hand-maintained numbers for one quantity. Two entries were also duplicated
("Profit Target 5%", "V12 New Moon"), and the five above were never rejections
at all. Corrected to **35**, with the count now derived from a single file by
the command above. The claim that shrank is the claim we can defend.

## C7 — unit tests exist for the live-engine logic

```bash
ls tests/
```
Expected: 5 test files (portfolio, market phase, ATR trail, multi-TF MACD,
phase log). Running them needs `pip install -r requirements.txt`.

## C8 — the live paper record, restated 28 Jul 2026

The whole archived forward record ships in this repo, so check it yourself
rather than trusting a summary line:

```bash
python3 -c "import json,collections;d=json.load(open('archive/basket_forward_20260622_20260722.json'));t=d['trades'];print(len(t),'trades');print('pnl Rs',round(sum(x['pnl_abs'] for x in t)));print('WR',round(100*sum(1 for x in t if x['is_win'])/len(t),1),'%');print(collections.Counter(x['exit_reason'] for x in t))"
```
Expected: `203 trades` · `pnl Rs -25997` · `WR 31.0 %` ·
`Counter({'MACD Cross': 105, 'Max Hold': 63, 'Stop Loss': 35})`
— i.e. **−5.20% of the ₹5L paper pool** over 22 Jun – 22 Jul.

The previously published line was *Day 36 — −4.7%, 33% WR, 211 trades*. That
count included 8 trades produced after the 22 Jul exit-recording regression,
which also dropped 62 positions without writing a trade — so the count was
incomplete and the loss understated. The clean window is the 203 above.

## C9 — where the loss actually came from (and why max-hold looks good)

```bash
python3 -c "
import json,collections
t=json.load(open('archive/basket_forward_20260622_20260722.json'))['trades']
for r in ('Stop Loss','MACD Cross','Max Hold'):
    s=[x for x in t if x['exit_reason']==r]
    print('%-11s n=%-4d Rs %+8.0f  WR %4.1f%%' % (r,len(s),sum(x['pnl_abs'] for x in s),100*sum(1 for x in s if x['is_win'])/len(s)))"
```
Expected:
```
Stop Loss   n=35   Rs   -31395  WR  0.0%
MACD Cross  n=105  Rs   -16845  WR 21.0%
Max Hold    n=63   Rs   +22243  WR 65.1%
```
Max-hold is the only profitable bucket — not because holding longer helps, but
because of exit precedence (Stop Loss → MACD Cross → Bearish Div → Max Hold): a
trade only *reaches* max-hold if it never fell 2% and never lost its MACD. It is
the residual of trades that were already working.

Note the stop-loss row averages **−2.69% against a 2.0% stop** — the live engine
checks the stop on 15-minute closes, never intrabar, so gaps slip through it.

## C10 — the divergence filter had never actually run live

```bash
grep -n "strftime" divergence_detector_v2.py | head -3
grep -n "index=" core/momentum_portfolio_feed.py | head -3
```
Expected: the detector formats `df.index[...]` with `.strftime()`, and the feed
now passes `index=df.index` into the frame it hands the detector. Before
2026-07-28 it passed a bare `RangeIndex`, so every call that found an event
raised `AttributeError` and a blanket `except Exception: return "none"` swallowed
it — `div_state` was permanently `"none"` in **both** live engines from 11 Jun.

Measured over 89 stocks × 23 hourly bars (23–28 Jul): **0 of 2047** evaluations
returned a divergence state before the fix; after it, 30.8% bearish / 20.8%
bullish, and **25 of 77 cross-up signals (32.5%) blocked**.

Counterfactual on the archived record — exit each trade at the first bar its
divergence state would have turned bearish: Σ pnl_pct **−78.0% → −36.7%**, win
rate **31.0% → 38.9%**. So the missing filter explains roughly **half** the
forward loss; with it the record would still have been negative.

---

## What is NOT claimed — read this too

- **No live-money performance.** Everything is backtest + forward paper.
- **No forward-confirmed edge yet.** The paper record is the test, and it is
  not passed; capital stays gated until ~3 months of forward proof.
- **Full re-runs need data** (Kite/OpenChart/yfinance) that is not shipped in
  this snapshot — scripts and `requirements.txt` are included; results JSONs
  are the committed evidence in the meantime.
- **Restatement history is deliberate — four now:** Sharpe 6.08→2.998
  (look-ahead, Jul W3), 3.84→2.31 (annualization, 27 Jul), the divergence filter
  found never to have run live (28 Jul, C10), and the forward record found partly
  corrupted by an exit-recording regression, archived and restarted (28 Jul, C8).
  All four were self-caught and restated here. The dated ledger of every number is
  [`RESULTS.md`](RESULTS.md).
- **2.998 is not the live configuration.** It averages 46 names with no
  concurrency cap; the live engine runs 15 slots and the cap binds. The
  apples-to-apples K-capped figure is in [`RESULTS.md`](RESULTS.md) row #10 and
  `basket_k15_report.md` (pending).
- **The forward record restarted 28 Jul 2026.** The money-gate clock restarts
  with it — the earlier window did not test the documented strategy, because the
  divergence filter was inactive throughout.
