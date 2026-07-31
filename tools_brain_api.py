#!/usr/bin/env python3
"""
tools_brain_api.py — WorldQuant BRAIN API system test.

End-to-end check that we can drive platform.worldquantbrain.com from code
instead of by hand: authenticate -> submit one simulation (Alpha 1 from
docs/research/BRAIN_ALPHA_DRAFTS.md) -> poll -> print the IS metrics.

Credentials are read from the environment, never hard-coded:
    export BRAIN_EMAIL='you@example.com'
    export BRAIN_PASSWORD='...'
    python3 tools_brain_api.py                 # runs Alpha 1
    python3 tools_brain_api.py --auth-only      # just prove login works
    python3 tools_brain_api.py --expr 'rank(-returns)'   # custom alpha

No secrets are written to disk or logged. Biometric/persona accounts are
detected and the required URL is printed rather than failing silently.
"""
import os
import sys
import time
import json
import argparse
import urllib.request
import urllib.error
import base64

API = "https://api.worldquantbrain.com"

# Alpha 1 — MACD momentum, cross-sectional (from BRAIN_ALPHA_DRAFTS.md).
ALPHA1 = (
    "macd = ts_mean(close, 12) - ts_mean(close, 26);"
    "signal = ts_mean(macd, 9);"
    "hist = macd - signal;"
    "rank(hist) + rank(ts_delta(hist, 3))"
)

SETTINGS = {
    "instrumentType": "EQUITY",
    "region": "USA",
    "universe": "TOP3000",
    "delay": 1,
    "decay": 4,
    "neutralization": "SUBINDUSTRY",
    "truncation": 0.08,
    "pasteurization": "ON",
    "unitHandling": "VERIFY",
    "nanHandling": "OFF",
    "language": "FASTEXPR",
    "visualization": False,
}


def _req(method, url, token=None, body=None, basic=None):
    """Minimal HTTP with clear errors. Returns (status, headers, parsed_body)."""
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Cookie", token)
    if basic:
        r.add_header("Authorization", "Basic " + base64.b64encode(basic.encode()).decode())
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            raw = resp.read().decode() or "{}"
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"_raw": raw}
            return resp.status, dict(resp.headers), parsed
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {"_raw": raw}
        return e.code, dict(e.headers), parsed


def authenticate(email, password):
    """POST /authentication with HTTP Basic. Returns the session Cookie header."""
    status, headers, body = _req("POST", API + "/authentication", basic=f"{email}:{password}")
    if status == 201:
        cookie = headers.get("Set-Cookie", "")
        if not cookie:
            sys.exit("✗ authenticated (201) but no Set-Cookie returned — cannot hold session.")
        # keep only the token pair before the first ';'
        return cookie.split(";")[0]
    if status == 401:
        wa = headers.get("WWW-Authenticate", "")
        if "persona" in wa.lower():
            loc = body.get("location") if isinstance(body, dict) else None
            sys.exit("✗ account needs biometric/persona verification.\n"
                     f"   Open this in a browser, complete it, then re-run:\n   {loc or wa}")
        sys.exit("✗ 401 — wrong BRAIN_EMAIL / BRAIN_PASSWORD.")
    sys.exit(f"✗ unexpected auth status {status}: {body}")


def whoami(cookie):
    status, _, body = _req("GET", API + "/authentication", token=cookie)
    return status, body


def simulate(cookie, expr):
    """Submit one REGULAR simulation, poll to completion, return the alpha id."""
    payload = {"type": "REGULAR", "settings": SETTINGS, "regular": expr}
    status, headers, body = _req("POST", API + "/simulations", token=cookie, body=payload)
    if status != 201:
        sys.exit(f"✗ simulation submit failed ({status}): {body}")
    loc = headers.get("Location")
    if not loc:
        sys.exit("✗ no Location header on the simulation — cannot poll.")
    print(f"  submitted → polling {loc}")
    for _ in range(120):  # up to ~10 min
        status, headers, body = _req("GET", loc, token=cookie)
        retry = headers.get("Retry-After")
        if retry:
            time.sleep(float(retry))
            continue
        if status == 200:
            alpha_id = body.get("alpha")
            if not alpha_id:
                sys.exit(f"✗ simulation finished but no alpha id: {body}")
            return alpha_id
        sys.exit(f"✗ polling returned {status}: {body}")
    sys.exit("✗ simulation timed out after ~10 min.")


def fetch_metrics(cookie, alpha_id):
    status, _, body = _req("GET", API + f"/alphas/{alpha_id}", token=cookie)
    if status != 200:
        sys.exit(f"✗ could not fetch alpha {alpha_id} ({status}): {body}")
    return body.get("is", {})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auth-only", action="store_true", help="just verify login")
    ap.add_argument("--expr", default=ALPHA1, help="alpha expression (default: Alpha 1)")
    args = ap.parse_args()

    email = os.environ.get("BRAIN_EMAIL")
    password = os.environ.get("BRAIN_PASSWORD")
    if not email or not password:
        sys.exit("✗ set BRAIN_EMAIL and BRAIN_PASSWORD in the environment first.")

    print("1) authenticating…")
    cookie = authenticate(email, password)
    st, who = whoami(cookie)
    user = (who.get("user") or {}).get("id", "?") if isinstance(who, dict) else "?"
    print(f"   ✓ logged in (session verify {st}, user {user})")
    if args.auth_only:
        print("   --auth-only: system reachable and login works. Done.")
        return

    print("2) submitting simulation (Alpha 1)…")
    alpha_id = simulate(cookie, args.expr)
    print(f"   ✓ alpha {alpha_id}")

    print("3) metrics:")
    m = fetch_metrics(cookie, alpha_id)
    for k in ("sharpe", "fitness", "turnover", "returns", "drawdown", "margin"):
        if k in m:
            print(f"     {k:9} {m[k]}")
    print(f"\n   full IS block: {json.dumps(m, indent=2)}")


if __name__ == "__main__":
    main()
