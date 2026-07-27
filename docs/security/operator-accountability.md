# Operator accountability

MNEMOS points a scanner at other people's infrastructure. Registration is
therefore a weapons-control surface, and the controlling risk is not spam — it is
an unattributable operator directing the scanner at a system that never consented.

The property this document describes: **for any scan MNEMOS performs, we can
produce a signed chain from a human's covenant acceptance to that scan.**

## Status

| Part | State |
|---|---|
| A1 tiers | Built — `accounts.tier`, enforced in `authorise_scan` |
| A2 signed receipts | Built — Ed25519, canonical JSON, append-only ledger |
| A3 scope grants | Built — mandatory expiry capped at 90 days, evidence_ref recorded |
| A4 structural binding | **Built — `agent_runs.grant_id`/`receipt_id` are NOT NULL FKs** |
| A3 domain-control proof | **Not built** — `evidence_ref` is recorded but DNS TXT verification is not implemented |
| B MNEMOS-GATE | **Not built** |
| C credentials at rest | Partial — Argon2id not yet swapped in; scrypt in use (see below) |
| D tokens & sessions | Partial — opaque bearer tokens exist; no refresh rotation, no JWT |
| E CockroachDB correctness | Verified — see findings below |
| F attacker tests | 3 of 21 rows covered (2, 3, 20) |

Nothing above is claimed as done that is not tested. `tests/security/` has 17
tests, all green.

## The chain

```
human accepts covenant text
  → covenant_receipts row: Ed25519 signature over canonical JSON,
    naming sha256(covenant_text) so consent is bound to exact wording
      → scope_grants row: references that receipt, carries evidence_ref,
        expires_at mandatory and ≤ 90 days
          → agent_runs row: grant_id + receipt_id, both NOT NULL FKs
```

The last arrow is the one that matters. `agent_runs.grant_id` and `receipt_id`
are `NOT NULL` foreign keys, so a scan that cannot name its authorisation is
rejected by CockroachDB. From `tests/security/`:

```python
def test_a_run_cannot_exist_without_naming_its_authorisation(mem):
    """Enforcement that lives only in a handler is not enforcement."""
    with pytest.raises(psycopg.errors.NotNullViolation):
        cur.execute("INSERT INTO agent_runs (target_id, pass_no, cost_ceiling_usd) ...")
```

## Tiers

| Tier | Obtained by | Scanner rights |
|---|---|---|
| `pending` | signup + email verification | none |
| `operator` | covenant signed, then explicit approval | scopes with a live grant, only |
| `admin` | out of band | grant review, revocation, audit export |

`pending → operator` requires `promote_to_operator()`, which verifies the receipt
belongs to that operator. It is a manual call today. The automated path attaches
an identity-verification result and a reviewed scope attestation to the same
call; the signature it produces is the audit anchor either way.

A `pending` account reaching the scanner is a P0, and is tested
(`test_pending_tier_cannot_dispatch`).

## Receipt format

```json
{
  "v": 1,
  "covenant_hash": "sha256 of the exact accepted text",
  "covenant_version": "2026.1",
  "operator_id": "uuid",
  "identity_binding": "hmac(pepper, normalized_email)",
  "accepted_at": "RFC3339 UTC",
  "ip_hash": "hmac(pepper, ip)",
  "user_agent_hash": "hmac(pepper, ua)",
  "nonce": "32 random bytes, base64url"
}
```

Signed with Ed25519 over `canonical_json()` — sorted keys, no whitespace, UTF-8.

Two deliberate choices:

**The signed document is stored verbatim.** Verification never reconstructs the
payload, so it can never reconstruct it subtly differently and produce a false
rejection.

**The pepper is mandatory.** `identity_binding` refuses to run without
`MNEMOS_IDENTITY_PEPPER` rather than defaulting to an empty one. An unpeppered
binding is a plain SHA-256 of an email address, which is reversible against a
wordlist in seconds. The pepper lives with the KEK, never in CockroachDB.

## Consent is never silently re-mapped

`current_receipt()` matches on `covenant_hash`. Change one character of the
covenant and every prior acceptance stops satisfying the operator tier, because
those people agreed to different words. Tested by
`test_changing_the_covenant_invalidates_prior_acceptance`.

## Third-party verification

`Accountability.verify_stored_receipt()` returns the public key, algorithm, and
verdict, so a receipt can be validated without trusting this system. The HTTP
endpoint (`GET /api/v1/receipts/:id/verify`) is **not yet wired**; the function
behind it is built and tested.

## Append-only ledger

`covenant_receipts` is granted `SELECT, INSERT` to `mnemos_agent` and nothing
else. Revocation is a new row with `kind = 'revocation'` pointing at `supersedes`,
never a mutation. Verified from outside the application in
`test_receipt_ledger_is_append_only` — `UPDATE` and `DELETE` both raise
`InsufficientPrivilege`.

## The bootstrap grant

Migration 008 seeds one grant, `…0003`, to bind rows created before this model
existed. It is **expired and revoked at creation**, so it is traceable in the
audit trail and can never satisfy `authorise_scan`. Tested by
`test_the_bootstrap_grant_can_never_authorise_a_scan`.

Binding legacy rows to a visible, dead grant was chosen over allowing NULL:
"created before accountability existed" is a fact worth being able to query, and
a nullable column would have hidden it *and* removed the structural guarantee for
every future row.

## Known gaps

Ranked by how much they weaken the chain:

1. **No domain-control proof.** `evidence_ref` records the claim
   (`bounty:`/`letter:`/`self_owned:`) but nothing verifies it. An operator can
   currently assert authorisation for a domain they do not control. This is the
   weakest link in the identity surface today.
2. **No gate (Part B).** Registration has no proof-of-work, so account creation is
   cheap at scale.
3. **Approval is manual and unauthenticated as a workflow.** `promote_to_operator`
   checks the receipt belongs to the operator but does not itself require an admin
   session — the caller is trusted. It needs the `admin` tier check that the HTTP
   layer would provide.
