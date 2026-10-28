import io


def test_risk_account(client, auth):
    r = client.get("/api/v1/risk/accounts/PH-INC-01", headers=auth("risk.tan")).json()
    assert r["market"]["hist_var_99"] >= r["market"]["hist_var_95"] > 0
    assert r["rates"]["duration"] > 0
    rates = next(s for s in r["scenarios"] if s["scenario"] == "RATES_UP_100")
    assert rates["pnl"] < 0  # long-duration bond fund loses when rates rise


def test_stress_custom(client, auth):
    r = client.post("/api/v1/risk/stress", headers=auth("risk.tan"),
                    json={"accounts": ["PH-EQ-01"], "equity_pct": -10}).json()["results"][0]
    assert -11 < r["pnl_pct"] < -8


def test_optimizer_constraints(client, auth):
    syms = ["BDO", "SM", "ALI", "ICT", "RTB-2029", "FXTN-2031", "SMICPM-2030"]
    base = {"symbols": syms, "max_weight": 0.3}
    mv = client.post("/api/v1/optimize", headers=auth("pm.santos"), json=base | {"objective": "min_variance"}).json()
    ws = [w["weight"] for w in mv["weights"]]
    assert abs(sum(ws) - 1) < 1e-6 and max(ws) <= 0.3 + 1e-6
    assert mv["portfolio"]["volatility"] <= mv["equal_weight"]["volatility"] + 1e-9
    cb = client.post("/api/v1/optimize", headers=auth("pm.santos"), json=base | {
        "objective": "max_sharpe", "class_bounds": {"EQ": [40, 60]}}).json()
    eq = sum(w["weight"] for w in cb["weights"] if w["asset_class"] == "EQ")
    assert 0.4 - 1e-4 <= eq <= 0.6 + 1e-4
    assert len(cb["frontier"]) > 3


def test_model_versioning_and_rebalance(client, auth):
    m = client.get("/api/v1/models/PH-EQ", headers=auth("pm.santos")).json()
    w = dict(m["weights"])
    w["BDO"], w["CASH"] = w["BDO"] - 2, w["CASH"] + 2
    r = client.post("/api/v1/models/PH-EQ/versions", headers=auth("pm.santos"), json={"weights": w, "rationale": "Trim banks"})
    v = r.json()["versions"][0]["version"]
    assert client.post(f"/api/v1/models/PH-EQ/versions/{v}/approve", headers=auth("pm.santos")).status_code == 403
    r = client.post(f"/api/v1/models/PH-EQ/versions/{v}/approve", headers=auth("compliance.cruz")).json()
    assert r["active_version"] == v
    prev = client.post("/api/v1/rebalance/preview", headers=auth("pm.santos"),
                       json={"accounts": ["PH-EQ-01"], "mode": "full"}).json()["proposals"][0]
    assert prev["lines"] and prev["version"] == v
    sub = client.post("/api/v1/rebalance/submit", headers=auth("pm.santos"),
                      json={"accounts": ["PH-EQ-01"], "mode": "full"}).json()
    assert sub["orders_created"] > 0 and sub["batch_id"].startswith("RB-")


def test_bad_model_weights_rejected(client, auth):
    r = client.post("/api/v1/models/PH-EQ/versions", headers=auth("pm.santos"),
                    json={"weights": {"BDO": 50}, "rationale": "bad"})
    assert r.status_code == 422


def test_reconciliation_and_reports(client, auth):
    acct = client.get("/api/v1/portfolio/accounts/MULTI-06", headers=auth("ops.garcia")).json()
    lines = ["account,symbol,qty"] + [f"MULTI-06,{p['symbol']},{p['qty']}" for p in acct["positions"]]
    lines[1] = lines[1].rsplit(",", 1)[0] + ",1"  # introduce a break
    lines.append("MULTI-06,AAPL,10")
    f = {"file": ("custody.csv", io.BytesIO("\n".join(lines).encode()), "text/csv")}
    r = client.post("/api/v1/reconciliation", headers=auth("ops.garcia"), files=f).json()
    types = {b["type"] for b in r["breaks"]}
    assert {"QTY_MISMATCH", "MISSING_IN_BOOK"} <= types
    csv_r = client.get("/api/v1/reports/holdings.csv?entity=SG", headers=auth("ops.garcia"))
    assert csv_r.headers["content-type"].startswith("text/csv") and "MULTI-06" in csv_r.text
