"""MNEMOS memory core — CockroachDB-backed agent memory."""

from .artifacts import ArtifactStore, get_artifact_store
from .db import connect, migrate, run_in_transaction, transaction
from .intelligence import (
    CONFIDENCE_HALF_LIFE_DAYS,
    Correlation,
    MemoryIntelligence,
    Reconciliation,
    confidence_for,
)
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
    "ArtifactStore", "get_artifact_store", "CONFIDENCE_HALF_LIFE_DAYS",
    "Correlation", "MemoryIntelligence", "Reconciliation", "confidence_for",
    "Candidate", "CostCeilingExceeded", "DedupVerdict", "EMBED_DIM", "Embedder",
    "Memory", "Recalled", "ScopeViolation", "connect", "get_embedder", "migrate", "run_in_transaction",
    "transaction",
]
