def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json()["status"] == "ready"


def test_login_and_me(client, auth):
    me = client.get("/api/v1/auth/me", headers=auth("pm.santos")).json()
    assert me["role"] == "PM"
    assert "order:create" in me["permissions"]


def test_bad_password_and_lockout(client):
    for _ in range(5):
        r = client.post("/api/v1/auth/login", data={"username": "viewer", "password": "wrong-password1"})
        assert r.status_code == 401
    r = client.post("/api/v1/auth/login", data={"username": "viewer", "password": "Mpower@2026!"})
    assert r.status_code == 423


def test_unauthenticated_rejected(client):
    assert client.get("/api/v1/portfolio/overview").status_code == 401


def test_rbac_blocks_ops_creating_orders(client, auth):
    r = client.post("/api/v1/orders", headers=auth("ops.garcia"),
                    json={"account": "PH-BAL-01", "symbol": "BDO", "side": "BUY", "qty": 100})
    assert r.status_code == 403


def test_admin_unlocks_and_password_policy(client, auth):
    h = auth("admin")
    assert client.post("/api/v1/system/users/viewer/unlock", headers=h).status_code == 200
    r = client.post("/api/v1/system/users", headers=h, json={
        "username": "weak.user", "full_name": "Weak", "email": "w@example.com", "role": "VIEWER", "password": "short"})
    assert r.status_code == 422
