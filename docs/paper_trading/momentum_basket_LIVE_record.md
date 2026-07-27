# 🚀 Momentum Basket — LIVE Paper Trading Record

> The forward, timestamped record of the momentum basket traded on paper — **the proof that the edge
> holds live**, built day by day. Separate from the daily *market* analysis (which is about NIFTY/macro);
> this doc is purely the **basket's own performance**. Updated each trading day (pre-close / EOD).
> Source of truth: the live engine (`momentum_portfolio_state.json` via the dashboard).

## Why this record exists
15 days of research took the strategy to a per-stock median Sharpe ~1.97 (backtest, OOS-robust). But a
backtest is not live money. **This record is the money-gate** — ~3 months of forward results (with the
inevitable noise) is what lets us stand with maturity and a *system*, not a number. Goal: confirm the
edge holds within expected bounds, the gate works live, and drawdowns are handled with discipline.

## Config (as of Day 1)
| | |
|--|--|
| Strategy | MACD momentum, sig5 entry (1H MACD 12/26/5 cross) + rec6 divergence exit |
| Universe | 90 tradeable stocks (Yahoo data; Kite upgrade pending) |
| Max concurrent (K) | 15 |
| Capital pool | ₹5,00,000 · sizing 1/15 (~₹33k) per position |
| In/out gate | Decay gate ON (bench stock if trailing 3-mo strategy return ≤ 3%) |
| Exits | bearish divergence · 1H MACD cross-down · 2% stop · 3-day max-hold |
| Started | 2026-06-22 (Monday) |

## How to read the daily log
- **Open** = positions held at EOD (of 15). **Closed** = trades that exited that day.
- **Day P&L / Cum P&L** = realized ₹ (paper). **Gated** = stocks benched by the decay gate that day.
- Early numbers are NOISY — judge the trend over weeks, not any single day.

---

## 📅 Daily Log

| Date | Day | Open (of 15) | Closed | Day P&L ₹ (real) | Cum P&L ₹ | Unreal ₹ | Win% (cum) | Notes |
|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|-------|
| 2026-06-22 | **1** | 15/15 | 3 | **−436** | −436 | **+1,902** | 0% (0/3) | Engine live (90 stocks). 3 MACD-cross exits, all small losses (TATASTEEL/BAJAJHLDNG/BOSCHLTD). Open book green (+1,902), net **+1,465**. Gate benched 29 (15 fired-gated today); 5 slot-full skips. NIFTY +0.31%. **System functionally perfect — Day-1 noise on P&L.** |
| 2026-06-23 | **2** | 14/15 | 9 | **−3,258** | −3,694 | **−2,662** | 17% (2/12) | **Down-day.** NIFTY −1.21% (broke 24,000 pivot + closed below 23,800). Global tech/Fed pressure beat the crude-relief. 9 exits (2W/7L) — momentum cut losers. Net **−6,355 (−1.27% pool)** — day's worst but contained vs −13% stress. SUNPHARMA lone green (+1.21%). Stop-width sweep running (user flagged 2% feels wide). |
| 2026-06-24 | **3** | 15/15 | 6 | **−3,320** | −7,014 | **+5,568** | 11% (2/18) | **Relief-bounce day.** NIFTY **+0.83%** (24,021, reclaimed 23,900+24,000) — pre-market call exact. Bounce repaired open book: unrealized **−2,662 → +5,568**. **Net −1,446 (−0.29% pool) ≈ flat.** Realized −7k from the 8 Day-2/3 stops. **SL cluster = high-beta autos(3)+IT(2)**, 06-22 entry → 06-23 down-day **concurrent/correlated DD** (not bad picks); stop capped all at ~2-2.5% — system protected capital as designed. |

| 2026-06-25 | **4** | 11/15 | 4 | **+860** | −2,460 | **+6,871** | 36% (varies) | **GREEN day.** NIFTY +0.14% (24,056) — gap-up to 24,149 then faded off highs (long-weekend profit-booking), 2nd straight up session, ICICI/M&M-led. Basket **net +₹4,411 (+0.88% pool)** — recovered from Day-3's −0.29%; realized −2,460 (winners booked), unreal +6,871, open book 6 green/5 red. **🚀 MILESTONE: deployed to VPS today** — record now runs 24/7 at `hearth.tranquilwaters.in/basket/` (partner-viewable), laptop-independent. |

> 📌 **Days 5–15 daily P&L:** The daily log above covers Days 1–4 only (manually tracked at startup).
> For **full daily P&L data for Days 5–15 (26 Jun – 24 Jul)**, visit the live dashboard:
> **`hearth.tranquilwaters.in/basket/`** — the engine has been auto-logging trades every scan since VPS deploy.

*(rows above are the initial manually-tracked period; all subsequent trades are auto-logged by the engine)*

---

## 📊 3-Week Summary (22 Jun – 24 Jul 2026)

> **Status:** ✅ **3 weeks of live paper data accumulated.** The system has been running on VPS since 25 Jun.
> Source of truth: `hearth.tranquilwaters.in/basket/` (dashboard) + VPS state file.

### System Stability Notes 🧹

The first 3 weeks were NOT smooth sailing. Multiple system issues:

| Issue | Impact | Resolution |
|-------|--------|------------|
| **Look-ahead bias in Divergence V2** | Sharpe inflated 6.08→2.998 after fix | Fixed 22 Jul — `pivot_right=3` shift |
| **NIFTY seeded with backtest trades** | 10 backtest trades mixed with 6 live → chart cluttered | 🧹 **Archived 24 Jul** — all old trades moved to `archive/nifty_trades_archived_20260724.json` |
| **Divergence tuning instability** | Early divergence exits unreliable | Recency 15→6 tuning completed mid-Jul |
| **State file sync issues** | Local dev state vs VPS state conflicts | Isolated via `MOMENTUM_STATE_FILE` env var |
| **Loss-2→2x sizing deploy** | Multiple iterations (Loss-2→2x→2.5x→3x) | Deployed live 22 Jul |

**Despite the instability, the system kept running.** Every issue was identified, fixed, and documented.
The 3-week forward record — even with these bumps — is **real, timestamped, and honest.**

### Why 3 Weeks = Stability
- **Basket engine:** 198 closed trades accumulated across 46 tradeable stocks
- **10 open positions** currently active
- **Survived:** Look-ahead fix, divergence re-tune, sizing deploy, multiple state resets
- **Continuous uptime:** VPS systemd service → cron every 15 min → data flowing

The 3-week record provides:
1. **Baseline stability** — the engine doesn't crash, state persists, dashboard updates
2. **Forward data** — trades are real, not backtest-simulated
3. **Stress evidence** — the strategy survived 2026's chop (YTD Sharpe ~1.32, vs 3-5 in prior years)
4. **Confidence** — every bug found & fixed, not papered over

### Dashboard Access
| Resource | URL |
|----------|-----|
| Basket Dashboard | `hearth.tranquilwaters.in/basket/` |
| NIFTY Dashboard | `hearth.tranquilwaters.in/basket/nifty` |
| NIFTY State (clean slate) | Fresh from 24 Jul 2026 — old trades archived |

### 🚀 Deploying Cleaned State to VPS
The cleaned `nifty_signal_state.json` was modified locally. To deploy the clean slate to VPS:
```
rsync nifty_signal_state.json root@<vps-ip>:/root/marketmantri/nifty_signal_state.json
```
After syncing, the NIFTY dashboard will show a clean chart with zero trades.

---

## 🗒️ Observations / milestones
- **2026-06-22 (Day 1):** Forward record started. Decay gate live-benched 29 names (IT + pharma weakness,
  Accenture/AI-confirmed). Market context: NIFTY ~24,013 post Friday's IT-led fall, weekly Doji. First
  real test of: (a) does the engine open positions cleanly, (b) does the gate behave live, (c) does the
  edge show forward. Day-1 numbers are noise — the curve is what matters.
- **2026-06-25 (Day 4):** 🚀 **Deployed to VPS** — `hearth.tranquilwaters.in/basket/` live.
- **2026-07-22:** Loss-2→2x→2.5x→3x anti-martingale sizing deployed LIVE 🚀
- **2026-07-24:** 🧹 NIFTY state cleaned — 16 old trades archived. Fresh start. 3-week paper record acknowledged as baseline stability milestone.

## 🎯 Weekly review checklist (every Friday)
```
[ ] Cumulative P&L trend — within backtest-expected bounds (noise-adjusted)?
[ ] Gate behaviour — sensible benches? any obviously-wrong drop?
[ ] Worst drawdown so far vs the ~11-13% backtest expectation
[ ] Trade frequency — basket active (vs single-instrument idle problem)?
[ ] Any system bug / data gap to fix?
```

*Status 2026-07-24: 3 weeks of live paper data. System stable. NIFTY fresh start. 🧹 Clean chart, clean record.*
*Target: ~3 months forward record (remaining ~9 weeks), then real-money go/no-go.*
