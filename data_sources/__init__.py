"""
Pluggable data source layer for autoresearch_india.

All data sources return a pandas DataFrame with columns:
    date (datetime64[ns, UTC]), open, high, low, close, volume

The date column is timezone-aware UTC. The backtest harness handles IST
conversion via session.py when it needs to reason about trading hours.
"""
