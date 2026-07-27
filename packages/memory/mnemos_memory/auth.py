"""Accounts, sessions, and entitlement.

Reading memory is public. Acting on it is not — scans spend real money and touch
someone else's infrastructure, so every write path asks this module whether the
caller is entitled.

Two deliberate choices:

* **Passwords are hashed with scrypt** from the standard library, with a per-user
  salt and a version tag on the stored string so the parameters can be raised later
  without invalidating existing hashes.
* **Sessions store only a hash of the bearer token.** A dump of the `sessions`
  table does not let anyone log in. Same reasoning as never storing the password.

No card data is handled anywhere in this system. `provider_customer_id` is written
from a billing provider's webhook after checkout happens on the provider's domain.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg

from .db import transaction

log = logging.getLogger(__name__)

TRIAL_DAYS = int(os.getenv("MNEMOS_TRIAL_DAYS", "5"))
SESSION_DAYS = 30

# scrypt parameters. n=2**15 is ~100ms on commodity hardware in 2026 — slow enough
# to make offline cracking expensive, fast enough that login stays interactive.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P = 2**15, 8, 1
# scrypt needs 128 * N * r bytes = exactly 32 MiB at these parameters, which is
# also OpenSSL's default maxmem — so it fails on the boundary unless we raise it.
_SCRYPT_MAXMEM = 128 * _SCRYPT_N * _SCRYPT_R * 2
_HASH_VERSION = "scrypt1"

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 10


class AuthError(RuntimeError):
    """Bad credentials, unknown account, or an expired session."""


class NotEntitled(RuntimeError):
    """Authenticated, but the trial has ended and there is no active plan."""


@dataclass(frozen=True)
class Account:
    id: str
    email: str
    display_name: str | None


@dataclass(frozen=True)
class Entitlement:
    plan: str
    status: str
    trial_ends_at: datetime | None
    can_write: bool
    days_left: int

    @property
    def is_trial(self) -> bool:
        return self.plan == "trial"


# ---------------------------------------------------------------------------
# password hashing
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    if len(password) < MIN_PASSWORD_LEN:
        raise ValueError(f"password must be at least {MIN_PASSWORD_LEN} characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM, dklen=32,
    )
    return "$".join([
        _HASH_VERSION,
        str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P),
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    ])


def verify_password(password: str, stored: str) -> bool:
    """Constant-time comparison; malformed stored values fail closed."""
    try:
        version, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if version != _HASH_VERSION:
            return False
        candidate = hashlib.scrypt(
            password.encode(), salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p),
            maxmem=128 * int(n) * int(r) * 2, dklen=32,
        )
        return hmac.compare_digest(candidate, base64.b64decode(digest_b64))
    except Exception:
        log.warning("malformed password hash encountered; refusing")
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------------------------------------------------------------------------
# the service
# ---------------------------------------------------------------------------
class Accounts:
    """Account, session, and entitlement operations against CockroachDB."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.conn = conn

    # -- signup / login ----------------------------------------------------
    def sign_up(self, email: str, password: str, display_name: str | None = None) -> Account:
        """Create an account and start its trial, in one transaction.

        An account without a subscription row would be an account the entitlement
        check cannot reason about — and it fails closed, so the user would sign up
        and immediately be unable to do anything. Both land or neither does.
        """
        email = email.strip().lower()
        if not _EMAIL_RE.match(email):
            raise ValueError("invalid email address")
        pw_hash = hash_password(password)
        trial_ends = datetime.now(timezone.utc) + timedelta(days=TRIAL_DAYS)

        with transaction(self.conn) as cur:
            cur.execute(
                "INSERT INTO accounts (email, password_hash, display_name) "
                "VALUES (%s, %s, %s) ON CONFLICT (email) DO NOTHING "
                "RETURNING id, email, display_name",
                (email, pw_hash, display_name),
            )
            row = cur.fetchone()
            if row is None:
                raise ValueError("an account with that email already exists")
            account = Account(str(row["id"]), row["email"], row["display_name"])
            cur.execute(
                "INSERT INTO subscriptions (account_id, plan, status, trial_ends_at) "
                "VALUES (%s, 'trial', 'trialing', %s)",
                (account.id, trial_ends),
            )
        return account

    def log_in(self, email: str, password: str, *, user_agent: str | None = None) -> str:
        """Return an opaque bearer token. Raises AuthError on any failure.

        The error is deliberately identical for "no such account" and "wrong
        password" so the endpoint cannot be used to enumerate registered emails.
        """
        email = email.strip().lower()
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, password_hash, disabled_at FROM accounts WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()

        if row is None:
            # Spend comparable time so absence is not detectable by timing.
            verify_password(password, hash_password("placeholder-not-a-real-secret"))
            raise AuthError("invalid email or password")
        if row["disabled_at"] is not None:
            raise AuthError("account disabled")
        if not verify_password(password, row["password_hash"]):
            raise AuthError("invalid email or password")

        token = secrets.token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
        with transaction(self.conn) as cur:
            cur.execute(
                "INSERT INTO sessions (account_id, token_sha256, user_agent, expires_at) "
                "VALUES (%s, %s, %s, %s)",
                (row["id"], _token_hash(token), user_agent, expires),
            )
            cur.execute("UPDATE accounts SET last_login_at = now() WHERE id = %s", (row["id"],))
        return token

    def log_out(self, token: str) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "UPDATE sessions SET revoked_at = now() "
                "WHERE token_sha256 = %s AND revoked_at IS NULL",
                (_token_hash(token),),
            )

    def account_for_token(self, token: str) -> Account | None:
        if not token:
            return None
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT a.id, a.email, a.display_name FROM sessions s "
                "JOIN accounts a ON a.id = s.account_id "
                "WHERE s.token_sha256 = %s AND s.revoked_at IS NULL "
                "AND s.expires_at > now() AND a.disabled_at IS NULL",
                (_token_hash(token),),
            )
            row = cur.fetchone()
        return Account(str(row["id"]), row["email"], row["display_name"]) if row else None

    # -- entitlement -------------------------------------------------------
    def entitlement(self, account_id: str) -> Entitlement:
        """What this account may do right now.

        Fails closed: a missing subscription row, an unreadable table, or an
        unrecognised status all resolve to "cannot write". The expensive direction
        is the one that spends money on someone else's infrastructure.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT plan, status, trial_ends_at, current_period_end "
                    "FROM subscriptions WHERE account_id = %s",
                    (account_id,),
                )
                row = cur.fetchone()
        except Exception as exc:
            log.error("entitlement lookup failed for %s (%s) — denying", account_id, exc)
            return Entitlement("unknown", "unreadable", None, False, 0)

        if row is None:
            return Entitlement("none", "expired", None, False, 0)

        now = datetime.now(timezone.utc)
        trial_ends = row["trial_ends_at"]
        if trial_ends is not None and trial_ends.tzinfo is None:
            trial_ends = trial_ends.replace(tzinfo=timezone.utc)

        days_left = 0
        if trial_ends is not None:
            days_left = max(0, (trial_ends - now).days + (1 if trial_ends > now else 0))

        can_write = False
        if row["status"] == "active":
            can_write = True
        elif row["status"] == "trialing" and trial_ends is not None and trial_ends > now:
            can_write = True

        return Entitlement(
            plan=row["plan"], status=row["status"], trial_ends_at=trial_ends,
            can_write=can_write, days_left=days_left,
        )

    def require_write(self, account_id: str) -> Entitlement:
        ent = self.entitlement(account_id)
        if not ent.can_write:
            raise NotEntitled(
                "trial ended and no active plan — reading memory stays free, "
                "but scans spend real resources"
            )
        return ent

    # -- billing provider callbacks ---------------------------------------
    def activate_plan(
        self, account_id: str, *, provider_customer_id: str,
        provider_subscription_id: str, current_period_end: datetime,
    ) -> None:
        """Called from the billing provider's webhook after checkout succeeds.

        Checkout happens entirely on the provider's domain; this system never sees
        a card number, and there is no code path in it that could accept one.
        """
        with transaction(self.conn) as cur:
            cur.execute(
                "UPDATE subscriptions SET plan = 'pro', status = 'active', "
                "provider_customer_id = %s, provider_subscription_id = %s, "
                "current_period_end = %s, updated_at = now() WHERE account_id = %s",
                (provider_customer_id, provider_subscription_id,
                 current_period_end, account_id),
            )

    def expire_overdue_trials(self) -> int:
        """Flip trialing rows whose window has closed. Idempotent."""
        with transaction(self.conn) as cur:
            cur.execute(
                "UPDATE subscriptions SET status = 'expired', plan = 'none', "
                "updated_at = now() WHERE status = 'trialing' AND trial_ends_at <= now() "
                "RETURNING id"
            )
            return len(cur.fetchall())

    def summary(self) -> dict[str, Any]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS accounts, "
                "count(*) FILTER (WHERE s.status = 'trialing') AS trialing, "
                "count(*) FILTER (WHERE s.status = 'active') AS active, "
                "count(*) FILTER (WHERE s.status = 'expired') AS expired "
                "FROM accounts a LEFT JOIN subscriptions s ON s.account_id = a.id"
            )
            return {k: int(v) for k, v in dict(cur.fetchone()).items()}
