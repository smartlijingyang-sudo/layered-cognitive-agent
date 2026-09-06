"""Session checkpoint policy public API (ADR-0195 P4-S02)."""

from __future__ import annotations

from lca.contracts.protocols.session.checkpoint.policy import SessionCheckpointPolicyProtocol
from lca.contracts.protocols.session.persistence.service import CheckpointFailure
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
