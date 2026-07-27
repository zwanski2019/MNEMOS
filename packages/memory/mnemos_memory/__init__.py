"""MNEMOS memory core — CockroachDB-backed agent memory."""

from .auth import (
    Account,
    Accounts,
    AuthError,
    Entitlement,
    NotEntitled,
    TRIAL_DAYS,
)
from .artifacts import ArtifactStore, get_artifact_store
from .db import connect, migrate, run_in_transaction, transaction
from .epistemic import (
    Belief,
    EpistemicStatus,
    PriorLink,
    derive_status,
    initial_confidence,
    update as bayes_update,
)
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
    "Account", "Accounts", "ArtifactStore", "AuthError", "Entitlement", "NotEntitled",
    "TRIAL_DAYS", "get_artifact_store", "CONFIDENCE_HALF_LIFE_DAYS",
    "Correlation", "MemoryIntelligence", "Reconciliation", "confidence_for",
    "Belief", "Candidate", "EpistemicStatus", "PriorLink", "bayes_update",
    "derive_status", "initial_confidence", "CostCeilingExceeded", "DedupVerdict", "EMBED_DIM", "Embedder",
    "Memory", "Recalled", "ScopeViolation", "connect", "get_embedder", "migrate", "run_in_transaction",
    "transaction",
]
