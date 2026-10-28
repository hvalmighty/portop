def _order(client, h, **kw):
    body = {"account": "PH-BAL-02", "symbol": "BDO", "side": "BUY", "qty": 1000} | kw
    return client.post("/api/v1/orders", headers=h, json=body)


def test_maker_checker_flow_and_booking(client, auth):
    before = client.get("/api/v1/portfolio/accounts/PH-BAL-02", headers=auth("pm.santos")).json()
    qty0 = next(p["qty"] for p in before["positions"] if p["symbol"] == "BDO")
    r = _order(client, auth("trader.lim"))
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["status"] == "PENDING_APPROVAL" and o["compliance_status"] in ("PASS", "WARN")
    # maker cannot approve own order (trader lacks approve permission; PM self-approval tested below)
    assert client.post(f"/api/v1/orders/{o['id']}/approve", headers=auth("trader.lim")).status_code == 403
    r = client.post(f"/api/v1/orders/{o['id']}/approve", headers=auth("pm.reyes"))
    assert r.json()["status"] == "FILLED"
    after = client.get("/api/v1/portfolio/accounts/PH-BAL-02", headers=auth("pm.santos")).json()
    assert next(p["qty"] for p in after["positions"] if p["symbol"] == "BDO") == qty0 + 1000
    trades = client.get("/api/v1/trades?account=PH-BAL-02", headers=auth("ops.garcia")).json()
    assert trades[0]["order_id"] == o["id"]


def test_self_approval_blocked(client, auth):
    o = _order(client, auth("pm.santos"), qty=100).json()
    r = client.post(f"/api/v1/orders/{o['id']}/approve", headers=auth("pm.santos"))
    assert r.status_code == 403
    assert client.post(f"/api/v1/orders/{o['id']}/cancel", headers=auth("pm.santos")).json()["status"] == "CANCELLED"


def test_client_restriction_blocks(client, auth):
    r = _order(client, auth("trader.lim"), account="PH-BAL-01", symbol="JFC")
    assert r.status_code == 409
    assert "restricted" in str(r.json()["detail"]["violations"]).lower()


def test_mandate_band_blocks_equities_in_bond_fund(client, auth):
    r = _order(client, auth("trader.lim"), account="PH-INC-01", symbol="BDO", qty=100)
    assert r.status_code == 409


def test_soft_limit_requires_override(client, auth):
    # ~25% of NAV in one stock trips the 20% soft cap (and nothing hard)
    pre = client.post("/api/v1/orders/pretrade", headers=auth("pm.santos"),
                      json={"account": "US-GRW-01", "symbol": "JNJ", "side": "BUY", "qty": 200_000}).json()
    soft = [x for x in pre["results"] if not x["passed"] and x["severity"] == "SOFT"]
    assert soft
    r = _order(client, auth("pm.santos"), account="US-GRW-01", symbol="JNJ", qty=200_000)
    assert r.status_code == 409 and r.json()["detail"]["requires_override"]
    r = _order(client, auth("pm.santos"), account="US-GRW-01", symbol="JNJ", qty=200_000,
               override_reason="IC approved tactical overweight")
    assert r.status_code == 201


def test_no_short_rule(client, auth):
    r = _order(client, auth("trader.lim"), account="PH-BAL-02", symbol="TEL", side="SELL", qty=10_000_000)
    assert r.status_code == 409
