"""``RunHealthCondition`` — one observable fact about a run (PR-1 / Task 1.1).

Upholds AGENTS.md §3 C13 (information bloodline closure) and §3 C11 (event
closed-set): the contract is frozen and rejects extra fields, and the
status alphabet is closed while the ``type`` vocabulary is intentionally
OPEN (k8s Conditions RFC 8294 / OTel Attributes pattern). See design spec
``docs/superpowers/specs/2026-09-16-run-health-and-execution-closure-design.md``
§10.3 for the full docstring obligations enforced here.

The ``type`` field is intentionally an OPEN string (not a ``Literal``) to
follow the k8s Condition RFC 8294 and OTel Attributes pattern: the contract
is the fold function, not the type vocabulary. New types are added by
registering a new ``HealthDeriver`` entry point — no contract change, no
consumer change, no fold change.

The ``reason`` field is a stable identifier (k8s pattern), NOT a
human-readable message. Agents and consumers MUST NOT parse the reason
text. Use ``evidence_refs`` to jump to the spine. Example stable
identifiers: ``"tool_orphan_dropped"``, ``"sandbox_enter_unmatched"``,
``"messages_incomplete"``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from lca.contracts.observability.health.evidence_ref import EvidenceRef

# Closed status alphabet — the only allowed values of ``RunHealthCondition.status``.
# Any other value MUST be rejected at the contract boundary so consumers can
# pattern-match exhaustively (AGENTS.md §3 C11).
RunHealthStatus = Literal["ok", "degraded", "failed", "unknown"]


class RunHealthCondition(BaseModel):
    """One observable fact about a run.

    Frozen (``model_config = ConfigDict(frozen=True, extra="forbid")``)
    per AGENTS.md §3 C13. ``conditions`` is a tuple on ``RunHealthReport``
    to keep the report hashable and deterministic (AGENTS.md §3 C8).

    The ``type`` field is intentionally an OPEN string (not a ``Literal``)
    to follow the k8s Condition RFC 8294 and OTel Attributes pattern:
    the contract is the fold function, not the type vocabulary. New
    types are added by registering a new HealthDeriver entry point —
    no contract change, no consumer change, no fold change.

    The ``reason`` field is a stable identifier (k8s pattern), NOT
    a human-readable message. Agents and consumers MUST NOT parse
    the reason text. Use ``evidence_refs`` to jump to the spine.
    Example stable identifiers: ``"tool_orphan_dropped"``,
    ``"sandbox_enter_unmatched"``, ``"messages_incomplete"``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: str  # OPEN; convention documented in module docstring.
    status: RunHealthStatus
    reason: str  # stable identifier, NOT for parsing.
    evidence_refs: tuple[EvidenceRef, ...]  # minimum 1
    observed_at: float  # epoch_seconds, monotonic per type.


__all__ = ["RunHealthCondition", "RunHealthStatus"]
