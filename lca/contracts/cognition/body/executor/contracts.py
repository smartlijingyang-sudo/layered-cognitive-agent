"""L2 body surface-event contract (PR-2, G-16).

Defines the journal shape ``Body.dispatch_tool_calls`` MUST produce per
``Decision`` cycle. The contract is the seam between the act phase
(SimpleBody) and the observation/derivation layer
(``RunSessionWriter.derive_messages`` + ``RunHealthReport`` fold).

Invariant (one line): for every ``Decision`` with N>=1 ``tool_calls``,
the Session MUST contain exactly 1 ``surface/assistant_message`` carrying
all N ``tool_calls``, followed by N ``surface/tool_result`` messages,
each linked by ``tool_call_id`` to its declared call.

Closing this invariant is the root-cause fix for B-1: prior to PR-2,
``dispatch_tool_call`` committed one assistant row + one tool_result per
``Decision`` regardless of ``len(decision.tool_calls)``, so multi-call
decisions (e.g. five ``runCommand`` calls in one turn) had their
assistant row declare N tool_calls but only one tool_result ever landed.
The remaining N-1 results were orphan-dropped at
``RunSessionWriter._drop_orphan_tool_results``, and the model never saw
them — so the LLM feedback chain was incomplete and
``RunHealthReport.llm`` flipped to ``failed``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from lca.contracts.harness.act.effect_receipt import EffectReceipt
from lca.contracts.models.core.execution.decision import Decision


@runtime_checkable
class BodySurfaceEventContract(Protocol):
    """Surface-event contract every Body MUST satisfy (PR-2, G-16).

    The implementation MUST persist-before-execute the assistant row
    (with all N ``tool_calls``) BEFORE any tool runs, then commit N
    ``surface/tool_result`` rows linked by ``call_id``. Returning
    ``list[EffectReceipt]`` of length N preserves the per-call effect
    semantics callers depend on.
    """

    async def dispatch_tool_calls(self, decision: Decision) -> list[EffectReceipt]:
        """Persist 1 assistant + N tool_results; return N EffectReceipts."""
        ...


__all__ = ["BodySurfaceEventContract"]
