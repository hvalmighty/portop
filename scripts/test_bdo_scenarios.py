#!/usr/bin/env python3
"""End-to-end check of the three BDO TIG sample portfolios against a running mPower server.

Uses only the Python standard library. Read-only by default; the flags below change state.

    python scripts/test_bdo_scenarios.py                                  # local server on :8000
    python scripts/test_bdo_scenarios.py --base-url https://portop-three.vercel.app
    python scripts/test_bdo_scenarios.py --propose                        # PM proposes optimised DRAFT versions
    python scripts/test_bdo_scenarios.py --approve                        # compliance checker approves the seeded draft

Password defaults to MPOWER_DEMO_PASSWORD or Mpower@2026!.
Exit code 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

CODES = ["BDO-PEQ", "BDO-GEQ", "BDO-HTF"]
RESULTS: list[tuple[str, bool, str]] = []


def call(base: str, method: str, path: str, token: str | None = None, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.loads(exc.read() or b"{}")
        except ValueError:
            return exc.code, {}


def login(base: str, user: str, password: str) -> str:
    data = f"username={user}&password={password}".encode()
    req = urllib.request.Request(base + "/api/v1/auth/login", data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())["access_token"]


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  - {detail}" if detail else ""))


def pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--password", default=os.environ.get("MPOWER_DEMO_PASSWORD", "Mpower@2026!"))
    ap.add_argument("--propose", action="store_true", help="PM proposes the optimised weights as DRAFT versions")
    ap.add_argument("--approve", action="store_true", help="compliance checker approves the seeded BDO-PEQ draft")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    print(f"Server: {base}")
    try:
        pm = login(base, "pm.santos", args.password)
        cruz = login(base, "compliance.cruz", args.password)
        viewer = login(base, "viewer", args.password)
    except Exception as exc:  # noqa: BLE001
        print(f"Cannot sign in ({exc}). Is the server up, and is the password right?")
        return 1
    check("sign in as PM, compliance and viewer", True)

    print("\n1. Configuration")
    st, models = call(base, "GET", "/api/v1/models", pm)
    by_code = {m["code"]: m for m in models} if st == 200 else {}
    for code in CODES:
        m = by_code.get(code)
        check(f"{code} exists with a mandate", bool(m and m.get("mandate", {}).get("universe")))
        if m:
            md = m["mandate"]
            print(f"      {m['name']}: {md['currency']}, {len(md['universe'])} securities, "
                  f"cap {md['max_weight_pct']:g}% ({md['max_weight_basis']}), goal +{md['excess_return_bps']} bps "
                  f"vs {m['benchmark']}")

    print("\n2. Optimisation against each mandate")
    results = {}
    for code in CODES:
        st, res = call(base, "POST", f"/api/v1/models/{code}/optimise", pm)
        check(f"{code} optimise returns 200", st == 200, f"HTTP {st}")
        if st != 200:
            continue
        results[code] = res
        if not res.get("feasible"):
            check(f"{code} goal achievable", False, res.get("message", ""))
            continue
        check(f"{code} goal achievable and met", bool(res["goal_met"]),
              f"excess {res['excess_return_bps']:.1f} bps vs goal {res['goal_bps']} bps")
        check(f"{code} position cap respected", bool(res["cap_respected"]),
              f"largest weight {res['max_position_pct']:.2f}% vs cap {res['max_weight_pct']:g}%")
        total = sum(res["weights"].values())
        check(f"{code} weights sum to 100", abs(total - 100) <= 0.01, f"sum {total:.2f}")
        print(f"      benchmark return {pct(res['benchmark_return'])}, target {pct(res['target_return'])}, "
              f"portfolio {pct(res['exp_return'])}, volatility {pct(res['volatility'])}")
        print(f"      best achievable excess: {res['max_achievable_excess_bps']:.0f} bps")
        for sym, w in sorted(res["weights"].items(), key=lambda kv: -kv[1]):
            print(f"        {sym:<14}{w:>7.2f}%")
        if res["firm_limit_breaches"]:
            print(f"      WARNING: above the firm-wide 20% single-position soft limit (INT-POS-20): "
                  f"{', '.join(res['firm_limit_breaches'])}. Compliance will flag these as soft breaches.")

    print("\n3. Role access")
    st, _ = call(base, "POST", "/api/v1/models/BDO-PEQ/optimise", cruz)
    check("compliance cannot run the optimiser", st == 403, f"HTTP {st}")
    st, _ = call(base, "POST", "/api/v1/models/BDO-PEQ/optimise", viewer)
    check("viewer cannot run the optimiser", st == 403, f"HTTP {st}")

    print("\n4. Mandate enforcement on proposals")
    st, body = call(base, "POST", "/api/v1/models/BDO-PEQ/versions", pm,
                    {"weights": {"AAPL": 50, "BDO": 50}, "rationale": "test: outside the universe"})
    check("PEQ rejects securities outside the universe", st == 422, f"HTTP {st}")
    st, body = call(base, "POST", "/api/v1/models/BDO-PEQ/versions", pm,
                    {"weights": {"BDO": 25, "SM": 15, "ALI": 10, "AC": 10, "JFC": 10, "TEL": 10, "ICT": 10, "MER": 10},
                     "rationale": "test: over the 20% cap"})
    check("PEQ rejects a weight above 20%", st == 422, f"HTTP {st}")

    print("\n5. Maker-checker on the seeded BDO-PEQ draft")
    st, peq = call(base, "GET", "/api/v1/models/BDO-PEQ", pm)
    draft = next((v for v in peq.get("versions", []) if v["status"] == "DRAFT"), None) if st == 200 else None
    if draft is None:
        print("  (no draft pending; already approved or not seeded)")
    else:
        v = draft["version"]
        st, _ = call(base, "POST", f"/api/v1/models/BDO-PEQ/versions/{v}/approve", pm)
        check("PM cannot approve their own draft", st == 403, f"HTTP {st}")
        if args.approve:
            st, _ = call(base, "POST", f"/api/v1/models/BDO-PEQ/versions/{v}/approve", cruz)
            check("compliance checker approves the draft", st == 200, f"HTTP {st}")

    if args.propose:
        print("\n6. Proposing optimised weights as DRAFT versions (PM)")
        for code, res in results.items():
            if res.get("feasible"):
                st, body = call(base, "POST", f"/api/v1/models/{code}/versions", pm,
                                {"weights": res["weights"],
                                 "rationale": f"Test run: optimised to the {code} mandate, goal met"})
                check(f"{code} draft version proposed", st == 201, f"HTTP {st}")

    failed = [name for name, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)} of {len(RESULTS)} checks passed.")
    if failed:
        print("Failed: " + "; ".join(failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
