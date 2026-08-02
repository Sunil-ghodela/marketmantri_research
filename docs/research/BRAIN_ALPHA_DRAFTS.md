# WorldQuant BRAIN — alpha drafts from the MarketMantri hypotheses

> Purpose: validate the **signal** side of our hypotheses on independent data/infra
> (platform.worldquantbrain.com). This does NOT test the engine (K slots, sizing,
> max-hold, NSE costs) — that stays in our own harness.
>
> ⚠️ **IP note:** alphas submitted to BRAIN belong to WorldQuant. These drafts are
> deliberately *generic-ified* (plain MACD/momentum building blocks, none of our
> tuned parameters like rec6/sig5 or the deployed exit stack). Do not paste the
> deployed strategy's exact recipe there.
>
> ⚠️ **Operator names are from memory and may be slightly off** — check the platform's
> operator reference; the *shapes* of the ideas are what matter. Start on USA TOP3000,
> delay-1, neutralization = subindustry, decay 4–8, truncation 0.05–0.10.

---

## Alpha 1 — MACD momentum, cross-sectional (the core claim)

*Hypothesis: stocks whose medium-term momentum just turned positive outperform peers.*

```text
# building blocks (EMA nahi hota to ts_mean/ts_decay_linear se approximate karo)
macd   = ts_mean(close, 12) - ts_mean(close, 26);
signal = ts_mean(macd, 9);
hist   = macd - signal;

# cross-sectional: histogram ka level + uska fresh flip
rank(hist) + rank(ts_delta(hist, 3))
```

- Variants to sweep: `ts_delta` window 2–5; replace level with `ts_rank(hist, 60)`.
- Expectation from our work: works in trends, whipsaws in chop — watch the
  year-by-year PnL, not just aggregate Sharpe (our NIFTY analogue: 2.9/2.8/3.2
  in 2023–25, ~0.2 in 2026 YTD).

## Alpha 2 — divergence as a signal *modifier* (the profit-engine claim)

*Hypothesis: momentum longs are worth less when price and momentum disagree
(bearish divergence). Down-weight, don't block.*

```text
macd = ts_mean(close, 12) - ts_mean(close, 26);
hist = macd - ts_mean(macd, 9);

# divergence proxy: price-vs-momentum agreement over ~1 month
agree = ts_corr(close, hist, 20);        # low/negative => divergence

# momentum, scaled by agreement (bearish divergence shrinks the position)
rank(hist) * winsorize(agree, std=2)
```

- Compare against Alpha 1 alone: the claim is PnL smoothness improves (our
  counterfactual: filter halves the losses, clips some winners).
- Variant: gate instead of scale — `trade_when(agree > 0, rank(hist), -1)`.

## Alpha 3 — breadth-regime throttle (open research item 9)

*Hypothesis: scale exposure by market-level breadth instead of filtering per-stock.
Per-stock chop filters died in our graveyard; the market-level version is untested.*

```text
macd  = ts_mean(close, 12) - ts_mean(close, 26);
hist  = macd - ts_mean(macd, 9);

# breadth: share of the universe with positive momentum (market-group mean)
breadth = group_mean(sign(hist), 1, market);

# momentum signal, throttled by regime (healthy -> full, hostile -> shrunk)
rank(hist) * (0.25 + 0.75 * group_rank(breadth, market))
```

- If group ops fight the dollar-neutral setting, test with neutralization=none
  first to see the raw effect, then re-add neutralization and check what survives.
- This is the BRAIN-leg of SITUATION.md item 9; the engine-level version (size
  multiplier in our own backtest) is the main leg.

---

## Submission bar (approx — platform में verify करो)

Sharpe ≳ 1.25 · fitness ≥ 1 · turnover roughly 1–70% · low self-correlation with
your other alphas · passes their OOS holdout. Simulate → iterate on ONE knob at a
time → submit only what's robust across years.

## Workflow

1. Account: platform.worldquantbrain.com (region list check karo — IND hai ya nahi).
2. Alpha 1 pehle — it's the base; note per-year IS results.
3. Alpha 2 vs Alpha 1 delta — divergence modifier ka value isolate hota hai.
4. Alpha 3 sirf tab jab 1 kaam karta dikhe.
5. Jo bhi survive kare, uska nateeja yahan wapas likho (per-year table) — that is
   independent evidence for/against our hypotheses, on data we never touched.

---

## Results log

### 29 Jul 2026 — first session (USA/TOP3000/D1, subind neutral, decay 4, trunc 0.08, test period 1y hidden)

**Alpha 1 — MACD momentum (as drafted):** Sharpe **−0.76** · fitness −0.31 · turnover 28.3% ·
DD 23.7%. Yearly: 2019 +0.75 · 2020 −1.21 · 2021 −0.47 · 2022 −1.39. Consistently negative →
not dead, **inverted**: on the US daily cross-section, MACD-histogram strength mean-reverts
(classic short-term reversal territory).

**Alpha 1-flip — "MACD reversal v1" (alpha id RR1zLZGg):** exact mirror — Sharpe **+0.76** ·
fitness 0.31 · DD **7.46%**. Yearly: 2019 −0.75 · 2020 +1.21 · 2021 +0.47 · 2022 +1.39.
Real signal, but regime-dependent (flat pre-mid-2020, 2019 negative) and below the ~1.25
submission bar. NOT submit-grade yet.

**Read-across to our NSE claim:** "MACD momentum works" is not universal — it is market/
horizon-specific. This neither validates nor kills the NSE 1H strategy; it kills the naive
transplant. Divergence-proxy test (Alpha 2) now runs as a modifier on the *reversal*
baseline, so its mapping to the NSE hypothesis is looser — we only claim "does
price-momentum disagreement carry extra information", nothing more.

Next queued: v2 delta-only reversal; Alpha 2 modifier delta vs reversal-v1.

### 29 Jul — iteration results (train only, test still sealed)

| variant | Sharpe | fitness | turnover | 2019 | 2020 | 2021 | 2022 |
|---|--:|--:|--:|--:|--:|--:|--:|
| reversal v1 (level+delta) | 0.76 | 0.31 | 28.3% | −0.75 | 1.21 | 0.47 | 1.39 |
| reversal v2 (delta only) | 0.95 | 0.40 | 30.1% | −1.21 | 1.76 | 0.32 | 1.85 |
| **v1 × divergence modifier** (id N1RzM10X) | **1.00** | **0.48** | **23.1%** | **+0.71** | 2.67 | 0.13 | 0.55 |

**The divergence-hypothesis result we came for:** multiplying the reversal base by the
price-momentum agreement proxy (`ts_corr(close, hist, 20)`) raised Sharpe (+0.24), raised
per-trade margin (3.39→4.64‱), CUT turnover (28→23%) and flipped the worst year (2019
−0.75→+0.71) — on data we never touched. Same mechanism we predicted for the NSE engine
(divergence → fewer/better entries → less churn cost). Caveats: gains concentrated in 2020;
2021/22 softer than base; still below the ~1.25 bar.

Queued: compose delta-only × modifier; then decay 4→8; only then one look at the test period.

### 29 Jul — verdict: OOS FAIL, hypothesis closed (rejection logged)

Final iterations: delta5 base 0.89 (worse than delta3); delta3×modifier 0.85 (delta and
agree overlap — they share information); decay-8 on champion 0.95/19.8% turnover (cheaper,
flatter, slightly lower Sharpe). Champion stayed **v4** (level+delta3 × agree modifier,
id N1RzM10X): train Sharpe 1.00, fitness 0.48.

**Pre-registered test look (one shot): TEST 2023 = Sharpe −0.29, fitness −0.06,
returns −0.97%.** Train edge was 2020-concentrated and did not survive out of sample.
Per the pre-registered rule: not submitted, no post-test tweaking, closed.

**What survives from the session:**
1. MACD-strength on the US daily cross-section mean-reverts (robust sign, both directions).
2. The divergence proxy (`ts_corr(close, hist, 20)`) consistently improved the in-sample
   base across variants (+Sharpe, −turnover, +margin, rescued 2019) — the *modifier* keeps
   its in-sample support even though the *base* died OOS.
3. The whole alpha family is a 2020-vol-regime artifact — logged in the graveyard
   ledger (`site/graveyard.json`, count via `docs/VERIFY.md` C6),
   this time on data we never touched, with the test period sealed until one look.

Next session (fresh hypothesis, not a tweak): different data set (the "Single Data Set
Alpha" flag is the platform's own hint — price-volume alone is crowded), or IND region if
available, or the throttle idea on a working base. Tutorial/certificate track in parallel.

---

### 31 Jul 2026 — automated reproduction (`tools_brain_api.py`, no manual clicks)

System test of the new API harness: authenticate → submit → poll → metrics, all from code
(account SK98175, no biometric). The three runs **reproduce the 29-Jul manual session on
independent re-simulation** — same settings (USA/TOP3000/D1, subind neutral, decay 4, trunc 0.08,
startDate 2019):

| run | expression | Sharpe | DD | note |
|---|---|--:|--:|---|
| Alpha 1 (momentum base) | `rank(hist) + rank(ts_delta(hist,3))` | **−0.67** | 26.8% | inverts on US daily (manual logged −0.76 — same sign) |
| Alpha 2 (modifier on momentum base) | `rank(hist) * winsorize(agree,2)` | **−0.86** | 28.4% | worse — modifying an inverted base |
| champion (reversal base × modifier) | `-(rank(hist)+rank(ts_delta(hist,3))) * winsorize(agree,2)` | **+0.80** | **7.3%** | sign flips +; modifier's value = **DD 26%→7%** |

**What this confirms:** (1) the harness works end-to-end; (2) the divergence proxy
`ts_corr(close,hist,20)` carries real information — its value shows up as **risk reduction**
(drawdown collapses 26%→7% on the reversal base), the same mechanism we claim for the NSE engine
(divergence → fewer/better entries → smoother PnL). **What it does NOT change:** 0.80 < 1.25 bar,
`LOW_SUB_UNIVERSE_SHARPE` FAIL (0.12) — edge is concentrated, not broad — and this whole family
already **OOS-failed** (29 Jul, 2023 test −0.29, 2020-vol artifact). Reproduction/validation, not a
new edge. Nothing submitted. Discipline held: these were re-runs of a closed hypothesis, not new bets.

## Graveyard recycling plan — queue for next sessions

**Premise:** a graveyard hypothesis is dead *in its context* (NSE/1H/our engine), not
universally — today's session showed context can flip a result in either direction.
Re-test only the SIGNAL-shaped ones on BRAIN; engine-mechanics don't map.

**Rules (non-negotiable, learned today):**
1. ONE hypothesis per day. Iterate on train only; ONE sealed test-period look at the
   pre-declared champion; verdict pre-registered in this file BEFORE the look.
2. No post-test tweaking of that alpha, ever. Survives → consider submit; dies → log,
   next hypothesis.
3. Generic forms only — none of our tuned parameters (BRAIN owns submissions).
4. Every result logged here, wins AND deaths.
5. 30+ hypotheses × many knobs = guaranteed false positives — the queue below is capped
   and triaged; do not spray.

**Queue (priority order):**

| # | Hypothesis | Why it died on NSE | Why BRAIN may differ | Sketch |
|---|---|---|---|---|
| 1 | **PEAD** ⭐ | survivorship illusion in our data | real earnings datasets + survivorship-free universe; documented anomaly; also fixes the "Single Data Set Alpha" flag | rank of post-announcement drift using an earnings/estimates dataset from the Data tab |
| 2 | **OBV / volume-flow** | tuning edge didn't hold | clean volume fields, cross-sectional flow is classic | `rank(ts_corr(close, obv-proxy, d))` family |
| 3 | **Gap reversal** | (engine frame) | overnight-gap fade = short-term reversal cousin | `-rank((open - ts_delay(close,1)) / ts_delay(close,1))` |
| 4 | **Weekly momentum** | trade count collapsed | frequency is a non-issue cross-sectionally | 12-1 style: `rank(ts_delta(close, 250) / close)` minus recent month |
| 5 | **Regime/ADX/chop as modifier** | per-trade filter mis-composed | modifier pattern just worked (divergence session) | multiply a working base by a regime `trade_when`/scalar |

**Not mappable (skip):** max-hold, stop tuning, sizing, cooldown, profit targets,
1m scalp, hourly port — engine mechanics, not cross-sectional signals.
**Skip anyway:** astro/new-moon (market-wide timing; meaningless when neutralized;
kept out of public material by standing decision).

**Standing note:** the best ROI on BRAIN is likely NEW datasets (analyst, sentiment,
fundamentals), not recycling price-volume ideas — PEAD is first precisely because it
brings a new dataset.

---

### 2 Aug 2026 — Session 2: PEAD (queue #1) — PRE-REGISTRATION (sims se pehle commit)

**Hypothesis:** post-earnings-announcement drift — jis stock ka actual quarterly
EPS consensus se upar aaya, wo announcement ke baad hafton tak peers se behtar
chalta hai (documented anomaly; NSE me survivorship-illusion me mara tha,
yahan survivorship-free universe + asli estimates data hai).

**Fields (analyst4, USA/TOP3000/D1):** `actual_eps_value_quarterly` (cov 1.0),
`anl4_qfv4_eps_mean` (cov 1.0), variant ke liye
`stddev_reported_eps_quarterly_estimate` (cov 0.56).

**Settings:** session-1 convention — subind neutral, decay 4, trunc 0.08,
testPeriod P1Y **sealed** (stats-printer train-only; test block final look tak
code me hi chhupa hai).

**Sim plan (cap 7, ek knob ek baar):**
1. base: `rank((actual_eps_value_quarterly - anl4_qfv4_eps_mean) / close)`
2. event-window: wahi, sirf announcement ke 60 din tak
   (`days_from_last_change(actual_eps_value_quarterly)` gate)
3. SUE scaling: close ki jagah stddev-of-estimates se bhaag (coverage cost check)
4. freshness weight: surprise × linear fade over 60d
5. decay 4→8 champion pe
6–7. reserve (error-fix/insight only — naya idea NAHI)

**Champion rule (abhi likha):** best train **fitness**, shart: turnover 1–70%,
train Sharpe ≥ 1.0 prefer. Sims ke baad champion yahin declare hoga, TABHI test.

**Verdict rule (abhi likha, test-look se pehle):** champion ka TEST Sharpe ≥ 0.5
AND sign train se match → zinda (submission-checks tak jayega). Warna → REJECTED,
log, band — koi post-test tweak nahi, kabhi nahi.

### 2 Aug — Session 2 results & verdict: PEAD REJECTED (logged in the graveyard ledger)

Train (sab, USA/TOP3000/D1/subind/decay4, test sealed):
| sim | idea | sharpe | fitness | turnover |
|---|---|---|---|---|
| S1 | base rank((actual−est)/close) | 0.01 | 0.00 | 3.6% |
| S2 | + 60d event-window | −0.19 | −0.06 | 5.8% |
| S3 | SUE (stddev-scaled) | −0.04 | −0.00 | 5.7% |
| S4 | freshness-fade | −0.51 | −0.26 | 9.2% |
| S5 | timing-fix (est ts_delay 63) | 0.07 | 0.01 | 3.7% |

**Champion (pre-registered rule: best train fitness): S5 (id zqNvOJ5G).**
**Sealed test-look (ONE, ritual poora): TEST Sharpe −0.74, fitness −0.44.**
**Verdict (pre-registered: TEST ≥ 0.5 + sign-match chahiye tha): REJECTED. Band.**
Koi post-test tweak nahi hua; sim-cap 7 me 5 use hue (2 reserve bache, kharch nahi kiye).

**Kya seekha (log, bahana nahi):**
1. Naive consensus-surprise PEAD is platform/universe pe kahin nahi dikhta — na raw,
   na windowed, na SUE, na freshness, na timing-fix. Sab ~0 ya negative.
2. Literature bhi kehta hai PEAD post-2010 large/mid-caps me heavily arbitraged hai;
   TOP3000 + delay-1 + subind-neutral shayad use poora kha jaata hai. Chhota
   universe / event-day data / different surprise def kisi AUR din ki alag
   hypothesis hai — is session ki tweak nahi.
3. Process note: session poori API se chali (login owner ke haath, cookie-only),
   pre-registration sims se pehle commit hui (5d7c12c) — discipline ab automated hai.

**Queue agla (kisi aur din, one-per-day):** #2 OBV/volume-flow.
