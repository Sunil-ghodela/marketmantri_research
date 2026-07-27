"""
data_sources/kite.py — Zerodha Kite Connect historical data fetcher.

Handles:
  - Interactive daily login flow (request_token → access_token, persisted to .env)
  - Instrument token lookup (NIFTYBEES equity, NIFTY 50 index)
  - Paginated historical fetch respecting Kite's per-interval day limits:
        minute:     60 days / req
        3/5/10min:  100 days / req
        15/30min:   200 days / req
        60min+:     400 days / req
        day/week:   2000 days / req
  - Safe throttling (Kite SDK enforces 3 req/sec; we add 0.4s sleep between calls)
  - Returns a dataframe with columns: date (UTC), open, high, low, close, volume

Does NOT run live; only historical fetch for backtest caching.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

import pandas as pd
import pytz
from dotenv import load_dotenv, set_key
from tqdm import tqdm

IST = pytz.timezone("Asia/Kolkata")

# Kite returns datetimes in IST; we convert to UTC for storage.
PAGINATION_DAYS = {
    "minute": 60,
    "2minute": 60,
    "3minute": 100,
    "4minute": 100,
    "5minute": 100,
    "10minute": 100,
    "15minute": 200,
    "30minute": 200,
    "60minute": 400,
    "hour": 400,
    "2hour": 400,
    "3hour": 400,
    "4hour": 400,
    "day": 2000,
    "week": 2000,
}

# How far back we'll attempt to walk before giving up (empty response or error).
MAX_LOOKBACK_YEARS = 10


class KiteDataSource:
    """Wraps kiteconnect for the narrow use-case of bulk historical fetch."""

    def __init__(self, env_path: str | Path = ".env"):
        try:
            from kiteconnect import KiteConnect
        except ImportError as e:
            raise RuntimeError(
                "kiteconnect not installed. Run `pip install kiteconnect`."
            ) from e

        self.env_path = Path(env_path).resolve()
        load_dotenv(self.env_path)

        api_key = os.environ.get("KITE_API_KEY")
        if not api_key:
            raise RuntimeError(
                f"KITE_API_KEY not set. Copy .env.example to .env and fill it in."
            )

        self.kite = KiteConnect(api_key=api_key)
        self.api_secret = os.environ.get("KITE_API_SECRET", "")
        self.access_token = os.environ.get("KITE_ACCESS_TOKEN", "")

        if self.access_token:
            self.kite.set_access_token(self.access_token)

        self._instruments_cache: dict[str, pd.DataFrame] = {}

    # ── Login flow ──────────────────────────────────────────────────────────
    def login(self) -> None:
        """
        Interactive login — prints the Kite login URL, asks user to paste back
        the redirect URL containing the request_token, exchanges it for an
        access_token, and persists to .env.
        """
        if not self.api_secret:
            raise RuntimeError("KITE_API_SECRET not set in .env")

        login_url = self.kite.login_url()
        print()
        print("=" * 72)
        print("Kite Connect login required.")
        print(f"Open this URL in your browser and log in:")
        print(f"  {login_url}")
        print()
        print("After login you'll be redirected to your registered redirect URL,")
        print("which will look like:")
        print("  https://your-redirect/?request_token=XXXXXX&action=login&status=success")
        print()
        print("Copy the FULL redirect URL (or just the request_token value) and paste below.")
        print("=" * 72)
        raw = input("Paste redirect URL or request_token: ").strip()

        if "request_token=" in raw:
            # Extract from the URL
            import urllib.parse
            parsed = urllib.parse.urlparse(raw)
            params = urllib.parse.parse_qs(parsed.query)
            request_token = params.get("request_token", [""])[0]
        else:
            request_token = raw

        if not request_token:
            raise RuntimeError("No request_token found in pasted input")

        print("Exchanging request_token for access_token...")
        session = self.kite.generate_session(request_token, api_secret=self.api_secret)
        self.access_token = session["access_token"]
        self.kite.set_access_token(self.access_token)

        # Persist to .env
        set_key(str(self.env_path), "KITE_ACCESS_TOKEN", self.access_token)
        print(f"Access token persisted to {self.env_path}")
        print(f"Token valid until end of today's trading day.")

    def ensure_logged_in(self, force: bool = False) -> None:
        """Login if we have no access token, or if the existing one is rejected."""
        if force or not self.access_token:
            self.login()
            return
        try:
            self.kite.profile()  # cheap call to validate token
        except Exception as e:
            print(f"Existing access_token rejected ({e}); re-running login flow")
            self.login()

    # ── Instrument lookup ───────────────────────────────────────────────────
    def _load_instruments(self, exchange: str) -> pd.DataFrame:
        if exchange in self._instruments_cache:
            return self._instruments_cache[exchange]
        raw = self.kite.instruments(exchange)
        df = pd.DataFrame(raw)
        self._instruments_cache[exchange] = df
        return df

    def instrument_token(self, symbol: str, exchange: str = "NSE") -> int:
        """Look up an instrument token by tradingsymbol. Case-insensitive match."""
        df = self._load_instruments(exchange)
        # NIFTY 50 index is tricky — it lives as 'NIFTY 50' with segment INDICES
        match = df[df["tradingsymbol"].str.upper() == symbol.upper()]
        if len(match) == 0:
            # Try partial/contains match for indices
            match = df[df["name"].str.upper() == symbol.upper()]
        if len(match) == 0:
            raise RuntimeError(
                f"Instrument {symbol!r} not found on exchange {exchange!r}. "
                f"Sample rows: {df.head(3).to_dict('records')}"
            )
        if len(match) > 1:
            # Prefer the cash equity row over any derivatives
            cash = match[match.get("segment", "") == "NSE"]
            if len(cash):
                match = cash
        return int(match.iloc[0]["instrument_token"])

    # ── Historical fetch ────────────────────────────────────────────────────
    def fetch(
        self,
        symbol: str,
        interval: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        exchange: str = "NSE",
    ) -> pd.DataFrame:
        """
        Paginated historical fetch walking backwards from `end` to `start`.

        If start is None, walks back until Kite returns empty (or MAX_LOOKBACK_YEARS).
        If end is None, uses today.

        Returns a DataFrame sorted by date ascending with UTC-aware 'date' column
        and open/high/low/close/volume.
        """
        if interval not in PAGINATION_DAYS:
            raise ValueError(f"Unsupported interval {interval!r}")

        token = self.instrument_token(symbol, exchange=exchange)
        chunk_days = PAGINATION_DAYS[interval]

        if end is None:
            end = datetime.now(IST).replace(hour=23, minute=59, second=0, microsecond=0).replace(tzinfo=None)
        if start is None:
            start = end - timedelta(days=365 * MAX_LOOKBACK_YEARS)

        # Walk backwards in `chunk_days` windows
        chunks: list[pd.DataFrame] = []
        cursor_end = end
        empty_streak = 0

        pbar = tqdm(
            desc=f"kite fetch {symbol} {interval}",
            unit="chunk",
            total=None,
        )
        while cursor_end > start:
            cursor_start = max(cursor_end - timedelta(days=chunk_days), start)
            try:
                rows = self.kite.historical_data(
                    instrument_token=token,
                    from_date=cursor_start,
                    to_date=cursor_end,
                    interval=interval,
                )
            except Exception as e:
                print(f"\nKite API error on chunk {cursor_start.date()} → {cursor_end.date()}: {e}")
                break

            if not rows:
                empty_streak += 1
                if empty_streak >= 3:
                    # Three empty chunks in a row — we've walked past the instrument's history
                    pbar.write(f"  Stopped at {cursor_end.date()} (3 empty chunks, likely pre-listing)")
                    break
            else:
                empty_streak = 0
                chunks.append(pd.DataFrame(rows))

            pbar.update(1)
            pbar.set_postfix_str(f"{cursor_start.date()} → {cursor_end.date()}  rows={sum(len(c) for c in chunks):,}")

            cursor_end = cursor_start - timedelta(seconds=1)
            time.sleep(0.4)  # stay well under Kite's 3 req/s limit
        pbar.close()

        if not chunks:
            raise RuntimeError(
                f"No data fetched for {symbol} {interval}. Check instrument exists and Kite has history."
            )

        df = pd.concat(chunks, ignore_index=True)
        df = df.rename(columns={"date": "date"})  # already named 'date' from Kite

        # Kite returns tz-aware IST timestamps; normalize to UTC
        if df["date"].dt.tz is None:
            df["date"] = df["date"].dt.tz_localize(IST)
        df["date"] = df["date"].dt.tz_convert("UTC")

        # Dedupe and sort
        df = df.drop_duplicates(subset=["date"]).sort_values("date").reset_index(drop=True)
        df = df[["date", "open", "high", "low", "close", "volume"]]

        return df
