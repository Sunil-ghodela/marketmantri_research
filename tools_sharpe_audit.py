"""Audit the 2.998 basket Sharpe: annualisation, and how much of it is 46-way diversification
the live K=15 engine cannot have.
"""
import numpy as np
import pandas as pd

df = pd.read_csv("basket_100_portfolio_returns.csv")
df["date"] = pd.to_datetime(df["date"])
stocks = [c for c in df.columns if c not in ("date", "portfolio_return", "portfolio_equity")]
R = df.set_index("date")[stocks]

print("stocks: %d | rows: %d | span %s -> %s (%.2f yrs)"
      % (len(stocks), len(R), R.index.min().date(), R.index.max().date(),
         (R.index.max() - R.index.min()).days / 365.25))


def sharpe(series, periods_per_year=252.0):
    s = series.dropna()
    return float(s.mean() / s.std() * np.sqrt(periods_per_year)) if s.std() > 0 else 0.0


port = R.mean(axis=1)
print()
print("=== 1. reproduce the published number ===")
print("  as published (46 names, sqrt(252))      : %.4f" % sharpe(port))

# annualisation on the true trading-day grid: reindex onto NSE business days, flat days = 0
grid = pd.bdate_range(R.index.min(), R.index.max())
port_grid = port.reindex(grid).fillna(0.0)
print("  reindexed onto %d business days         : %.4f" % (len(grid), sharpe(port_grid)))
print("  (exit-date rows %d vs business days %d -> factor %.3f)"
      % (len(R), len(grid), np.sqrt(len(grid) / len(R))))

print()
print("=== 2. how much is 46-way diversification? ===")
rng = np.random.default_rng(7)
for k in (46, 30, 20, 15, 10, 5, 1):
    if k == 46:
        vals = [sharpe(R.mean(axis=1))]
    else:
        vals = []
        for _ in range(300):
            pick = rng.choice(stocks, size=k, replace=False)
            vals.append(sharpe(R[list(pick)].mean(axis=1)))
    v = np.array(vals)
    print("  K=%-3d  median Sharpe %.2f   (p10 %.2f  p90 %.2f)"
          % (k, np.median(v), np.percentile(v, 10), np.percentile(v, 90)))

print()
print("=== 3. per-stock Sharpe distribution (what one name actually earns) ===")
per = pd.Series({s: sharpe(R[s].replace(0.0, np.nan)) for s in stocks}).sort_values()
print("  median %.2f | p25 %.2f | p75 %.2f | min %.2f | max %.2f"
      % (per.median(), per.quantile(.25), per.quantile(.75), per.min(), per.max()))
print("  NOTE: computed on each stock's own exit days only (0-days dropped), so this is the")
print("        per-trade-ish figure, not comparable to the portfolio number above.")

print()
print("=== 4. concurrency the backtest implies ===")
active = (R != 0).sum(axis=1)
print("  stocks closing a trade on the same day: mean %.2f  median %.0f  max %d"
      % (active.mean(), active.median(), active.max()))
print("  days with >15 simultaneous closes: %d of %d (%.1f%%)"
      % ((active > 15).sum(), len(active), 100.0 * (active > 15).sum() / len(active)))
