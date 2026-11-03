"""BDO TIG sample portfolios: configuration, benchmark-relative optimisation, mandate enforcement, maker-checker."""

import pytest

from app.db import SessionLocal
from app.services.scenarios import seed_bdo_scenarios

CODES = ["BDO-PEQ", "BDO-GEQ", "BDO-HTF"]


def test_scenarios_are_configured(client, auth):
    models = {m["code"]: m for m in client.get("/api/v1/models", headers=auth("pm.santos")).json()}
    for code in CODES:
        assert code in models, code
    peq, geq, htf = (models[c]["mandate"] for c in CODES)
    assert peq["currency"] == "PHP" and peq["max_weight_pct"] == 20 and peq["excess_return_bps"] == 100
    assert geq["currency"] == "USD" and geq["max_weight_pct"] == 100 and geq["excess_return_bps"] == 100
    assert htf["currency"] == "USD" and htf["max_weight_pct"] == 20 and htf["excess_return_bps"] == 200
    assert len(htf["universe"]) == 10
    assert htf["benchmark_weights"] == {"NDWUIT": 50, "NDWUHC": 50}


@pytest.mark.parametrize("code", CODES)
def test_optimise_meets_goal_and_cap(client, auth, code):
    r = client.post(f"/api/v1/models/{code}/optimise", headers=auth("pm.santos"))
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["feasible"], res["message"]
    assert res["goal_met"]
    assert res["cap_respected"]
    assert res["excess_return_bps"] >= res["goal_bps"] - 0.5
    assert abs(sum(res["weights"].values()) - 100) <= 0.01
    mandate = next(m for m in client.get("/api/v1/models", headers=auth("pm.santos")).json() if m["code"] == code)
    assert set(res["weights"]) <= set(mandate["mandate"]["universe"])


def test_optimise_requires_optimiser_role(client, auth):
    assert client.post("/api/v1/models/BDO-PEQ/optimise", headers=auth("compliance.cruz")).status_code == 403
    assert client.post("/api/v1/models/BDO-PEQ/optimise", headers=auth("viewer")).status_code == 403


def test_mandate_blocks_outside_universe_and_over_cap(client, auth):
    h = auth("pm.santos")
    outside = {"AAPL": 50, "BDO": 50}
    r = client.post("/api/v1/models/BDO-PEQ/versions", headers=h,
                    json={"weights": outside, "rationale": "test: outside universe"})
    assert r.status_code == 422 and "outside the mandate universe" in r.text
    over = {"BDO": 25, "SM": 15, "ALI": 10, "AC": 10, "JFC": 10, "TEL": 10, "ICT": 10, "MER": 10}
    r = client.post("/api/v1/models/BDO-PEQ/versions", headers=h,
                    json={"weights": over, "rationale": "test: over the 20% cap"})
    assert r.status_code == 422 and "20% cap" in r.text


def test_maker_checker_on_seeded_draft(client, auth):
    peq = client.get("/api/v1/models/BDO-PEQ", headers=auth("pm.santos")).json()
    draft = next((v for v in peq["versions"] if v["status"] == "DRAFT"), None)
    if draft is None:
        pytest.skip("seeded draft already approved in this session")
    v = draft["version"]
    r = client.post(f"/api/v1/models/BDO-PEQ/versions/{v}/approve", headers=auth("pm.santos"))
    assert r.status_code == 403  # proposer cannot approve their own version
    r = client.post(f"/api/v1/models/BDO-PEQ/versions/{v}/approve", headers=auth("compliance.cruz"))
    assert r.status_code == 200
    active = next(x for x in r.json()["versions"] if x["version"] == v)
    assert active["status"] == "ACTIVE" and active["approved_by"] == "compliance.cruz"


def test_seeding_is_idempotent():
    db = SessionLocal()
    try:
        result = seed_bdo_scenarios(db)
        assert result["status"] == "ok"
        assert result["created"] == []
    finally:
        db.close()
