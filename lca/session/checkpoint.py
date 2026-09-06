"""Session checkpoint policy public API (ADR-0195 P4-S02)."""

from __future__ import annotations

from lca.contracts.protocols.session.checkpoint_policy import SessionCheckpointPolicyProtocol
from lca.contracts.protocols.session.persistence_service import CheckpointFailure
from lca.plugins.session.checkpoint_policy.checkpoint_policy import (
    FlushableSession,
    SessionCheckpointPolicy,
)

__all__ = [
    "CheckpointFailure",
    "FlushableSession",
    "SessionCheckpointPolicy",
    "SessionCheckpointPolicyProtocol",
]
