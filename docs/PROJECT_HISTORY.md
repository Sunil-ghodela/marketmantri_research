# MarketMantri — Project History (Phase 1: research → deployed edge)

> The 3-month journey of an autonomous NSE strategy-research loop, from a single curve-fit dip-buyer to a
> deployed, robust momentum edge running live on the cloud. Written 2026-06-27, at the Phase-1 / Phase-2 boundary.
> The discipline is the story: **every idea tested net-of-cost, out-of-sample, on both halves — and most were
> honestly rejected. The few that survived are the edge.**

## The two strategies (what we ended with)

| | **strategy.py** (the foundation) | **momentum basket** (the deployed edge) |
|--|--|--|
| Logic | Pullback dip-buy in uptrend (EMA + up_ratio + PT) + 5-6 gates | 1H MACD(12/26/5) cross + bearish-divergence exit |
| Instrument | NIFTYBEES 15m | 90-stock basket, K=15 (+ now NIFTY/BANKNIFTY indices) |
| Sharpe | 1.801 (NIFTYBEES) | ~1.9-1.97 stock-median · **NIFTY 2.05, DD 7%** · BANKNIFTY 1.95 |
| Robustness | **FRAGILE** — up_ratio=20 is a sharp overfit peak; astro-nakshatra gate curve-fit | **ROBUST** — every param a smooth plateau; defaults chosen for fee-robustness, not gross-max |
| Status | the older foundation — taught us, not the thing to lean on | **LIVE on VPS** (basket 24/7 + NIFTY momentum dashboard) |

## Timeline

- **~2026-04-12 — start.** Autonomous research loop on strategy.py (9-layer dip-buy, Sharpe 1.801). 55-trade manual
  review → 3 structural insights (long-only gap, month-structure, distance×regime).
- **April–May — strategy.py at its ceiling.** Probe after probe REJECTED with numbers: 1m ports, intraday
  trend-window, 6-TF MTF alignment, month-anchor breakout, short-extension, meta-labeling (Track-3 ML), yearly-anchor
  (feature not filter), Version C 1m. Lesson: strategy.py's 1.801 is a local ceiling; counter-trend filters
  mis-compose with everything. Pitch path locked with the capital partner — 1-month paper trade requested.
- **Mid-June — the breakthrough: momentum generalizes.** strategy_macd_momentum tested on 10→59 NIFTY stocks →
  median net Sharpe ~1.9, robust across the universe (NOT a NIFTYBEES curve-fit). Exit-Lab tuning (divergence recency
  15→6, entry MACD signal 9→5) lifted it to 1.97, holdout 2.38, surviving 3× fees. Market-Phase panel + live paper
  dashboard built.
- **June 20–25 — hunting a second edge, finding mostly graveyard.** Crash/tail stress (~13% worst-case, contained
  by K-cap). Overnight drift (found a real gap edge — then DIED on real option fills / cash tail). 1m divergence
  scalp (breakeven on 2yr). Higher-TF trend-gate (rejected). Uncorrelated diversifiers (gold/silver/FANG/crypto —
  diversification real but modest +6%, parked; crypto killed by India TDS). **VPS deployment** — momentum basket
  live 24/7 at hearth.tranquilwaters.in/basket/.
- **June 26 — the strategy X-ray + the index find.** Fresh-frame market survey (most "edges" = traps). PEAD tested →
  survivorship illusion, rejected. Strategy internals audit: momentum core ROBUST, strategy.py FRAGILE (up_ratio
  overfit, astro curve-fit). Two-strategy combine (momentum + dip-buy, uncorrelated 0.14) → honest +11%, parked.
  MTF candle ideas all rejected (2-year samples lie). **Momentum works on the INDICES: NIFTY 2.05, BANKNIFTY 1.95.**
- **June 27 — Phase-1 close.** NIFTY momentum auto paper-trade dashboard built + deployed to VPS (chart with trade
  markers, timeframe toggle). Repo consolidated, merged to main. **Phase 2 begins.**

## The graveyard (honestly rejected — this IS the moat)

overnight drift/options · 1m divergence scalp · 1m ports · trend-window · 6-TF MTF alignment · month-anchor ·
short-extension · meta-labeling (ML) · yearly-anchor-as-filter · Version C 1m · higher-TF trend-gate ·
correlation-gate · PEAD · MTF candle funnel · NIFTY option-direction · uncorrelated-diversifier basket (parked) ·
two-strategy combine (parked). **Every one tested, every one closed with numbers.** A pitch that says "I tested
everything and *this* survived" beats an untested idea a hundred times over.

## The lessons (the research discipline)

1. **The Wall:** an edge must beat baseline on BOTH halves AND survive 3× fees before it's believed.
2. **Edge < friction kills most things** — high per-signal edge means nothing if turnover/cost/theta eats it.
3. **2-year samples lie** — regime artifacts (the NIFTY option "bear edge" reversed on 10yr; overnight basket Sharpe
   2.48 was frequency-inflated).
4. **Beware inflation traps** — survivorship (PEAD), cash-time (portfolio sims read 5.25 not the real ~1.9),
   modeled-option fills (overnight 2.87 → −1.78 real).
5. **Counter-trend filters mis-compose with momentum** — trend-gate, MTF-alignment, distance-on-momentum all hurt.
6. **Robust beats optimal** — the momentum defaults were chosen for fee-robustness, not the gross-max peak; that's
   why they generalize where strategy.py's tuned-to-a-peak up_ratio does not.

## Phase 2 (what's next)

Forward paper record (basket + NIFTY momentum, live on VPS) · the partner pitch (basket) · CE/PE option-economics
for the NIFTY signal (separate, manual) · longer-history index-futures validation via Kite · keep the discipline.
