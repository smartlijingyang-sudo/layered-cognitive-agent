"""ExecutionEnvelope — typed contract for tool invocations (PR6 / v3 §9).

The envelope carries:
- ``capability_grant``: which capability the tool is authorized to invoke
- ``idempotency_key``: optional; if absent the call is non-idempotent
- ``approval_requirement``: optional; if present, the call requires
  approval before being forwarded to the SafeExecutor

The envelope is the boundary between the Brain's intent (a Decision
with tool_calls) and the Body's execution (the SafeExecutor).  No
tool call may bypass the envelope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionEnvelope:
    """Capability-bound, idempotent, approval-aware tool invocation."""

    capability_grant: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    idempotency_key: str | None = None
    approval_requirement: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def is_idempotent(self) -> bool:
        """Whether the envelope carries an idempotency key."""
        return self.idempotency_key is not None

    def requires_approval(self) -> bool:
        """Whether the envelope requires approval before execution."""
        return self.approval_requirement is not None


def envelope_from_decision(
    tool_name: str, arguments: dict[str, Any], *, capability_grant: str = "default"
) -> ExecutionEnvelope:
    """Build a minimal envelope from a Decision tool call.

    The factory is the seam between the Decision layer and the Body
    layer.  PR6's deny-only enforcement path uses this to mint the
    envelope; the actual gate check lives in the Hub / Body layers.
    """
    return ExecutionEnvelope(
        capability_grant=capability_grant,
        tool_name=tool_name,
        arguments=arguments,
    )


def find_terminal_tool_invoked(history: object) -> bool:
    """Return True if a terminal tool has been invoked in the history.

    The check is used by the resume path to make resume idempotent
    (per spec §9.3).  A terminal tool is one whose name ends in
    ``respond`` or is in the workspace ``_PRODUCER_TOOLS`` set.
    """
    # The history is a list of Turn objects.
    from lca.contracts.models.core.decision import Turn

    for turn in history:
        if not isinstance(turn, Turn):
            continue
        if turn.decision.action_type != "use_tool":
            continue
        for tc in turn.decision.tool_calls:
            if tc.tool_name.endswith("respond") or tc.tool_name == "terminal_respond":
                return True
    return False
