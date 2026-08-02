# ❌ Rejected Hypotheses — long-form archive (through 22 July 2026)

> ⚠️ **This file is the prose archive, NOT the count.** It has 34 entries and
> stops at 22 Jul 2026. The live ledger is **`site/graveyard.json`** (35
> rejections + 4 tagged non-rejections), rendered at `site/graveyard.html` and
> counted by `docs/VERIFY.md` C6. If the two disagree, the JSON wins. Keeping
> two hand-maintained lists is exactly what caused the 41-vs-34 drift caught on
> 2 Aug 2026 — this file is kept for the detail, and nothing quotes it as a
> total.

> **Date:** 22 July 2026  
> **Purpose:** Every idea we tested and why it failed — the moat that protects the 3 that survived.
> **Theme:** Most failures = "edge < friction" or "2-year sample lies" or "overfit."

---

## How Each Hypothesis Died

Each entry has:
- **What:** the idea in one line
- **Why it seemed promising:** what made us test it
- **The kill shot:** the specific test that killed it
- **Lesson:** what we learned

---

## Category A: Strategy.py Tweaks (V10 Pullback Lineage)

### A1. V11 — Bearish Divergence Skip on strategy.py
- **What:** Skip entry when 15m bearish divergence is active
- **Why promising:** Divergence is a classic reversal signal; should filter false breakouts
- **Kill shot:** **Zero impact** on 10yr backtest — V2 detector found 642 bearish events globally but NONE within recency window of a trade surviving other filters (cooldown, distance, astro). Entry conditions structurally incompatible with bearish divergence context
- **Lesson:** A filter only matters if the signal actually fires. If your entry is already rare (~16 trades/yr), divergence almost never overlaps with it

### A2. V12 — New Moon MACD Momentum Entry
- **What:** When main conditions NOT met but T-2 New Moon window + MACD hist flip positive → enter
- **Why promising:** New Moon has historical edge; MACD flip times it precisely
- **Kill shot:** Sharpe 1.826→1.7996 (neutral-to-negative). DD 3.59%→5.26% (+46%). Added 12 extra trades in 10yr but quality was lower
- **Lesson:** Forcing extra entries degrades quality. New Moon edge works as sizing (V10 Moon 2x), not as entry trigger

### A3. V13 — 1H MACD Filter on strategy.py
- **What:** Skip trades when 1H MACD state is "red + bearish" (43/164 = 26% of trades)
- **Why promising:** Those 43 trades had Sharpe −0.242 (loss-making). Skipping them showed +12% Sharpe on paper
- **Kill shot:** **Never completed full isolated standalone test.** V13 code was committed but the attention shifted to the standalone MACD Momentum strategy before the test ran. Still pending (likely unnecessary now — momentum is the primary)
- **Lesson:** Scope creep. The momentum breakthrough de-prioritized this

### A4. Astro Nakshatra Gate (strategy.py V6)
- **What:** Skip certain nakshatras (lunar constellations)
- **Why promising:** Bottom-5 nakshatras looked like structural losers
- **Kill shot:** **Curve-fit.** Bottom-5 don't persist across halves (overlap 1/5, rank-corr −0.09). Not significant (p=0.125). Astro ablation inconsistent across instruments
- **Lesson:** P-value and cross-half validation catch overfits every time

### A5. up_ratio Window=20 (strategy.py Core)
- **What:** up_ratio(20) is the core entry signal — detects upward acceleration over 20 bars
- **Why promising:** Looked like a tuned, precise entry
- **Kill shot:** **Sharp overfit peak** — Sharpe 1.79 at 20 **collapses to ~1.0 at 16/26 and ~0.65 at 12/34**. A knife-edge
- **Lesson:** If moving a parameter by 20% kills the edge, it's not an edge — it's a fit. Momentum's params are smooth plateaus; this was a spike

### A6. Profit Target 5% (strategy.py V3)
- **What:** Exit at +5% profit
- **Why promising:** +5% gain is a reasonable target; round number
- **Kill shot:** **Inert.** 0.05/0.08/0.15/OFF all = 1.79 Sharpe. Rarely triggers. Pure decoration
- **Lesson:** In a strategy averaging +0.37%/trade, a 5% target is never hit. Dead parameter from the start

---

## Category B: Momentum Entry/Exit Tweaks (5 Tests)

### B1. MACD Cross Exit OFF
- **What:** Remove the MACD-cross exit. Let bearish divergence + max-hold handle all exits
- **Why promising:** "MACD Cross" exits lost −₹17k vs "Bearish Div" exits made +₹36k
- **Kill shot:** Sharpe 1.41→**0.47**. DD 2.13%→**5.68%** (2.7×). The cross-exit is **risk control** — it cuts losers early. Without it, losers run to max-hold and blow up
- **Lesson:** The exit that "loses money" is insurance. Remove insurance → worse outcomes

### B2. MACD Cross Exit (loss-only mode)
- **What:** Only exit via MACD cross if currently in loss. Winners exit only on bearish div
- **Why promising:** Let winners run longer, cut losers faster
- **Kill shot:** Sharpe 1.41→1.23. Winners held past the cross then reversed into loss → deeper losses
- **Lesson:** The cross happens near the top. Holding past it doesn't capture more — you give back gains

### B3. 15m Entry Confirm
- **What:** Confirm 1H MACD cross with 15m MACD cross before entering
- **Why promising:** 15m turns earlier than 1H — faster entry
- **Kill shot:** Marginally worse across all metrics. The 15m is PART of the chop, not a chop detector — in chop BOTH oscillate
- **Lesson:** Double confirmation removes trades without improving quality

### B4. 15m Exit (faster exits)
- **What:** Exit on 15m MACD cross instead of 1H
- **Why promising:** Faster → smaller losses
- **Kill shot:** Sharpe 1.41→**0.78**. 15m exit = noisy → cuts winners before bearish-div exit fires. The 1H lag is a FEATURE, not a bug
- **Lesson:** The profit engine (bearish div exit) needs time to trigger. Faster exits kill profit before the engine fires

### B5. ADX Chop-Gate (entry)
- **What:** Skip entry if ADX < 15/20/22/25 (chop filter)
- **Why promising:** Obvious — don't trade in chop!
- **Kill shot:** ALL thresholds worse. Momentum enters EARLY (MACD cross = trend birth, ADX still low). ADX≥20/25 = enter after trend established = miss the early entry
- **Lesson:** At entry time, "chop that fails" and "early trend that runs" look identical. Can't filter one without killing the other

---

## Category C: Profit Target (the one that fooled 2yr)

### C1. Profit Target +0.4% on Momentum
- **What:** Exit at +0.4% gain to capture MFE on reversal trades
- **Why promising:** Baba's insight: losing June trades gave ~180 NIFTY pts favorable move before reversing. Capture that
- **Kill shot:** **2yr looked great (Sharpe 1.41→1.52). 10yr OOS: total return −67%.** Those few fat-tail winners (+3-5%) carry the entire strategy. Profit-target caps them
- **Lesson:** A 2-year window fooled us twice. The 10-year OOS told the truth. Textbook OOS save

### C2. Profit Target +1.0% on Momentum
- **What:** Same idea, higher target
- **Why promising:** More room for runners
- **Kill shot:** 10yr OOS: total return **−33%** for +0.1 Sharpe improvement. 1/3rd of profit gone
- **Lesson:** Letting winners run IS the edge. No cap improves it

---

## Category D: Complete Strategies (Rejected)

### D1. Overnight Short Put Spread (Options)
- **What:** Sell 0.5% OTM put, buy 2.5% OTM put weekly, enter at close, exit at next-day open
- **Why promising:** **Modeled (Black-76) test showed Sharpe 2.87** — looked like THE breakthrough
- **Kill shot:** **Real open fills from NSE bhavcopy: Sharpe −1.78.** The gap-down tail cancels the drift. Model assumed smooth repricing; reality = IV spike + panic first print = gap nights killed everything. ALL five structures tested (sell puts, buy puts, naked puts, strangle, iron condor) — **none worked. Best gross Sharpe was +0.30.**
- **Lesson:** "Modeled fills" are not real fills. Real data BEFORE deploying capital is the discipline that separates systems from gambles. **Edge < friction** — 600 nights showed a REAL tiny drift (+0.34% median) but transaction cost + gap tail ate it

### D2. Overnight Cash Drift
- **What:** Capture NIFTY overnight gap with futures
- **Why promising:** Backtest showed real drift exists
- **Kill shot:** Drift is real (+0.34% median) but **uninvestable** after transaction costs. Same "edge < friction" problem as options
- **Lesson:** "Real" ≠ "tradable"

### D3. PEAD (Post-Earnings Announcement Drift)
- **What:** Buy stocks after positive earnings surprise, short after negative. Hold 60 days
- **Why promising:** Academic literature (CAR ~4.8%/64d, OOS-stable). Cleanest genuinely-different idea
- **Kill shot:** **Survivorship illusion.** Event study showed Q5 best surprise = +2.76% over 60d. BUT long-short (Q5−Q1, cancels survivorship + market beta): **Net Sharpe 0.22 — first half 0.07.** Clean FAIL
- **Lesson:** The event-study's "drift" was large-cap outperformance, NOT earnings alpha. Survivorship-neutral test caught the illusion

### D4. 1m Scalp
- **What:** Ultra-short mean-reversion scalping on 1-minute data
- **Why promising:** 83% WR claim (later withdrawn)
- **Kill shot:** Fees kill edge. **0-for-12 tested.** Claim not reproducible
- **Lesson:** 1m strategies in Indian markets = fee-farming for the broker

### D5. 5m Unified Strategy
- **What:** ADX-regime-adaptive scalper (choppy vs trend modes)
- **Why promising:** 83% WR claimed (attractive)
- **Kill shot:** **Claim withdrawn** — results not reproducible. Strategy was overfit/curve-fit. Honest withdrawal documented
- **Lesson:** Extraordinary claims require extraordinary evidence. This one didn't survive scrutiny

### D6. NIFTY Futures Shorts (Bidirectional)
- **What:** Extend long-only momentum to include shorts
- **Why promising:** Capture down moves too
- **Kill shot:** Bidirectional test showed **no edge** — short side carries down-years worse than long-only. 2026 BOTH +13% vs long-only −1% but over 10yr, shorts degrade Sharpe
- **Lesson:** Momentum works asymmetrically in Indian markets — long-only is the edge

### D7. MTF Candle Funnel
- **What:** Nested TF confluence — enter green-1h only when month/week/day all above period-open
- **Why promising:** Intuition: higher-TF alignment = stronger signal
- **Kill shot:** Faint 1-day momentum (+0.024% over baseline) but **reverses at 3 days** and per-candle edge (+0.0155%) < 0.05% cost. **Not tradable.**
- **Lesson:** The deployed momentum strategy already captures the 1-day momentum and exits before reversal. The funnel reaches for what's already there

### D8. MTF Alignment → Option Direction on NIFTY
- **What:** Month+week+day alignment on NIFTY, express via CE/PE
- **Why promising:** 2-year (2021-22, aeron7) showed ALL-RED = real bear edge (62% down days, bigger moves)
- **Kill shot:** **10-year data reversed it.** ALL-RED → +0.070%/EOD (oversold intraday bounce). The 2yr bear edge was a **2022-regime artifact**. Another **2-year sample lie**
- **Lesson:** 2-year samples killed here too. The 10-year data discipline caught the regime artifact

---

## Category E: Filter/Gate Ideas (Rejected)

### E1. Higher-TF Trend Gate
- **What:** Only trade when higher timeframe trends align
- **Why promising:** Common institutional approach
- **Kill shot:** **Counter-trend filters mis-compose with momentum.** Every variant hurt returns
- **Lesson:** Momentum and trend-gating are philosophically opposed. Momentum enters at trend birth (when higher-TF hasn't confirmed). Gating it = killing it

### E2. Month-Anchor Breakout
- **What:** Trade breakouts from monthly open
- **Why promising:** Monthly levels are psychological
- **Kill shot:** No edge found
- **Lesson:** Sometimes simple ideas just don't work

### E3. Short-Extension
- **What:** Extend short side with additional filters
- **Why promising:** Capture bear moves
- **Kill shot:** No edge after costs
- **Lesson:** Shorting in India has structural headwinds (STT, uptick rule, limited borrow)

### E4. Meta-Labeling (ML)
- **What:** ML model to predict which signals to take
- **Why promising:** Machine learning should improve selection
- **Kill shot:** No edge. 10yr data, proper walk-forward — ML added nothing
- **Lesson:** In low-frequency strategies (~49 trades/yr), there's not enough data for ML to learn anything useful

### E5. Yearly-Anchor-as-Filter
- **What:** Skip trades based on yearly open position
- **Why promising:** Annual levels are important
- **Kill shot:** Not a filter — had no predictive power
- **Lesson:** Annual opens are descriptive, not predictive

### E6. Version C 1m
- **What:** Alternative 1m strategy variant
- **Why promising:** Different entry logic
- **Kill shot:** No edge (like all 1m strategies)
- **Lesson:** 1m in Indian equity = structurally unprofitable after costs

### E7. Correlation Gate
- **What:** Skip signals when market-wide correlation spikes
- **Why promising:** Crashes have high correlation
- **Kill shot:** No edge. Correlation spikes don't predict direction
- **Lesson:** Knowing WHEN is not knowing WHICH WAY

### E8. Uncorrelated Diversifiers (Gold, Silver, FANG, Crypto)
- **What:** Add non-equity assets for diversification
- **Why promising:** Lower portfolio correlation
- **Kill shot:** **Modest +6% gain (parked).** Crypto killed by Indian TDS (30% on profits). Other diversifiers showed small edges but require separate infrastructure
- **Lesson:** Diversification is real but expensive to implement

---

## Category F: Strategy.py Additional Gates (V10 Context)

### F1. Profit Target 5% (strategy.py)
- **What:** Book profit at +5%
- **Why promising:** Common sense
- **Kill shot:** Inert — rarely triggers at +5%
- **Lesson:** Same momentum lesson — let winners run

### F2. Regime Cooldown (48h after bear crossover)
- **What:** Don't enter for 48h after EMA50/200 bear cross
- **Why promising:** Avoid bear market traps
- **Kill shot:** **Valid — KEPT.** It helps. One of the few filters that survived
- **Lesson:** This one works because it respects regime, not counter-trend

### F3. Distance-from-High
- **What:** Block entry if within 1% of 60d high / 0.5% of 20d high
- **Why promising:** Avoid buying at tops
- **Kill shot:** **Valid — KEPT.** It's a **trade-quality/turnover/cost filter**, not a return predictor. Removing it FAILS at 3× fees
- **Lesson:** Some filters "earn their place" under costs even if they don't predict direction

### F4. V12 New Moon MACD Entry (strategy.py)
- **What:** See A2 above
- **Why promising:** New Moon edge
- **Kill shot:** Neutral-to-negative. Rejected
- **Lesson:** Already covered in A2

---

## Category G: Data/Look-ahead Issues

### G1. Look-ahead Bias in DIVergence V2 (FIXED 22 July)
- **What:** Divergence state activated at pivot bar p2, but pivot needs p2+3 to be confirmed
- **Why it mattered:** Strategy "saw" divergences ~3 bars early → inflated Sharpe 6.08→2.998
- **Kill shot:** **FIXED** — pivot_right=3 shift applied everywhere
- **Lesson:** Pivot-based detectors must compensate for confirmation delay. Always check if the signal was "knowable at bar i"

---

## Summary: Why Things Die

| Cause | Count | Examples |
|-------|:-----:|----------|
| **Edge < friction** (costs beat signal) | ~10 | 1m scalp, overnight options, PEAD long-short |
| **2-year sample lies** (regime artifact) | ~5 | Profit-target, MTF options funnel, ADX gate |
| **Overfit / curve-fit** | ~4 | up_ratio peak, astro nakshatra, V12 entry |
| **Counter-trend mis-compose** | ~3 | Trend-gate, MTF alignment, distance-on-momentum |
| **Structurally incompatible** | ~3 | V11 div on strategy.py, correlation gate |
| **Inert / decoration** | ~2 | PT 5%, yearly-anchor |
| **Not reproducible** | ~2 | 5m unified, 1m scalp (withdrawn claim) |
| **Zero impact** | ~1 | V11 divergence on strategy.py |
| **Not completed** | ~1 | V13 MACD filter |

> **Total: 30+ hypotheses, 3 accepted.** The acceptance rate (~10%) is normal for serious quant research.
> The 3 that survived are: **MACD Momentum** (core edge), **V2 Divergence** (exit enhancer), **Loss-2→2x sizing** (risk scaler).

---

*Generated by Buffy on 22 July 2026 | #MarketMantri*
