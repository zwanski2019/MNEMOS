"""Artifact storage: content addressing, idempotency, and the CockroachDB link.

The property that matters is that the two halves cannot drift: whatever key S3 gets
is the key CockroachDB records, and both are derived from the sha256 of the bytes.
"""

from __future__ import annotations

import hashlib
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")

from mnemos_memory import Memory, migrate  # noqa: E402
from mnemos_memory.artifacts import NullArtifactStore, key_for  # noqa: E402
from mnemos_memory.embeddings import HashingEmbedder  # noqa: E402

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


class RecordingStore:
    """Stands in for S3 and remembers what it was asked to store."""

    backend = "recording"

    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes]] = []
        self.objects: dict[str, bytes] = {}

    def put(self, sha256: str, body: bytes, content_type: str) -> tuple[str | None, str]:
        key = key_for(sha256)
        self.puts.append((sha256, body))
        self.objects.setdefault(key, body)  # content-addressed: never overwrite
        return "test-bucket", key


@pytest.fixture(scope="session", autouse=True)
def _schema():
    migrate(verbose=False)


@pytest.fixture()
def target_and_mem():
    store = RecordingStore()
    mem = Memory(embedder=HashingEmbedder(), artifacts=store)
    suffix = uuid.uuid4().hex[:8]
    tid = mem.create_target(
        name=f"art-{suffix}", root_domain=f"{suffix}.art.test", authorisation="unit test",
        scope_rules=[(f"*.{suffix}.art.test", "allow", "owned")],
    )
    yield mem, tid, store
    mem.close()


def test_key_is_derived_from_content_hash():
    body = b"const KEY='pk_live_x';"
    sha = hashlib.sha256(body).hexdigest()
    assert key_for(sha) == f"artifacts/{sha[:2]}/{sha}"


def test_stored_key_matches_what_cockroachdb_records(target_and_mem):
    mem, tid, store = target_and_mem
    body = b"const API='https://api.example.com/v2';"
    sha = hashlib.sha256(body).hexdigest()

    artifact_id = mem.record_artifact(tid, None, body, content_type="application/javascript")

    with mem.conn.cursor() as cur:
        cur.execute(
            "SELECT sha256, s3_bucket, s3_key, byte_len FROM artifacts WHERE id = %s",
            (artifact_id,),
        )
        row = cur.fetchone()

    assert row["sha256"] == sha
    assert row["s3_bucket"] == "test-bucket"
    assert row["s3_key"] == key_for(sha), "the DB must point at the object we actually stored"
    assert row["byte_len"] == len(body)
    assert key_for(sha) in store.objects


def test_same_bytes_are_stored_once(target_and_mem):
    """The same bundle served from ten hosts must not become ten objects."""
    mem, tid, store = target_and_mem
    body = b"shared vendor bundle"

    first = mem.record_artifact(tid, None, body)
    second = mem.record_artifact(tid, None, body)

    assert first == second, "same content must resolve to the same artifact row"
    assert len(store.objects) == 1


def test_null_store_still_records_the_address():
    """Offline, we lose the bytes but must not lose the content address."""
    store = NullArtifactStore()
    sha = hashlib.sha256(b"x").hexdigest()
    bucket, key = store.put(sha, b"x", "text/plain")
    assert bucket is None
    assert key == key_for(sha)
