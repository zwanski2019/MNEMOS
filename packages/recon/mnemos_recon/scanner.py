"""Deterministic scanner core.

No model runs here. Given the same bytes this produces the same observations every
time, which is what makes the dedup story meaningful: when the second pass reports
something new, it is because the target changed, not because a sampler got creative.

The production deployment runs the Go implementation of this same contract on AWS
Lambda (`services/scanner`); this is the reference implementation the Go worker is
tested against.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Ordered most specific first — the first pattern to match wins, so a Stripe live
# key is never downgraded to the generic "long opaque string" rule.
_SECRET_PATTERNS: list[tuple[str, str, str]] = [
    (r"pk_live_[A-Za-z0-9]{16,}", "Stripe publishable live key in client bundle", "medium"),
    (r"sk_live_[A-Za-z0-9]{16,}", "Stripe SECRET key in client bundle", "critical"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id in client bundle", "critical"),
    (r"https://[0-9a-f]+@[a-z0-9.]+sentry\.io/\d+", "Sentry DSN in client bundle", "low"),
]

_ENDPOINT = re.compile(r"""["'`](/(?:v\d+/)?[A-Za-z0-9_\-/{}]{2,60})["'`]""")
# The optional `userinfo@` group is not captured on purpose: a Sentry DSN looks
# like https://<key>@o1.ingest.sentry.io/42, and without this the key itself gets
# reported as a discovered host.
_ABS_URL = re.compile(
    r"https?://(?:[A-Za-z0-9_\-.:%]+@)?([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)(?::\d+)?"
)
_UNAUTH_PATH = re.compile(r'"(/[^"]+)":\s*\{"get":\s*\{"security":\s*\[\]')


@dataclass(frozen=True)
class Observation:
    """One deterministic fact about the target. Not yet a finding."""

    host: str
    kind: str          # secret | endpoint | subdomain | exposure
    detail: str
    severity: str
    evidence: str


def extract_hosts(body: str) -> set[str]:
    return {m.group(1).lower() for m in _ABS_URL.finditer(body)}


def scan(host: str, url: str, body: str) -> list[Observation]:
    """Parse one artifact into observations. Pure function of its inputs."""
    seen: set[tuple[str, str]] = set()
    out: list[Observation] = []

    def add(kind: str, detail: str, severity: str, evidence: str) -> None:
        key = (kind, detail)
        if key in seen:
            return
        seen.add(key)
        out.append(Observation(host, kind, detail, severity, evidence.strip()[:400]))

    for pattern, detail, severity in _SECRET_PATTERNS:
        for match in re.finditer(pattern, body):
            add("secret", detail, severity, f"{url} :: {match.group(0)[:12]}…")

    for match in _UNAUTH_PATH.finditer(body):
        path = match.group(1)
        severity = "high" if "admin" in path else "medium"
        add("exposure", f"Unauthenticated API path {path}", severity, f"{url} :: {path}")

    for match in _ENDPOINT.finditer(body):
        path = match.group(1)
        if "admin" in path:
            add("endpoint", f"Admin endpoint referenced from client: {path}", "medium",
                f"{url} :: {path}")

    if "Server Status for" in body:
        add("exposure", "Apache mod_status exposed", "medium", f"{url} :: server-status")

    for discovered in sorted(extract_hosts(body)):
        if discovered != host:
            add("subdomain", f"Referenced host {discovered}", "info", f"{url} -> {discovered}")

    return out
