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


def test_market_endpoints(client, auth):
    cfg = client.get("/api/v1/market/config").json()
    assert cfg["mode"] in ("stream", "poll") and cfg["interval_ms"] > 0
    r = client.get("/api/v1/market/ticks", headers=auth("viewer"))
    assert r.status_code == 200 and "data" in r.json()
    assert client.get("/api/v1/market/ticks").status_code == 401


def test_poll_mode_advances_prices():
    import random

    from app.db import SessionLocal
    from app.services.marketdata import advance_prices

    db = SessionLocal()
    try:
        before = {t["symbol"]: t["price"] for t in advance_prices(db, random.Random(1), 0)}
        after = {t["symbol"]: t["price"] for t in advance_prices(db, random.Random(2), 60)}
        assert any(after[s] != before[s] for s in before)
    finally:
        db.close()


def test_database_url_normalisation(monkeypatch):
    from app.config import Settings

    monkeypatch.delenv("MPOWER_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/db?sslmode=require")
    assert Settings().database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"
    monkeypatch.delenv("DATABASE_URL")
    monkeypatch.setenv("VERCEL", "1")
    s = Settings()
    assert s.database_url.startswith("sqlite:////tmp/") and s.market_mode == "poll"
