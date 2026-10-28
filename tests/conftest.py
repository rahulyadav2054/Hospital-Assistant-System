"""Shared fixtures. Tests run against a throw-away SQLite DB, offline AI mode and no rate limiting."""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="hospital-tests-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP}/test.db".replace("\\", "/"),
    "AI_MODE": "offline",          # deterministic answers; the Claude path is unit-tested with a fake client
    "MOCK_AI": "false",
    "RATE_LIMIT_ENABLED": "false",
    "JWT_SECRET": "test-secret-0123456789-abcdefghijklmnopqrstuvwxyz",
    "HF_HUB_DISABLE_PROGRESS_BARS": "1",
    "TRANSFORMERS_VERBOSITY": "error",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.app import sessions  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.seed import seed  # noqa: E402

PASSWORD = "demo123"
_tokens: dict[str, str] = {}


@pytest.fixture(scope="session", autouse=True)
def _seeded_db():
    seed(reset=True)
    yield


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def reseed():
    """For tests that change data (reschedules). Tokens stay valid: user ids are recreated in the same order."""
    seed(reset=True)
    sessions.clear()
    yield
    seed(reset=True)
    sessions.clear()


def auth(client, user: str) -> dict:
    if user not in _tokens:
        r = client.post("/auth/login", json={"username": user, "password": PASSWORD})
        assert r.status_code == 200, r.text
        _tokens[user] = r.json()["access_token"]
    return {"Authorization": f"Bearer {_tokens[user]}"}


def ask(client, user: str, question: str, session: str | None = None) -> dict:
    r = client.post("/chat", json={"message": question, "session_id": session or f"t-{user}-{abs(hash(question))}"},
                    headers=auth(client, user))
    assert r.status_code == 200, r.text
    body = r.json()
    for key in ("answer", "status", "intent", "citations", "tool_calls", "cards", "action_required", "disclaimer"):
        assert key in body, f"contract field {key} missing"
    return body


def tool_names(r: dict) -> list[str]:
    return [t["name"] for t in r["tool_calls"]]
