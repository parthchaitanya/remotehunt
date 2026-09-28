"""Demo mode: seeded fictional data, dangerous actions blocked."""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings


@pytest.fixture
def demo_client():
    from app.main import app

    s = get_settings()
    old = (s.demo_mode, s.embedding_backend)
    s.demo_mode, s.embedding_backend = True, "hashing"
    with TestClient(app) as c:
        yield c
    s.demo_mode, s.embedding_backend = old


def test_demo_blocks_live_actions(demo_client):
    for method, path in (("post", "/api/search/run"), ("post", "/api/gmail/sync"), ("get", "/api/gmail/auth/start"),
                         ("post", "/api/sources/health-check"), ("post", "/api/digests/run")):
        r = getattr(demo_client, method)(path, json={}) if method == "post" else demo_client.get(path)
        assert r.status_code == 403, path
    r = demo_client.post("/api/resume/upload", files={"file": ("r.pdf", b"x")})
    assert r.status_code == 403
    assert demo_client.get("/api/gmail/status").json()["configured"] is False


def test_demo_seed_uses_fictional_candidate():
    from app import demo
    from app.resume.parser import parse_text

    parsed = parse_text(demo.DEMO_RESUME)
    assert parsed["name"] == "Asha Verma"
    assert parsed["contact"]["email"].endswith("@example.com")
    assert demo.FIXTURE.exists(), "run scripts/export_demo_jobs.py to create the demo job snapshot"
