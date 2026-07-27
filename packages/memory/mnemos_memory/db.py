"""CockroachDB connection handling and migrations."""

from __future__ import annotations

import logging
import os
import pathlib
import time
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row

log = logging.getLogger(__name__)

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"

DEFAULT_DSN = "postgresql://root@localhost:26257/mnemos?sslmode=disable"

# CockroachDB raises 40001 on contention; retrying is the documented client
# responsibility rather than a nicety, so it lives at the connection layer.
_RETRYABLE = {"40001"}
_MAX_RETRIES = 5


def dsn() -> str:
    return os.getenv("DATABASE_URL") or DEFAULT_DSN


def connect(autocommit: bool = True) -> psycopg.Connection:
    conn = psycopg.connect(dsn(), row_factory=dict_row, connect_timeout=15)
    conn.autocommit = autocommit
    return conn


@contextmanager
def transaction(conn: psycopg.Connection) -> Iterator[psycopg.Cursor]:
    """Run a block inside one transaction. Single attempt.

    The scope+target write and the finding write both need to be all-or-nothing;
    a half-written scope rule is the one failure mode that could let the agent act
    outside its authorisation.

    Any exception — including a domain error like CostCeilingExceeded raised from
    inside the block — rolls the transaction back before it propagates. Callers that
    need work to survive the exception must therefore let the block close first and
    raise afterwards. See ``Memory.charge``.

    Retrying is deliberately *not* done here: a context manager cannot re-run its
    caller's block, so a retry loop around ``yield`` would silently commit a partial
    attempt. Use :func:`run_in_transaction` when you need retry-on-contention.
    """
    previous = conn.autocommit
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        try:
            conn.autocommit = previous
        except psycopg.Error:  # connection already broken; nothing to restore
            pass


def run_in_transaction(conn: psycopg.Connection, fn, *, max_retries: int = _MAX_RETRIES):
    """Call ``fn(cursor)`` in a transaction, retrying CockroachDB serialisation errors.

    CockroachDB uses serialisable isolation, so a contended write can fail with
    40001 and is expected to be retried by the client. ``fn`` must be idempotent
    because it may be invoked more than once.
    """
    for attempt in range(1, max_retries + 1):
        try:
            with transaction(conn) as cur:
                return fn(cur)
        except psycopg.errors.Error as exc:
            if getattr(exc, "sqlstate", None) not in _RETRYABLE or attempt == max_retries:
                raise
            backoff = 0.05 * (2 ** (attempt - 1))
            log.warning(
                "CockroachDB retryable error, attempt %d/%d, sleeping %.2fs",
                attempt, max_retries, backoff,
            )
            time.sleep(backoff)


def _split_statements(sql: str) -> list[str]:
    """Naive splitter — our migrations contain no semicolons inside literals."""
    out, buf = [], []
    for line in sql.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        buf.append(line)
        if stripped.endswith(";"):
            out.append("\n".join(buf).strip())
            buf = []
    if buf:
        out.append("\n".join(buf).strip())
    return [s for s in out if s]


def migrate(verbose: bool = True) -> list[str]:
    """Apply every migration in order. Statements are individually idempotent."""
    applied: list[str] = []
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        raise FileNotFoundError(f"no migrations found in {MIGRATIONS_DIR}")

    # The first migration creates the database, so connect to the cluster default.
    bootstrap = os.getenv("DATABASE_URL") or DEFAULT_DSN
    conn = psycopg.connect(bootstrap.replace("/mnemos?", "/defaultdb?"), autocommit=True)
    try:
        for path in files:
            for stmt in _split_statements(path.read_text()):
                with conn.cursor() as cur:
                    cur.execute(stmt)
            applied.append(path.name)
            if verbose:
                log.info("applied %s", path.name)
    finally:
        conn.close()
    return applied
