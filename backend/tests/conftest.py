import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ["MPOWER_DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["MPOWER_MARKET_SIM_ENABLED"] = "false"
os.environ["MPOWER_JWT_SECRET"] = "test-secret-0123456789abcdef-0123456789"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

PWD = "Mpower@2026!"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _token(client, user):
    r = client.post("/api/v1/auth/login", data={"username": user, "password": PWD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def auth(client):
    cache = {}

    def get(user):
        if user not in cache:
            cache[user] = _token(client, user)
        return cache[user]

    return get
