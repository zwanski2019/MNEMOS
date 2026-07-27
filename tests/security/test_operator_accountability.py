"""Attacker validation for operator accountability (Part F rows 2, 3, 20).

The claim under test is structural, not procedural: a scan that cannot name its
authorising grant must be impossible at the schema level. Every test here tries
to produce one anyway.
"""

from __future__ import annotations

import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
pytest.importorskip("cryptography")

from mnemos_memory import Memory, migrate  # noqa: E402
from mnemos_memory.auth import Accounts, hash_password  # noqa: E402
from mnemos_memory.covenant import (  # noqa: E402
    MAX_GRANT_DAYS,
    Accountability,
    NotAuthorised,
    canonical_json,
    verify_receipt,
)
from mnemos_memory.embeddings import HashingEmbedder  # noqa: E402

DSN = os.getenv("DATABASE_URL", "postgresql://root@localhost:26257/mnemos?sslmode=disable")

COVENANT = "I assert written authorisation for every scope I submit. v2026.1"
COVENANT_VERSION = "2026.1"


def _cluster_reachable() -> bool:
    try:
        with psycopg.connect(DSN.replace("/mnemos?", "/defaultdb?"), connect_timeout=3):
            return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _cluster_reachable(), reason="no CockroachDB reachable; run `make db-up`"
)


@pytest.fixture(scope="session", autouse=True)
def _keys():
    """Ephemeral signing key and pepper for the suite.

    Generated per-run rather than committed: a test fixture key that leaks into
    production config is a real incident, and there is no reason for these to be
    stable across runs.
    """
    import base64

    os.environ.setdefault(
        "MNEMOS_RECEIPT_KEY",
        base64.urlsafe_b64encode(os.urandom(32)).decode().rstrip("="),
    )
    os.environ.setdefault("MNEMOS_IDENTITY_PEPPER", uuid.uuid4().hex)
    migrate(verbose=False)


@pytest.fixture()
def mem():
    with Memory(embedder=HashingEmbedder()) as m:
        yield m


@pytest.fixture()
def acct(mem):
    return Accounts(mem.conn), Accountability(mem.conn)


def _new_operator(accounts, accountability, *, promote: bool = True):
    email = f"op-{uuid.uuid4().hex[:10]}@mnemos.test"
    account = accounts.sign_up(email, "a-long-enough-password")
    receipt = accountability.accept_covenant(
        operator_id=account.id, email=email, covenant_text=COVENANT,
        covenant_version=COVENANT_VERSION, ip="203.0.113.9", user_agent="pytest",
    )
    if promote:
        accountability.promote_to_operator(
            account.id, approved_by=account.id, receipt_id=receipt.id
        )
    return account, receipt


# ---------------------------------------------------------------------------
# F2 — a pending account may not dispatch a scan
# ---------------------------------------------------------------------------
def test_pending_tier_cannot_dispatch(acct):
    accounts, accountability = acct
    account, _ = _new_operator(accounts, accountability, promote=False)

    with pytest.raises(NotAuthorised, match="tier"):
        accountability.authorise_scan(account.id, "www.example.com")


def test_signup_defaults_to_pending(acct, mem):
    accounts, accountability = acct
    account, _ = _new_operator(accounts, accountability, promote=False)
    with mem.conn.cursor() as cur:
        cur.execute("SELECT tier FROM accounts WHERE id = %s", (account.id,))
        assert cur.fetchone()["tier"] == "pending"


# ---------------------------------------------------------------------------
# F3 — no grant / expired grant / revoked grant, all refused
# ---------------------------------------------------------------------------
def test_no_grant_is_refused(acct):
    accounts, accountability = acct
    account, _ = _new_operator(accounts, accountability)

    with pytest.raises(NotAuthorised, match="no live grant"):
        accountability.authorise_scan(account.id, "www.example.com")


def test_expired_grant_is_refused(acct, mem):
    accounts, accountability = acct
    account, receipt = _new_operator(accounts, accountability)
    grant = accountability.issue_grant(
        operator_id=account.id, receipt_id=receipt.id, scope_spec="*.example.com",
        evidence_kind="letter", evidence_ref="letter:abc", granted_by=account.id,
    )
    # Both timestamps move: `grant_must_expire` refuses expires_at <= granted_at,
    # so a grant cannot be retro-expired into an invalid shape. Ageing the whole
    # row is what a real elapsed grant looks like.
    with mem.conn.cursor() as cur:
        cur.execute(
            "UPDATE scope_grants SET granted_at = now() - INTERVAL '40 days', "
            "expires_at = now() - INTERVAL '1 hour' WHERE id = %s",
            (grant.id,))

    with pytest.raises(NotAuthorised, match="no live grant"):
        accountability.authorise_scan(account.id, "www.example.com")


def test_revoked_grant_is_refused(acct):
    accounts, accountability = acct
    account, receipt = _new_operator(accounts, accountability)
    grant = accountability.issue_grant(
        operator_id=account.id, receipt_id=receipt.id, scope_spec="*.example.com",
        evidence_kind="letter", evidence_ref="letter:abc", granted_by=account.id,
    )
    assert accountability.authorise_scan(account.id, "www.example.com")

    accountability.revoke_grant(grant.id, revoked_by=account.id, reason="programme ended")
    with pytest.raises(NotAuthorised, match="no live grant"):
        accountability.authorise_scan(account.id, "www.example.com")


def test_grant_does_not_cover_hosts_outside_its_spec(acct):
    accounts, accountability = acct
    account, receipt = _new_operator(accounts, accountability)
    accountability.issue_grant(
        operator_id=account.id, receipt_id=receipt.id, scope_spec="*.example.com",
        evidence_kind="letter", evidence_ref="letter:abc", granted_by=account.id,
    )
    with pytest.raises(NotAuthorised):
        accountability.authorise_scan(account.id, "www.someone-else.com")


def test_grants_cannot_outlive_the_cap(acct):
    accounts, accountability = acct
    account, receipt = _new_operator(accounts, accountability)
    with pytest.raises(ValueError, match=str(MAX_GRANT_DAYS)):
        accountability.issue_grant(
            operator_id=account.id, receipt_id=receipt.id, scope_spec="*.example.com",
            evidence_kind="letter", evidence_ref="x", granted_by=account.id,
            days=MAX_GRANT_DAYS + 1,
        )


# ---------------------------------------------------------------------------
# A4 — structural binding. The important one.
# ---------------------------------------------------------------------------
def test_a_run_cannot_exist_without_naming_its_authorisation(mem):
    """Enforcement that lives only in a handler is not enforcement."""
    with mem.conn.cursor() as cur:
        cur.execute("SELECT id FROM targets LIMIT 1")
        row = cur.fetchone()
    if row is None:
        pytest.skip("no target available")

    with pytest.raises(psycopg.errors.NotNullViolation):
        with mem.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agent_runs (target_id, pass_no, cost_ceiling_usd) "
                "VALUES (%s, 1, 1.0)", (row["id"],))
    mem.conn.rollback()


def test_a_run_cannot_cite_a_grant_that_does_not_exist(mem):
    with mem.conn.cursor() as cur:
        cur.execute("SELECT id FROM targets LIMIT 1")
        row = cur.fetchone()
    if row is None:
        pytest.skip("no target available")

    with pytest.raises(psycopg.errors.ForeignKeyViolation):
        with mem.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO agent_runs (target_id, pass_no, cost_ceiling_usd, "
                "grant_id, receipt_id) VALUES (%s, 1, 1.0, %s, %s)",
                (row["id"], str(uuid.uuid4()), str(uuid.uuid4())))
    mem.conn.rollback()


def test_start_run_refuses_without_authorisation(mem, monkeypatch):
    """The convenience path must not become the bypass."""
    monkeypatch.delenv("MNEMOS_BOOTSTRAP_GRANT", raising=False)
    with mem.conn.cursor() as cur:
        cur.execute("SELECT id FROM targets LIMIT 1")
        row = cur.fetchone()
    if row is None:
        pytest.skip("no target available")

    with pytest.raises(ValueError, match="cannot name its authorisation"):
        mem.start_run(str(row["id"]))


def test_the_bootstrap_grant_can_never_authorise_a_scan(mem):
    """It exists to label legacy rows, not to be a back door."""
    with mem.conn.cursor() as cur:
        cur.execute(
            "SELECT expires_at, revoked_at FROM scope_grants WHERE id = "
            "'00000000-0000-0000-0000-000000000003'")
        row = cur.fetchone()
    assert row is not None
    assert row["revoked_at"] is not None, "bootstrap grant must be born revoked"

    accountability = Accountability(mem.conn)
    with pytest.raises(NotAuthorised):
        accountability.authorise_scan(
            "00000000-0000-0000-0000-000000000001", "legacy.pre-accountability.invalid"
        )


# ---------------------------------------------------------------------------
# F20 — tamper a receipt, then verify
# ---------------------------------------------------------------------------
def test_receipt_verifies_against_its_public_key(acct):
    accounts, accountability = acct
    account, receipt = _new_operator(accounts, accountability)
    result = accountability.verify_stored_receipt(receipt.id)
    assert result["found"] and result["signature_valid"]
    assert result["algorithm"] == "Ed25519"


def test_tampered_receipt_fails_verification(acct):
    """Even if a row could be altered, the signature would not survive it."""
    accounts, accountability = acct
    account, receipt = _new_operator(accounts, accountability)

    forged = dict(receipt.payload)
    forged["covenant_version"] = "9999.1"
    from mnemos_memory.covenant import load_signing_key

    assert verify_receipt(forged, receipt.signature, load_signing_key().public_b64) is False


def test_receipt_ledger_is_append_only(mem):
    """The application role has SELECT+INSERT and nothing else."""
    admin = psycopg.connect(DSN, autocommit=True)
    user = f"receipt_probe_{uuid.uuid4().hex[:8]}"
    password = uuid.uuid4().hex
    try:
        with admin.cursor() as cur:
            cur.execute(f"CREATE USER IF NOT EXISTS {user} WITH PASSWORD %s", (password,))
            cur.execute(f"GRANT mnemos_agent TO {user}")
    finally:
        admin.close()

    import urllib.parse

    parts = urllib.parse.urlsplit(DSN)
    netloc = f"{user}:{urllib.parse.quote(password)}@{parts.hostname}"
    if parts.port:
        netloc += f":{parts.port}"
    probe_dsn = urllib.parse.urlunsplit(
        (parts.scheme, netloc, parts.path, parts.query, parts.fragment))

    conn = psycopg.connect(probe_dsn, autocommit=True)
    try:
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("UPDATE covenant_receipts SET covenant_version = 'x'")
        with conn.cursor() as cur:
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                cur.execute("DELETE FROM covenant_receipts")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# consent is not silently re-mapped
# ---------------------------------------------------------------------------
def test_changing_the_covenant_invalidates_prior_acceptance(acct):
    accounts, accountability = acct
    account, receipt = _new_operator(accounts, accountability)

    from mnemos_memory.covenant import sha256_hex

    assert accountability.current_receipt(account.id, sha256_hex(COVENANT)) == receipt.id

    revised = COVENANT + " Additionally you agree to a new clause."
    assert accountability.current_receipt(account.id, sha256_hex(revised)) is None


def test_canonical_json_is_stable_across_key_order():
    """The signature is over these bytes; drift here is a false rejection."""
    a = canonical_json({"b": 1, "a": 2, "c": {"z": 1, "y": 2}})
    b = canonical_json({"c": {"y": 2, "z": 1}, "a": 2, "b": 1})
    assert a == b
    assert b"  " not in a, "canonical form must not contain whitespace"


def test_identity_binding_is_not_reversible_without_the_pepper(acct):
    from mnemos_memory.covenant import identity_binding

    bound = identity_binding("Someone@Example.COM")
    assert "@" not in bound and "example" not in bound.lower()
    # Normalisation: case and surrounding space must not produce a different handle.
    assert bound == identity_binding("  someone@example.com  ")
