"""The authorised sandbox corpus.

MNEMOS is a reconnaissance tool, so the demo must not point it at infrastructure
nobody authorised. This module is a fixed, offline corpus standing in for a target
we own: the scanner parses it with exactly the same code path it uses against a
live host, but no packet leaves the machine.

`PASS_TWO_EXTRA` is the point of the whole demo. It is the one genuinely new thing
that appears on the second visit. Everything else is unchanged, so a memoryless
agent would re-report all of it and a remembering agent reports only the new bundle.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxAsset:
    host: str
    kind: str
    url: str
    body: str


ROOT_DOMAIN = "sandbox.mnemos.test"

# Written authorisation for the sandbox, recorded on the target row.
AUTHORISATION = "MNEMOS project-owned sandbox corpus; offline fixture, no live hosts."

SCOPE_RULES: list[tuple[str, str, str]] = [
    ("*.sandbox.mnemos.test", "allow", "Owned sandbox estate"),
    ("sandbox.mnemos.test", "allow", "Apex of the owned sandbox estate"),
    # Explicit carve-out: the guard must refuse this even though the wildcard
    # above would otherwise match it.
    ("admin.sandbox.mnemos.test", "deny", "Out of scope by written agreement"),
    # Not ours at all. Present so the demo can prove the guard denies it.
    ("*.partner-bank.test", "deny", "Third party — never in scope"),
]


# One third-party script, deployed by the same team to two different properties.
# It is served from both estates byte-for-byte, which is what makes the correlation
# in `MemoryIntelligence.correlations()` a real finding rather than a coincidence:
# neither scan can know the file is shared, because each only ever sees one estate.
SHARED_VENDOR_BUNDLE = """
        const VENDOR_ANALYTICS = "https://cdn.vendor-analytics.test/v3/collect";
        const STRIPE_PUBLISHABLE = "pk_live_51KxSampleSandboxKeyDoNotUse00";
        navigator.sendBeacon(VENDOR_ANALYTICS, JSON.stringify(payload));
        """


PASS_ONE: list[SandboxAsset] = [
    SandboxAsset(
        host="cdn.sandbox.mnemos.test",
        kind="js_bundle",
        url="https://cdn.sandbox.mnemos.test/vendor-analytics.js",
        body=SHARED_VENDOR_BUNDLE,
    ),
    SandboxAsset(
        host="www.sandbox.mnemos.test",
        kind="js_bundle",
        url="https://www.sandbox.mnemos.test/static/app.4f21.js",
        body="""
        const API_ROOT = "https://api.sandbox.mnemos.test/v2";
        // TODO(remove before launch): staging key left in the bundle
        const STRIPE_PUBLISHABLE = "pk_live_51KxSampleSandboxKeyDoNotUse00";
        fetch(API_ROOT + "/users/me", { headers: { Authorization: bearer } });
        fetch(API_ROOT + "/admin/export?format=csv");
        fetch(API_ROOT + "/billing/invoices");
        const DEBUG = window.location.search.includes("debug=1");
        """,
    ),
    SandboxAsset(
        host="api.sandbox.mnemos.test",
        kind="url",
        url="https://api.sandbox.mnemos.test/.well-known/openapi.json",
        body="""
        {"paths": {"/v2/users/{id}": {"get": {"security": []}},
                   "/v2/admin/export": {"get": {"security": []}},
                   "/v2/billing/invoices": {"get": {"security": [{"bearer": []}]}}}}
        """,
    ),
    SandboxAsset(
        host="legacy.sandbox.mnemos.test",
        kind="url",
        url="https://legacy.sandbox.mnemos.test/server-status",
        body="Apache Server Status for legacy.sandbox.mnemos.test (via 10.0.4.19)",
    ),
]

# Second visit: the estate is unchanged except for one newly deployed bundle.
PASS_TWO_EXTRA: list[SandboxAsset] = [
    SandboxAsset(
        host="beta.sandbox.mnemos.test",
        kind="js_bundle",
        url="https://beta.sandbox.mnemos.test/static/beta.9c02.js",
        body="""
        const API_ROOT = "https://api.sandbox.mnemos.test/v2";
        const INTERNAL_METRICS = "https://metrics.internal.sandbox.mnemos.test/ingest";
        // new in this release
        const SENTRY_DSN = "https://abc123@o1.ingest.sentry.io/42";
        fetch(INTERNAL_METRICS, { method: "POST" });
        """,
    ),
]

# The out-of-scope probe the guard must refuse, regardless of what the scanner found.
OUT_OF_SCOPE_PROBE = "admin.sandbox.mnemos.test"


# ---------------------------------------------------------------------------
# A second, separate estate.
#
# It exists so correlation has something true to find. `vendor-analytics.js` here
# is byte-identical to a bundle on the first estate — the same third-party script
# deployed by the same team to two different properties. Neither scan can know
# that. Only memory, joining on the content address, can.
# ---------------------------------------------------------------------------
SECOND_ROOT_DOMAIN = "acme-labs.mnemos.test"

SECOND_AUTHORISATION = (
    "MNEMOS project-owned second sandbox corpus; offline fixture, no live hosts."
)

SECOND_SCOPE_RULES: list[tuple[str, str, str]] = [
    ("*.acme-labs.mnemos.test", "allow", "Second owned sandbox estate"),
    ("acme-labs.mnemos.test", "allow", "Apex of the second owned estate"),
    ("payments.acme-labs.mnemos.test", "deny", "Cardholder scope — excluded by agreement"),
]

SECOND_ESTATE: list[SandboxAsset] = [
    SandboxAsset(
        host="www.acme-labs.mnemos.test",
        kind="js_bundle",
        url="https://www.acme-labs.mnemos.test/assets/vendor-analytics.js",
        body=SHARED_VENDOR_BUNDLE,
    ),
    SandboxAsset(
        host="docs.acme-labs.mnemos.test",
        kind="url",
        url="https://docs.acme-labs.mnemos.test/server-status",
        body="Apache Server Status for docs.acme-labs.mnemos.test (via 10.9.1.4)",
    ),
]


def pass_assets(pass_no: int) -> list[SandboxAsset]:
    """What the scanner sees on visit `pass_no` to the first estate."""
    if pass_no <= 1:
        return list(PASS_ONE)
    return list(PASS_ONE) + list(PASS_TWO_EXTRA)


def second_estate_assets() -> list[SandboxAsset]:
    return list(SECOND_ESTATE)
