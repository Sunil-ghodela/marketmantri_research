"""Counterfactual: would the divergence exit have front-run the losing MACD-cross exits?

Divergence sits ABOVE max-hold and BELOW MACD-cross in the exit priority, and it fires when
momentum diverges from price — i.e. before the MACD actually crosses back. So for each
archived trade, walk its holding window bar by bar and find the first 1H bar where div_state
would have been "bearish". Compare exiting there against what actually happened.

This is a COUNTERFACTUAL on historical bars, not a forward result. Two known approximations:
  * the archived record's bar labels are timezone-mixed, so trades are matched to bars by
    DATE range rather than exact timestamp
  * div_state is evaluated on the trailing 7d slice production would have had at that bar
"""
import collections
import json
import pickle
import sys

sys.path.insert(0, ".")
import os
import tempfile
os.environ["MOMENTUM_STATE_FILE"] = os.path.join(tempfile.mkdtemp(), "cf.json")

import pandas as pd
from core import momentum_portfolio_feed as FEED

arch = json.load(open("./archive/basket_forward_20260622_20260722.json"))
bars = pickle.load(open("/tmp/replay_bars.pkl", "rb"))
WINDOW = pd.Timedelta(days=7)

rows = []
skipped = 0

for t in arch["trades"]:
    sym = t["stock"]
    df = bars.get(sym)
    if df is None:
        skipped += 1
        continue
    ed, xd = t["entry_date"], t["exit_time"][:10]
    entry = t["entry_price"]
    # 1H bars strictly inside the holding window (entry date .. exit date)
    h = df["Close"].resample("1h").last().dropna()
    grid = [ts for ts in h.index if ed <= str(ts)[:10] <= xd]
    if not grid:
        skipped += 1
        continue

    first_bear_px, first_bear_ts = None, None
    for ts in grid:
        sl = df[(df.index > ts - WINDOW) & (df.index <= ts)]
        if len(sl) < 100:
            continue
        FEED._DIV_CACHE.clear()
        if FEED._compute_div_state(sl) == "bearish":
            first_bear_px, first_bear_ts = float(sl["Close"].iloc[-1]), ts
            break

    actual_pct = t["pnl_pct"]
    if first_bear_px is None:
        rows.append((t, None, actual_pct, actual_pct))
    else:
        cf_pct = (first_bear_px - entry) / entry * 100 if entry else 0.0
        rows.append((t, str(first_bear_ts)[:16], actual_pct, round(cf_pct, 2)))

print("trades analysed: %d (skipped %d — no bars)" % (len(rows), skipped))
print()

for reason in ("MACD Cross", "Stop Loss", "Max Hold"):
    sub = [r for r in rows if r[0]["exit_reason"] == reason]
    if not sub:
        continue
    hit = [r for r in sub if r[1] is not None]
    act = sum(r[2] for r in sub)
    cf = sum(r[3] for r in sub)
    print("=== %s (n=%d) ===" % (reason, len(sub)))
    print("  divergence would have fired first in : %d of %d (%.0f%%)"
          % (len(hit), len(sub), 100.0 * len(hit) / len(sub)))
    print("  sum pnl_pct  actual %+8.2f%%   ->  with div-exit %+8.2f%%   (delta %+.2f pp)"
          % (act, cf, cf - act))
    if hit:
        better = sum(1 for r in hit if r[3] > r[2])
        print("  of those %d, exiting on divergence was better in %d (%.0f%%)"
              % (len(hit), better, 100.0 * better / len(hit)))
    print()

tot_act = sum(r[2] for r in rows)
tot_cf = sum(r[3] for r in rows)
print("=== WHOLE RECORD (unweighted pnl_pct) ===")
print("  actual        : %+.2f%%" % tot_act)
print("  with div-exit : %+.2f%%   (delta %+.2f pp)" % (tot_cf, tot_cf - tot_act))
wins_a = sum(1 for r in rows if r[2] > 0)
wins_c = sum(1 for r in rows if r[3] > 0)
print("  win rate      : %.1f%%  ->  %.1f%%"
      % (100.0 * wins_a / len(rows), 100.0 * wins_c / len(rows)))
