"""Accounts, sessions, and the write gate.

The product rule being tested: **reading memory is free forever, acting on it is
not.** Every assertion here is about the boundary between those two.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest

psycopg = pytest.importorskip("psycopg")

from mnemos_memory import Memory, migrate  # noqa: E402
from mnemos_memory.auth import (  # noqa: E402
    Accounts,
    AuthError,
    NotEntitled,
    hash_password,
    verify_password,
)

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


@pytest.fixture(scope="session", autouse=True)
def _schema():
    migrate(verbose=False)


@pytest.fixture()
def accounts():
    with Memory() as mem:
        yield Accounts(mem.conn)


def _email() -> str:
    return f"user-{uuid.uuid4().hex[:10]}@mnemos.test"


# ---------------------------------------------------------------------------
# password hashing
# ---------------------------------------------------------------------------
def test_password_hash_is_not_reversible_and_is_salted():
    a, b = hash_password("correct horse battery"), hash_password("correct horse battery")
    assert a != b, "identical passwords must not produce identical hashes"
    assert "correct horse battery" not in a
    assert verify_password("correct horse battery", a)
    assert verify_password("correct horse battery", b)


def test_wrong_password_is_rejected():
    stored = hash_password("correct horse battery")
    assert verify_password("Correct horse battery", stored) is False


def test_malformed_hash_fails_closed():
    assert verify_password("anything", "not-a-real-hash") is False
    assert verify_password("anything", "") is False


def test_short_passwords_are_refused():
    with pytest.raises(ValueError, match="at least"):
        hash_password("short")


# ---------------------------------------------------------------------------
# signup / login
# ---------------------------------------------------------------------------
def test_signup_creates_account_and_starts_trial(accounts):
    acct = accounts.sign_up(_email(), "a-long-enough-password")
    ent = accounts.entitlement(acct.id)
    assert ent.plan == "trial"
    assert ent.status == "trialing"
    assert ent.can_write is True
    assert 0 < ent.days_left <= 5


def test_duplicate_email_is_refused(accounts):
    email = _email()
    accounts.sign_up(email, "a-long-enough-password")
    with pytest.raises(ValueError, match="already exists"):
        accounts.sign_up(email, "another-long-password")


def test_invalid_email_is_refused(accounts):
    with pytest.raises(ValueError, match="invalid email"):
        accounts.sign_up("not-an-email", "a-long-enough-password")


def test_login_returns_a_working_token(accounts):
    email = _email()
    acct = accounts.sign_up(email, "a-long-enough-password")
    token = accounts.log_in(email, "a-long-enough-password")
    assert accounts.account_for_token(token).id == acct.id


def test_login_failures_are_indistinguishable(accounts):
    """Wrong password and unknown account must not be tellable apart."""
    email = _email()
    accounts.sign_up(email, "a-long-enough-password")

    with pytest.raises(AuthError) as wrong_pw:
        accounts.log_in(email, "the-wrong-password")
    with pytest.raises(AuthError) as no_account:
        accounts.log_in(_email(), "the-wrong-password")

    assert str(wrong_pw.value) == str(no_account.value)


def test_logout_revokes_the_token(accounts):
    email = _email()
    accounts.sign_up(email, "a-long-enough-password")
    token = accounts.log_in(email, "a-long-enough-password")
    assert accounts.account_for_token(token) is not None

    accounts.log_out(token)
    assert accounts.account_for_token(token) is None


def test_session_table_stores_no_usable_token(accounts):
    """A dump of `sessions` must not let anyone log in."""
    email = _email()
    accounts.sign_up(email, "a-long-enough-password")
    token = accounts.log_in(email, "a-long-enough-password")

    with accounts.conn.cursor() as cur:
        cur.execute("SELECT token_sha256 FROM sessions WHERE token_sha256 IS NOT NULL LIMIT 50")
        stored = [r["token_sha256"] for r in cur.fetchall()]
    assert token not in stored


def test_garbage_token_is_not_a_session(accounts):
    assert accounts.account_for_token("not-a-real-token") is None
    assert accounts.account_for_token("") is None


# ---------------------------------------------------------------------------
# entitlement — the actual product rule
# ---------------------------------------------------------------------------
def test_expired_trial_cannot_write(accounts):
    acct = accounts.sign_up(_email(), "a-long-enough-password")
    with accounts.conn.cursor() as cur:
        cur.execute(
            "UPDATE subscriptions SET trial_ends_at = now() - INTERVAL '1 day' "
            "WHERE account_id = %s", (acct.id,))

    ent = accounts.entitlement(acct.id)
    assert ent.can_write is False
    with pytest.raises(NotEntitled):
        accounts.require_write(acct.id)


def test_paid_plan_can_write_after_trial_ends(accounts):
    acct = accounts.sign_up(_email(), "a-long-enough-password")
    with accounts.conn.cursor() as cur:
        cur.execute(
            "UPDATE subscriptions SET trial_ends_at = now() - INTERVAL '1 day' "
            "WHERE account_id = %s", (acct.id,))
    assert accounts.entitlement(acct.id).can_write is False

    accounts.activate_plan(
        acct.id, provider_customer_id="cus_test", provider_subscription_id="sub_test",
        current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
    )
    ent = accounts.entitlement(acct.id)
    assert ent.plan == "pro" and ent.status == "active" and ent.can_write is True


def test_account_without_subscription_cannot_write(accounts):
    """Fails closed: no entitlement row means no writing, not unlimited writing."""
    with accounts.conn.cursor() as cur:
        cur.execute(
            "INSERT INTO accounts (email, password_hash) VALUES (%s, %s) RETURNING id",
            (_email(), hash_password("a-long-enough-password")))
        orphan = str(cur.fetchone()["id"])

    ent = accounts.entitlement(orphan)
    assert ent.can_write is False
    with pytest.raises(NotEntitled):
        accounts.require_write(orphan)


def test_entitlement_fails_closed_when_memory_is_unreachable(accounts, monkeypatch):
    class Broken:
        def cursor(self):
            raise RuntimeError("connection reset")

    monkeypatch.setattr(accounts, "conn", Broken())
    ent = accounts.entitlement(str(uuid.uuid4()))
    assert ent.can_write is False


def test_expiring_overdue_trials_is_idempotent(accounts):
    acct = accounts.sign_up(_email(), "a-long-enough-password")
    with accounts.conn.cursor() as cur:
        cur.execute(
            "UPDATE subscriptions SET trial_ends_at = now() - INTERVAL '1 day' "
            "WHERE account_id = %s", (acct.id,))

    accounts.expire_overdue_trials()
    assert accounts.entitlement(acct.id).status == "expired"
    accounts.expire_overdue_trials()  # second run must not error or change anything
    assert accounts.entitlement(acct.id).status == "expired"
