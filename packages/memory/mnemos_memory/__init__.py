"""MNEMOS memory core — CockroachDB-backed agent memory."""

from .db import connect, migrate, run_in_transaction, transaction
from .embeddings import EMBED_DIM, Embedder, get_embedder
from .memory import (
    Candidate,
    CostCeilingExceeded,
    DedupVerdict,
    Memory,
    Recalled,
    ScopeViolation,
)

__all__ = [
    "Candidate", "CostCeilingExceeded", "DedupVerdict", "EMBED_DIM", "Embedder",
    "Memory", "Recalled", "ScopeViolation", "connect", "get_embedder", "migrate", "run_in_transaction",
    "transaction",
]
