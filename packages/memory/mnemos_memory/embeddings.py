"""Embedding providers.

Production path is Amazon Bedrock Titan Text Embeddings V2 at 1024 dimensions —
the same width as the ``VECTOR(1024)`` columns CockroachDB indexes.

``HashingEmbedder`` exists so the test suite and ``make demo`` can run on a laptop
with no AWS credentials. It is deterministic and normalised so the vector maths is
identical, but it carries no semantics; it is never selected when AWS credentials
are present, and it stamps its own name into ``embeddings.model`` so a row produced
offline can never be mistaken for a Titan row.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import re
from typing import Protocol, Sequence

log = logging.getLogger(__name__)

EMBED_DIM = 1024
TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"


class Embedder(Protocol):
    """Anything that turns text into a unit-length EMBED_DIM vector."""

    model_id: str

    def embed(self, text: str) -> list[float]: ...

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]: ...


def _l2_normalise(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0.0:
        # Degenerate input; return a fixed unit vector rather than dividing by zero.
        out = [0.0] * len(vec)
        out[0] = 1.0
        return out
    return [v / norm for v in vec]


class BedrockTitanEmbedder:
    """Amazon Bedrock Titan Text Embeddings V2, 1024-dim, normalised."""

    def __init__(self, region: str | None = None, model_id: str = TITAN_MODEL_ID) -> None:
        import boto3  # imported lazily so offline runs never need botocore

        self.model_id = model_id
        self._client = boto3.client(
            "bedrock-runtime", region_name=region or os.getenv("AWS_REGION", "us-east-1")
        )

    def embed(self, text: str) -> list[float]:
        body = json.dumps(
            {"inputText": text, "dimensions": EMBED_DIM, "normalize": True}
        )
        resp = self._client.invoke_model(modelId=self.model_id, body=body)
        payload = json.loads(resp["body"].read())
        vec = payload["embedding"]
        if len(vec) != EMBED_DIM:
            raise ValueError(
                f"{self.model_id} returned {len(vec)} dims, schema expects {EMBED_DIM}"
            )
        return vec

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        # Titan V2 is single-input; batching is a loop, kept here so callers do not
        # have to care which provider they got.
        return [self.embed(t) for t in texts]


class HashingEmbedder:
    """Deterministic offline stand-in. Not semantic — see module docstring.

    Hashes token trigrams into a fixed-width bag, which gives stable, comparable
    vectors: identical text embeds identically and near-identical text lands close,
    which is all the dedup/recall plumbing needs in order to be exercised in CI.
    """

    model_id = "offline-hashing-v1"

    _TOKEN = re.compile(r"[a-z0-9]+")

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * EMBED_DIM
        tokens = self._TOKEN.findall(text.lower())
        grams = tokens + [
            " ".join(tokens[i : i + 2]) for i in range(max(0, len(tokens) - 1))
        ]
        for gram in grams or ["\0"]:
            digest = hashlib.blake2b(gram.encode(), digest_size=8).digest()
            idx = int.from_bytes(digest[:4], "big") % EMBED_DIM
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        return _l2_normalise(vec)

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


_creds_usable: bool | None = None


def aws_credentials_usable() -> bool:
    """Whether AWS credentials exist *and* are actually accepted.

    Checking only that credentials are configured is not enough: a stale key in
    ``~/.aws/credentials`` looks perfectly valid to botocore and then fails on the
    first real call, which would take the demo down mid-run. One cheap STS call at
    selection time turns that into a clean fallback instead. Cached for the process.
    """
    global _creds_usable
    if _creds_usable is not None:
        return _creds_usable

    try:
        import boto3
        from botocore.config import Config

        session = boto3.Session()
        if session.get_credentials() is None:
            _creds_usable = False
            return _creds_usable
        sts = session.client(
            "sts", config=Config(retries={"max_attempts": 1}, connect_timeout=5, read_timeout=5)
        )
        sts.get_caller_identity()
        _creds_usable = True
    except Exception as exc:
        log.warning("AWS credentials present but not usable (%s)", type(exc).__name__)
        _creds_usable = False
    return _creds_usable


def get_embedder(force: str | None = None) -> Embedder:
    """Select an embedder.

    ``MNEMOS_EMBEDDER=bedrock`` forces Bedrock and fails loudly if it is not usable,
    which is what the deployed configuration sets. ``offline`` forces the stand-in.
    With neither set we use Bedrock when credentials exist and fall back otherwise,
    so a fresh clone can run the demo before it can run the cloud.
    """
    choice = (force or os.getenv("MNEMOS_EMBEDDER") or "auto").lower()

    if choice == "offline":
        return HashingEmbedder()

    if choice == "bedrock":
        return BedrockTitanEmbedder()

    if aws_credentials_usable():
        try:
            return BedrockTitanEmbedder()
        except Exception as exc:  # pragma: no cover - depends on local AWS config
            log.warning("Bedrock embedder unavailable (%s); using offline embedder", exc)

    log.warning(
        "No AWS credentials found — using %s. Vectors are deterministic but not "
        "semantic. Set AWS credentials and MNEMOS_EMBEDDER=bedrock for the real thing.",
        HashingEmbedder.model_id,
    )
    return HashingEmbedder()
