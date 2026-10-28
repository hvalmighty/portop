def test_rule_versioning_and_scan(client, auth):
    h = auth("compliance.cruz")
    r = client.post("/api/v1/compliance/rules", headers=h, json={
        "code": "TEST-SEC-5", "name": "Sector cap test", "rule_type": "MAX_SECTOR_WEIGHT", "scope": "ACCOUNT",
        "scope_ref": "PH-EQ-01", "params": {"limit_pct": 5}, "severity": "SOFT"})
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    client.post("/api/v1/compliance/scan", headers=h)
    br = client.get("/api/v1/compliance/breaches?account=PH-EQ-01&status=OPEN", headers=h).json()
    assert any(b["rule"] == "TEST-SEC-5" and b["kind"] == "PASSIVE" for b in br)
    # loosen the rule -> next scan auto-resolves
    client.patch(f"/api/v1/compliance/rules/{rid}", headers=h, json={"params": {"limit_pct": 99}})
    hist = client.get(f"/api/v1/compliance/rules/{rid}/history", headers=h).json()
    assert [v["version"] for v in hist] == [2, 1]
    client.post("/api/v1/compliance/scan", headers=h)
    br = client.get("/api/v1/compliance/breaches?account=PH-EQ-01&status=OPEN", headers=h).json()
    assert not any(b["rule"] == "TEST-SEC-5" for b in br)


def test_rating_downgrade_creates_passive_breach(client, auth):
    client.patch("/api/v1/system/instruments/SMICPM-2030", headers=auth("ops.garcia"), json={"rating": "BB+"})
    client.post("/api/v1/compliance/scan", headers=auth("compliance.cruz"))
    br = client.get("/api/v1/compliance/breaches?status=OPEN", headers=auth("compliance.cruz")).json()
    hits = [b for b in br if b["rule"] == "REG-PH-RATING" and b["subject"] == "SMICPM-2030"]
    assert hits and all(b["kind"] == "PASSIVE" for b in hits)
    r = client.post(f"/api/v1/compliance/breaches/{hits[0]['id']}", headers=auth("compliance.cruz"),
                    json={"status": "ACKNOWLEDGED", "note": "Sell-down plan within 30 days"})
    assert r.json()["status"] == "ACKNOWLEDGED"
    client.patch("/api/v1/system/instruments/SMICPM-2030", headers=auth("ops.garcia"), json={"rating": "BBB"})


def test_compliance_write_requires_role(client, auth):
    r = client.post("/api/v1/compliance/rules", headers=auth("pm.santos"), json={
        "code": "X-1", "name": "nope", "rule_type": "NO_SHORT_CASH"})
    assert r.status_code == 403


def test_audit_trail_records_actions(client, auth):
    rows = client.get("/api/v1/audit?action=RULE_UPDATE", headers=auth("compliance.cruz")).json()
    assert rows and rows[0]["before"] and rows[0]["after"]
