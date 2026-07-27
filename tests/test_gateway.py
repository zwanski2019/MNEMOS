"""Gateway behaviour at the HTTP boundary.

The interesting responses here are the refusals: 403 for out of scope and 409 for
"memory already knew". Those two status codes are the product.
"""

from __future__ import annotations

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

DSN = os.getenv("DATABASE_URL", "postgresql://root@localhost:26257/mnemos?sslmode=disable")


def _cluster_reachable() -> bool:
    try:
        with psycopg.connect(DSN.replace("/mnemos?", "/defaultdb?"), connect_timeout=3):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _cluster_reachable(), reason="no CockroachDB reachable; run `make db-up`"
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("MNEMOS_EMBEDDER", "offline")
    from mnemos_gateway.app import app

    with TestClient(app) as c:
        yield c


@pytest.fixture()
def target(client):
    suffix = uuid.uuid4().hex[:8]
    resp = client.post("/targets", json={
        "name": f"gw-{suffix}",
        "root_domain": f"{suffix}.gw.test",
        "authorisation": "unit test",
        "scope_rules": [
            {"pattern": f"*.{suffix}.gw.test", "effect": "allow", "reason": "owned"},
            {"pattern": f"admin.{suffix}.gw.test", "effect": "deny", "reason": "excluded"},
        ],
    })
    assert resp.status_code == 201
    return resp.json()["target_id"], suffix


def test_health_reports_the_memory_layer(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "findings" in body["memory"]


def test_target_without_allow_rule_is_rejected(client):
    resp = client.post("/targets", json={
        "name": "no-allow", "root_domain": f"{uuid.uuid4().hex[:8]}.gw.test",
        "authorisation": "x",
        "scope_rules": [{"pattern": "*.x.test", "effect": "deny", "reason": "nope"}],
    })
    assert resp.status_code == 422


def test_scope_check_is_fail_closed(client, target):
    target_id, suffix = target
    allowed = client.post("/scope/check", json={
        "target_id": target_id, "host": f"www.{suffix}.gw.test"}).json()
    denied = client.post("/scope/check", json={
        "target_id": target_id, "host": "unrelated.example.com"}).json()
    carved_out = client.post("/scope/check", json={
        "target_id": target_id, "host": f"admin.{suffix}.gw.test"}).json()

    assert allowed["allowed"] is True
    assert denied["allowed"] is False
    assert carved_out["allowed"] is False


def test_out_of_scope_finding_is_forbidden(client, target):
    target_id, _ = target
    run_id = client.post("/runs", params={"target_id": target_id}).json()["run_id"]
    resp = client.post("/findings", json={
        "target_id": target_id, "run_id": run_id, "host": "someone-elses.example.com",
        "title": "should never land", "severity": "high", "summary": "x",
    })
    assert resp.status_code == 403


def test_duplicate_finding_returns_409_not_a_second_row(client, target):
    target_id, suffix = target
    run_id = client.post("/runs", params={"target_id": target_id}).json()["run_id"]
    payload = {
        "target_id": target_id, "run_id": run_id, "host": f"www.{suffix}.gw.test",
        "title": "Stripe key in bundle", "severity": "medium",
        "summary": "A publishable key ships to the browser.",
    }
    first = client.post("/findings", json=payload)
    assert first.status_code == 201 and first.json()["written"] is True

    second = client.post("/findings", json=payload)
    assert second.status_code == 409
    assert second.json()["written"] is False

    rows = client.get("/findings", params={"target_id": target_id}).json()
    assert sum(1 for r in rows if r["title"] == "Stripe key in bundle") == 1


def test_recall_returns_prior_context(client, target):
    target_id, suffix = target
    run_id = client.post("/runs", params={"target_id": target_id}).json()["run_id"]
    client.post("/findings", json={
        "target_id": target_id, "run_id": run_id, "host": f"api.{suffix}.gw.test",
        "title": "Apache mod_status exposed", "severity": "medium",
        "summary": "server-status is reachable without credentials.",
    })
    hits = client.get("/memory/recall", params={
        "target_id": target_id, "q": "Apache mod_status exposed", "k": 3}).json()
    assert hits["results"], "recall must find what was just written"
    # Assert on identity rather than an absolute distance: the threshold that is
    # meaningful for Titan is not the one that is meaningful for the offline
    # embedder, but "the thing we just wrote ranks first" holds for both.
    top = hits["results"][0]
    assert "Apache mod_status exposed" in top["content"]
    assert top["kind"] == "finding"
