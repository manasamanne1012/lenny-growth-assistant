"""API contract tests.

The non-integration tests here assert the shape of the contract — validation,
error envelopes, OpenAPI surface — without a database. The integration tests
exercise the full turn against Postgres.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_liveness_is_dependency_free(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_every_response_carries_a_trace_id_header(client):
    r = client.get("/api/health")
    assert r.headers.get("X-Trace-Id")
    assert r.headers.get("X-Response-Time-Ms")


def test_active_model_configuration_is_exposed(client):
    body = client.get("/api/config").json()
    assert body["chat"]["provider"]
    assert "is_local" in body["chat"]


def test_runtime_config_never_leaks_secrets(client):
    body = client.get("/api/config/runtime").text.lower()
    for secret in ("api_key", "apikey", "password", "sk-"):
        assert secret not in body


def test_blank_message_is_rejected_with_a_structured_error(client):
    r = client.post("/api/chat", json={"message": "   "})
    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "validation_error"
    assert error["hint"]


def test_oversized_message_is_rejected(client):
    r = client.post("/api/chat", json={"message": "x" * 9000})
    assert r.status_code == 422


def test_unknown_route_returns_the_error_envelope(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_openapi_documents_every_public_endpoint(client):
    paths = client.get("/openapi.json").json()["paths"]
    for expected in (
        "/api/chat", "/api/search", "/api/sessions",
        "/api/health/deep", "/api/artifacts/{artifact_id}",
    ):
        assert expected in paths, f"{expected} missing from the OpenAPI document"


def test_artifact_render_endpoint_sets_a_deny_everything_csp():
    from app.api.artifacts import ARTIFACT_CSP

    assert "default-src 'none'" in ARTIFACT_CSP
    assert "frame-ancestors 'self'" in ARTIFACT_CSP
    assert "form-action 'none'" in ARTIFACT_CSP
    assert "connect-src" not in ARTIFACT_CSP  # no egress is permitted at all


# --------------------------------------------------------------- integration
@pytest.mark.integration
def test_full_turn_persists_a_session_and_two_messages(requires_db, client):
    r = client.post("/api/chat", json={"message": "What signals product-market fit?"})
    assert r.status_code == 200, r.text
    body = r.json()
    session_id = body["session_id"]
    assert body["message"]["role"] == "assistant"
    assert body["trace_id"]

    messages = client.get(f"/api/sessions/{session_id}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant"]


@pytest.mark.integration
def test_sessions_keep_independent_context(requires_db, client):
    a = client.post("/api/chat", json={"message": "Talk about pricing."}).json()
    b = client.post("/api/chat", json={"message": "Talk about onboarding."}).json()
    assert a["session_id"] != b["session_id"]
    assert len(client.get(f"/api/sessions/{a['session_id']}/messages").json()) == 2


@pytest.mark.integration
def test_search_endpoint_returns_a_sufficiency_verdict(requires_db, client):
    body = client.post("/api/search", json={"query": "activation", "top_k": 5}).json()
    assert body["sufficiency"] in ("sufficient", "thin", "insufficient")
    assert isinstance(body["results"], list)


@pytest.mark.integration
def test_deep_health_reports_each_dependency(requires_db, client):
    checks = client.get("/api/health/deep").json()["checks"]
    assert {"database", "knowledge_base", "models"} <= set(checks)


@pytest.mark.integration
def test_archiving_a_session_hides_it_from_the_list(requires_db, client):
    sid = client.post("/api/chat", json={"message": "hello"}).json()["session_id"]
    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert sid not in [s["id"] for s in client.get("/api/sessions").json()]
