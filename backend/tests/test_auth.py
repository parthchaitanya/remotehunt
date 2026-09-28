"""Login protection for deployed instances."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def client():
    from app.main import app

    s = get_settings()
    old = s.app_password
    s.app_password = "correct horse battery staple"
    with TestClient(app) as c:
        yield c
    s.app_password = old


def test_api_requires_login(client):
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/dashboard").status_code == 401
    assert client.get("/api/auth/me").json() == {"authenticated": False, "auth_enabled": True, "demo": False}


def test_wrong_password_rejected(client):
    r = client.post("/api/auth/login", json={"password": "nope"})
    assert r.status_code == 401
    assert "rh_session" not in r.cookies


def test_login_grants_session_and_logout_clears(client):
    r = client.post("/api/auth/login", json={"password": "correct horse battery staple"})
    assert r.status_code == 200
    assert client.get("/api/auth/me").json()["authenticated"] is True
    assert client.get("/api/settings").status_code == 200
    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/settings").status_code == 401


def test_forged_token_rejected():
    from app import auth

    tok = auth.make_token(1)
    expires, nonce, sig = tok.split(".")
    assert auth.valid_token(tok)
    assert not auth.valid_token(f"{int(expires) + 999}.{nonce}.{sig}")
    assert not auth.valid_token("garbage")


def test_auth_disabled_locally():
    from app.main import app

    s = get_settings()
    old = s.app_password
    s.app_password = ""
    with TestClient(app) as c:
        assert c.get("/api/auth/me").json() == {"authenticated": True, "auth_enabled": False, "demo": False}
    s.app_password = old
