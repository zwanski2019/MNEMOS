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
def auth(client):
    """Headers for a signed-in account on an active trial.

    Writes are gated (see the tests at the bottom of this file), so anything that
    creates a target or a run has to authenticate. Reads deliberately do not.
    """
    email = f"gw-{uuid.uuid4().hex[:10]}@mnemos.test"
    resp = client.post(
        "/auth/signup", json={"email": email, "password": "a-long-enough-password"}
    )
    assert resp.status_code == 201
    return {"Authorization": f"Bearer {resp.json()['token']}"}


@pytest.fixture()
def target(client, auth):
    suffix = uuid.uuid4().hex[:8]
    resp = client.post("/targets", headers=auth, json={
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


def test_target_without_allow_rule_is_rejected(client, auth):
    resp = client.post("/targets", headers=auth, json={
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


def test_out_of_scope_finding_is_forbidden(client, target, auth):
    target_id, _ = target
    run_id = client.post("/runs", params={"target_id": target_id},
                         headers=auth).json()["run_id"]
    resp = client.post("/findings", headers=auth, json={
        "target_id": target_id, "run_id": run_id, "host": "someone-elses.example.com",
        "title": "should never land", "severity": "high", "summary": "x",
    })
    assert resp.status_code == 403


def test_duplicate_finding_returns_409_not_a_second_row(client, target, auth):
    target_id, suffix = target
    run_id = client.post("/runs", params={"target_id": target_id},
                         headers=auth).json()["run_id"]
    payload = {
        "target_id": target_id, "run_id": run_id, "host": f"www.{suffix}.gw.test",
        "title": "Stripe key in bundle", "severity": "medium",
        "summary": "A publishable key ships to the browser.",
    }
    first = client.post("/findings", headers=auth, json=payload)
    assert first.status_code == 201 and first.json()["written"] is True

    second = client.post("/findings", headers=auth, json=payload)
    assert second.status_code == 409
    assert second.json()["written"] is False

    rows = client.get("/findings", params={"target_id": target_id}).json()
    assert sum(1 for r in rows if r["title"] == "Stripe key in bundle") == 1


def test_recall_returns_prior_context(client, target, auth):
    target_id, suffix = target
    run_id = client.post("/runs", params={"target_id": target_id},
                         headers=auth).json()["run_id"]
    client.post("/findings", headers=auth, json={
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


# ---------------------------------------------------------------------------
# reads are open, writes are gated
# ---------------------------------------------------------------------------
def _signup(client) -> tuple[str, str]:
    email = f"gw-{uuid.uuid4().hex[:10]}@mnemos.test"
    r = client.post("/auth/signup", json={"email": email, "password": "a-long-enough-password"})
    assert r.status_code == 201
    return r.json()["token"], email


def test_every_read_endpoint_works_without_a_token(client):
    """The console is the funnel. Judges and visitors must never hit a wall."""
    for path in ("/health", "/findings", "/runs", "/audit", "/stats"):
        assert client.get(path).status_code == 200, path


def test_writes_require_authentication(client):
    body = {
        "name": "unauthenticated", "root_domain": f"{uuid.uuid4().hex[:8]}.noauth.test",
        "authorisation": "none",
        "scope_rules": [{"pattern": "*.noauth.test", "effect": "allow", "reason": "x"}],
    }
    assert client.post("/targets", json=body).status_code == 401


def test_garbage_token_is_rejected(client):
    r = client.post(
        "/targets",
        headers={"Authorization": "Bearer not-a-real-token"},
        json={"name": "x", "root_domain": f"{uuid.uuid4().hex[:8]}.noauth.test",
              "authorisation": "none",
              "scope_rules": [{"pattern": "*.noauth.test", "effect": "allow", "reason": "x"}]},
    )
    assert r.status_code == 401


def test_trial_account_can_write(client):
    token, _ = _signup(client)
    suffix = uuid.uuid4().hex[:8]
    r = client.post(
        "/targets",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": f"trial-{suffix}", "root_domain": f"{suffix}.trial.test",
              "authorisation": "unit test",
              "scope_rules": [{"pattern": f"*.{suffix}.trial.test", "effect": "allow",
                               "reason": "owned"}]},
    )
    assert r.status_code == 201


def test_expired_trial_gets_402_not_403(client):
    """Payment required, not forbidden — the client can act on the difference."""
    token, email = _signup(client)
    from mnemos_memory import Memory

    with Memory() as mem, mem.conn.cursor() as cur:
        cur.execute(
            "UPDATE subscriptions SET trial_ends_at = now() - INTERVAL '1 day' "
            "WHERE account_id = (SELECT id FROM accounts WHERE email = %s)", (email,))

    suffix = uuid.uuid4().hex[:8]
    r = client.post(
        "/targets",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "expired", "root_domain": f"{suffix}.expired.test",
              "authorisation": "unit test",
              "scope_rules": [{"pattern": f"*.{suffix}.expired.test", "effect": "allow",
                               "reason": "owned"}]},
    )
    assert r.status_code == 402

    # ...but reading is still completely open for that same account.
    assert client.get("/findings").status_code == 200


def test_me_reports_entitlement(client):
    token, _ = _signup(client)
    body = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).json()
    assert body["plan"] == "trial"
    assert body["can_write"] is True
    assert 0 < body["trial_days_left"] <= 5


def test_logout_invalidates_the_token(client):
    token, _ = _signup(client)
    assert client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"}).status_code == 204
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
