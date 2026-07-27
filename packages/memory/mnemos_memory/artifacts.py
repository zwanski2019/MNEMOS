"""Artifact storage — Amazon S3.

Raw bodies (JS bundles, API responses, page sources) are large, immutable, and
rarely read; vectors and metadata are small, mutable, and read on every cycle. So
they live in different places: bytes go to S3, the **content address** goes to
CockroachDB. Memory stays queryable and joinable in SQL next to the vectors and the
audit trail, and the blobs stay cheap.

Keys are content-addressed (`artifacts/ab/abcdef…`), which makes the store naturally
idempotent: the same bundle seen on ten hosts is uploaded once. A re-scan that finds
nothing changed uploads nothing at all, which is the storage-layer version of the
same idea dedup applies to findings.
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

log = logging.getLogger(__name__)


def key_for(sha256: str) -> str:
    """Content-addressed key with a two-char prefix to spread S3 partitions."""
    return f"artifacts/{sha256[:2]}/{sha256}"


class ArtifactStore(Protocol):
    backend: str

    def put(self, sha256: str, body: bytes, content_type: str) -> tuple[str | None, str]:
        """Return ``(bucket, key)``. Bucket is None when nothing was uploaded."""
        ...


class S3ArtifactStore:
    """Amazon S3, content-addressed and idempotent."""

    backend = "s3"

    def __init__(self, bucket: str, region: str | None = None) -> None:
        import boto3

        self.bucket = bucket
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self._s3 = boto3.client("s3", region_name=self.region)

    def ensure_bucket(self) -> None:
        """Create the bucket if it is missing. Safe to call repeatedly."""
        from botocore.exceptions import ClientError

        try:
            self._s3.head_bucket(Bucket=self.bucket)
            return
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("404", "NoSuchBucket", "403"):
                raise
            if exc.response["Error"]["Code"] == "403":
                # Exists but owned by someone else — fail loudly rather than
                # silently writing findings evidence somewhere we do not control.
                raise

        kwargs: dict = {"Bucket": self.bucket}
        if self.region != "us-east-1":
            kwargs["CreateBucketConfiguration"] = {"LocationConstraint": self.region}
        self._s3.create_bucket(**kwargs)

        # Recon artifacts are someone else's source code and API responses. They are
        # never public, and they are never overwritten once written.
        self._s3.put_public_access_block(
            Bucket=self.bucket,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True, "IgnorePublicAcls": True,
                "BlockPublicPolicy": True, "RestrictPublicBuckets": True,
            },
        )
        self._s3.put_bucket_encryption(
            Bucket=self.bucket,
            ServerSideEncryptionConfiguration={
                "Rules": [{"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]
            },
        )
        self._s3.put_bucket_versioning(
            Bucket=self.bucket, VersioningConfiguration={"Status": "Enabled"}
        )
        log.info("created artifact bucket %s in %s", self.bucket, self.region)

    def put(self, sha256: str, body: bytes, content_type: str) -> tuple[str | None, str]:
        from botocore.exceptions import ClientError

        key = key_for(sha256)
        try:
            self._s3.head_object(Bucket=self.bucket, Key=key)
            return self.bucket, key  # already stored; content-addressed means identical
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("404", "NoSuchKey", "NotFound"):
                raise

        self._s3.put_object(
            Bucket=self.bucket, Key=key, Body=body, ContentType=content_type,
            ServerSideEncryption="AES256",
            Metadata={"sha256": sha256},
        )
        return self.bucket, key


class NullArtifactStore:
    """No upload. Used offline; the content address is still recorded."""

    backend = "none"

    def put(self, sha256: str, body: bytes, content_type: str) -> tuple[str | None, str]:
        return None, key_for(sha256)


def get_artifact_store(force: str | None = None) -> ArtifactStore:
    """Select a store. ``MNEMOS_ARTIFACT_STORE=s3|none``, default auto."""
    from .embeddings import aws_credentials_usable

    choice = (force or os.getenv("MNEMOS_ARTIFACT_STORE") or "auto").lower()
    bucket = os.getenv("S3_ARTIFACT_BUCKET", "")

    if choice == "none":
        return NullArtifactStore()

    if choice == "s3":
        if not bucket:
            raise ValueError("MNEMOS_ARTIFACT_STORE=s3 requires S3_ARTIFACT_BUCKET")
        return S3ArtifactStore(bucket)

    if bucket and aws_credentials_usable():
        try:
            store = S3ArtifactStore(bucket)
            store.ensure_bucket()
            return store
        except Exception as exc:  # pragma: no cover - depends on AWS state
            log.warning("S3 artifact store unavailable (%s); not uploading bodies", exc)

    return NullArtifactStore()
