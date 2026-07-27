"""Covenant acceptance receipts and scope grants.

The chain this exists to produce, for any scan the system ever performs:

    this human accepted this covenant text at this time
      → asserted authorisation for this scope, with evidence
        → and this scan is bound to both, by foreign key

No hand-rolled primitives. Ed25519 and SHA-256 come from `cryptography`; the
protocol on top of them — canonical JSON, the receipt shape, the append-only
ledger — is ours, which is the part that has to be got right.

Two properties worth stating plainly:

* **Receipts are verifiable without trusting us.** The signed document is stored
  byte-for-byte as it was signed, so verification never reconstructs it and never
  gets the reconstruction subtly wrong. A third party with the public key can
  check a receipt we have no ability to alter.

* **Consent is not silently re-mapped.** A receipt names the exact covenant text
  by hash. Change the covenant and every existing acceptance stops satisfying the
  operator tier, because they consented to different words.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .db import transaction

log = logging.getLogger(__name__)

RECEIPT_VERSION = 1
MAX_GRANT_DAYS = 90


class CovenantError(RuntimeError):
    """Receipt could not be produced or verified."""


class NotAuthorised(RuntimeError):
    """No live grant covers this target. The scanner must not dispatch."""


def canonical_json(doc: dict[str, Any]) -> bytes:
    """Sorted keys, no whitespace, UTF-8.

    The signature is over these exact bytes. Any drift between the signer's
    serialisation and the verifier's produces a false rejection, so this is the
    single definition and both sides call it.
    """
    return json.dumps(doc, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _pepper() -> bytes:
    """Pepper for identity binding and IP hashing.

    Lives outside CockroachDB on purpose: a database dump must not be enough to
    correlate a receipt back to an email address or an IP.
    """
    value = os.getenv("MNEMOS_IDENTITY_PEPPER", "")
    if not value:
        # Refusing here rather than defaulting: a silently-empty pepper would make
        # identity_binding a plain hash of the email, which is trivially reversible
        # against a wordlist of addresses.
        raise CovenantError(
            "MNEMOS_IDENTITY_PEPPER is not set — refusing to create receipts with "
            "an unpeppered identity binding"
        )
    return value.encode("utf-8")


def identity_binding(email: str) -> str:
    """Searchable, non-reversible handle for an email address."""
    normalised = email.strip().lower().encode("utf-8")
    return hmac.new(_pepper(), normalised, hashlib.sha256).hexdigest()


def peppered_hash(value: str) -> str:
    """For IP and user-agent. Peppered so a dump cannot be brute-forced."""
    return hmac.new(_pepper(), value.encode("utf-8"), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------------------
# signing keys
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SigningKey:
    key_id: str
    private: Ed25519PrivateKey

    @property
    def public_b64(self) -> str:
        raw = self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return _b64(raw)


def load_signing_key() -> SigningKey:
    """Load the receipt signing key from the environment.

    Deliberately not auto-generated on first use: a key that appears by magic is a
    key nobody backed up, and losing it makes every prior receipt unverifiable.
    """
    seed_b64 = os.getenv("MNEMOS_RECEIPT_KEY", "")
    key_id = os.getenv("MNEMOS_RECEIPT_KEY_ID", "receipt-v1")
    if not seed_b64:
        raise CovenantError(
            "MNEMOS_RECEIPT_KEY is not set. Generate one with:\n"
            "  python -c \"import os,base64;print(base64.urlsafe_b64encode("
            "os.urandom(32)).decode().rstrip('='))\"\n"
            "and store it with the KEK, never in CockroachDB."
        )
    seed = _unb64(seed_b64)
    if len(seed) != 32:
        raise CovenantError("MNEMOS_RECEIPT_KEY must decode to exactly 32 bytes")
    return SigningKey(key_id, Ed25519PrivateKey.from_private_bytes(seed))


def verify_receipt(payload: dict[str, Any], signature_b64: str, public_b64: str) -> bool:
    """Check a receipt against a public key. Any failure is False, never an exception."""
    try:
        public = Ed25519PublicKey.from_public_bytes(_unb64(public_b64))
        public.verify(_unb64(signature_b64), canonical_json(payload))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# receipts and grants
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Receipt:
    id: str
    payload: dict[str, Any]
    signature: str
    key_id: str


@dataclass(frozen=True)
class Grant:
    id: str
    operator_id: str
    scope_spec: str
    expires_at: datetime
    revoked_at: datetime | None

    @property
    def live(self) -> bool:
        now = datetime.now(timezone.utc)
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return self.revoked_at is None and expires > now


class Accountability:
    """Covenant receipts, scope grants, and the dispatch check."""

    def __init__(self, conn) -> None:
        self.conn = conn

    # -- covenant ---------------------------------------------------------
    def accept_covenant(
        self,
        *,
        operator_id: str,
        email: str,
        covenant_text: str,
        covenant_version: str,
        ip: str,
        user_agent: str,
    ) -> Receipt:
        """Record a signed acceptance. Append-only; never updates a prior receipt."""
        key = load_signing_key()
        payload: dict[str, Any] = {
            "v": RECEIPT_VERSION,
            "covenant_hash": sha256_hex(covenant_text),
            "covenant_version": covenant_version,
            "operator_id": operator_id,
            "identity_binding": identity_binding(email),
            "accepted_at": datetime.now(timezone.utc)
                .isoformat(timespec="seconds").replace("+00:00", "Z"),
            "ip_hash": peppered_hash(ip),
            "user_agent_hash": peppered_hash(user_agent),
            "nonce": _b64(os.urandom(32)),
        }
        signature = _b64(key.private.sign(canonical_json(payload)))

        with transaction(self.conn) as cur:
            cur.execute(
                "INSERT INTO covenant_receipts (operator_id, kind, covenant_version, "
                "covenant_hash, payload, signature, key_id) "
                "VALUES (%s, 'acceptance', %s, %s, %s, %s, %s) RETURNING id",
                (operator_id, covenant_version, payload["covenant_hash"],
                 json.dumps(payload), signature, key.key_id),
            )
            receipt_id = str(cur.fetchone()["id"])
        return Receipt(receipt_id, payload, signature, key.key_id)

    def verify_stored_receipt(self, receipt_id: str) -> dict[str, Any]:
        """Third-party verification. Returns the public key and the verdict.

        Because the signed bytes are stored verbatim, a tampered row fails here
        even though the append-only grant already makes tampering hard.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, payload, signature, key_id, covenant_version, created_at "
                "FROM covenant_receipts WHERE id = %s", (receipt_id,),
            )
            row = cur.fetchone()
        if row is None:
            return {"found": False}

        public_b64 = load_signing_key().public_b64
        valid = verify_receipt(dict(row["payload"]), row["signature"], public_b64)
        return {
            "found": True,
            "receipt_id": str(row["id"]),
            "covenant_version": row["covenant_version"],
            "key_id": row["key_id"],
            "public_key": public_b64,
            "algorithm": "Ed25519",
            "signature_valid": valid,
            "created_at": row["created_at"].isoformat(),
        }

    def current_receipt(self, operator_id: str, covenant_hash: str) -> str | None:
        """The operator's live acceptance of *this exact* covenant text.

        Matching on the hash is what stops consent being silently re-mapped: edit
        the covenant and this returns None until the operator accepts again.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM covenant_receipts WHERE operator_id = %s "
                "AND covenant_hash = %s AND kind = 'acceptance' "
                "AND id NOT IN (SELECT supersedes FROM covenant_receipts "
                "               WHERE supersedes IS NOT NULL AND kind = 'revocation') "
                "ORDER BY created_at DESC LIMIT 1",
                (operator_id, covenant_hash),
            )
            row = cur.fetchone()
        return str(row["id"]) if row else None

    # -- grants -----------------------------------------------------------
    def issue_grant(
        self,
        *,
        operator_id: str,
        receipt_id: str,
        scope_spec: str,
        evidence_kind: str,
        evidence_ref: str,
        granted_by: str,
        days: int = 30,
        target_id: str | None = None,
    ) -> Grant:
        if days > MAX_GRANT_DAYS:
            raise ValueError(f"grants may not exceed {MAX_GRANT_DAYS} days")
        if days <= 0:
            raise ValueError("grant duration must be positive")

        expires = datetime.now(timezone.utc) + timedelta(days=days)
        with transaction(self.conn) as cur:
            cur.execute(
                "INSERT INTO scope_grants (operator_id, receipt_id, target_id, scope_spec, "
                "evidence_kind, evidence_ref, expires_at, granted_by) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "RETURNING id, expires_at, revoked_at",
                (operator_id, receipt_id, target_id, scope_spec, evidence_kind,
                 evidence_ref, expires, granted_by),
            )
            row = cur.fetchone()
        return Grant(str(row["id"]), operator_id, scope_spec, row["expires_at"],
                     row["revoked_at"])

    def revoke_grant(self, grant_id: str, *, revoked_by: str, reason: str) -> None:
        with transaction(self.conn) as cur:
            cur.execute(
                "UPDATE scope_grants SET revoked_at = now(), revoked_by = %s, "
                "revocation_reason = %s WHERE id = %s AND revoked_at IS NULL",
                (revoked_by, reason, grant_id),
            )

    def resolve_grant(self, operator_id: str, host: str) -> Grant | None:
        """Find a live grant covering `host`, using the scope engine's own matcher.

        Deliberately not a second, looser parser. `fnmatch` here is the same rule
        `Memory.check_scope` applies to `scope_decisions`, so a host cannot be in
        scope for dispatch and out of scope for the guard, or vice versa.
        """
        import fnmatch

        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, scope_spec, expires_at, revoked_at FROM scope_grants "
                "WHERE operator_id = %s AND revoked_at IS NULL AND expires_at > now() "
                "ORDER BY expires_at DESC",
                (operator_id,),
            )
            rows = cur.fetchall()

        for row in rows:
            if fnmatch.fnmatch(host.lower(), str(row["scope_spec"]).lower()):
                return Grant(str(row["id"]), operator_id, row["scope_spec"],
                             row["expires_at"], row["revoked_at"])
        return None

    # -- the dispatch gate ------------------------------------------------
    def authorise_scan(self, operator_id: str, host: str) -> tuple[str, str]:
        """Return (grant_id, receipt_id) or refuse. There is no third outcome.

        Never falls back to warn-and-continue. A scanner that proceeds without a
        resolvable grant is the failure mode this entire part exists to prevent.
        """
        with self.conn.cursor() as cur:
            cur.execute("SELECT tier FROM accounts WHERE id = %s", (operator_id,))
            row = cur.fetchone()

        if row is None:
            raise NotAuthorised("unknown operator")
        if row["tier"] not in ("operator", "admin"):
            raise NotAuthorised(
                f"tier '{row['tier']}' may not dispatch scans — "
                f"the covenant must be accepted and approved first"
            )

        grant = self.resolve_grant(operator_id, host)
        if grant is None:
            raise NotAuthorised(f"no live grant covers {host}")

        with self.conn.cursor() as cur:
            cur.execute("SELECT receipt_id FROM scope_grants WHERE id = %s", (grant.id,))
            receipt_id = str(cur.fetchone()["receipt_id"])
        return grant.id, receipt_id

    def promote_to_operator(
        self, operator_id: str, *, approved_by: str, receipt_id: str
    ) -> None:
        """pending -> operator. Requires an explicit approval action.

        Manual for now. The automated path would attach an identity-verification
        provider result and a reviewed scope attestation to this same call; the
        signature it produces is the audit anchor either way.
        """
        with transaction(self.conn) as cur:
            cur.execute(
                "SELECT operator_id FROM covenant_receipts WHERE id = %s", (receipt_id,)
            )
            row = cur.fetchone()
            if row is None or str(row["operator_id"]) != operator_id:
                raise CovenantError("receipt does not belong to this operator")
            cur.execute(
                "UPDATE accounts SET tier = 'operator', tier_granted_at = now(), "
                "tier_granted_by = %s WHERE id = %s AND tier = 'pending'",
                (approved_by, operator_id),
            )
