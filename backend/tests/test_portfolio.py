def test_overview_totals_consistent(client, auth):
    d = client.get("/api/v1/portfolio/overview?entity=SG", headers=auth("pm.santos")).json()
    assert d["reporting_ccy"] == "SGD"
    assert d["totals"]["positions"] == len(d["positions"])
    gross = sum(a["gross"] for a in d["accounts"])
    assert abs(gross - d["totals"]["gross"]) < 1e-3
    swap = next(p for p in d["positions"] if p["symbol"] == "IRS-USD-5Y")
    assert swap["exposure"] == swap["qty"] * swap["mark"]  # derivative exposure is full notional


def test_account_detail_has_drift(client, auth):
    d = client.get("/api/v1/portfolio/accounts/PH-BAL-01", headers=auth("pm.santos")).json()
    assert d["account"]["model"] == "PH-BAL"
    assert d["drift"]["rows"]


def test_entity_entitlement(client, auth):
    h = auth("admin")
    client.post("/api/v1/system/users", headers=h, json={
        "username": "ph.viewer", "full_name": "PH Viewer", "email": "p@example.com", "role": "VIEWER",
        "password": "Mpower@2026!", "entities": ["PH"]})
    from tests.conftest import _token
    hv = _token(client, "ph.viewer")
    assert client.get("/api/v1/portfolio/accounts/APAC-EQ-01", headers=hv).status_code == 403
    d = client.get("/api/v1/portfolio/overview", headers=hv).json()
    assert {a["entity"] for a in d["accounts"]} == {"PH"}
