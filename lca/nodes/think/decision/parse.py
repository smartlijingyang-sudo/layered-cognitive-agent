"""``think.decision.parse`` graph node (spec §E).

Single responsibility: project an :class:`LLMResponse` into a typed
:class:`Decision` for downstream ``think.gate`` (and the outer
interpreter).

This is the third of three single-responsibility nodes that replace
``think.reason.complete``:

- ``think.history.assemble`` (Task 2): writer → :class:`ModelVisibleRequest`
- ``think.llm.dispatch`` (Task 3): LLM call → :class:`LLMResponse`
- ``think.decision.parse`` (Task 3): :class:`LLMResponse` → :class:`Decision`

The orchestrator ``think.reason`` wires them via edges; the deleted
``complete`` node used to do all three jobs inline.

The parse mirrors ``decision_classify.decision.parse.response`` but emits
a single :class:`Decision` (the spec §E node emits ``decision`` as one
typed port, not the typed-port split used by ``concept.decision.classify``).

The :func:`@graph_node <graph_node>` decorator (ADR-0227) replaces the
manual ``NodeExecutor`` dataclass + ``@plugin(...)`` setup pair that lived
in :mod:`lca.plugins.think.decision_parse.execute` (PR2). Composite-key
registration under ``think::decision.parse`` is preserved.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import (
    Decision,
    DelegationSpec,
    ToolCall,
)
from lca.framework.graph.nodes.decorator import graph_node

if TYPE_CHECKING:
    from lca.contracts.models.core.conversation.llm import LLMResponse


_log = logging.getLogger(__name__)

_DELEGATE_TOOL_NAME = "delegate"


@graph_node(
    id="decision.parse",
    region="think",
    inputs=("state", "llm_response"),
    outputs=("decision",),
)
async def decision_parse(*, state: Any, llm_response: LLMResponse) -> Decision:
    """Project an :class:`LLMResponse` into a :class:`Decision`.

    Step 1 — extract native tool calls + delegate tool specs.
    Step 2 — derive intent from response text (after leak-recovery so
    JSON that was smuggled inside ``text`` does not double-count).
    Step 3 — assemble a :class:`Decision` with ``action_type`` inferred
    from tool presence (``use_tool`` when there are tool calls or
    delegations; ``respond`` otherwise).
    """
    del state  # reserved for future state-aware routing
    tool_calls, delegations, intent = _project_response(llm_response)
    action_type = _infer_action_type(tool_calls=tool_calls, delegations=delegations)
    decision_id = new_id("decision")
    return Decision(
        decision_id=decision_id,
        action_type=action_type,
        rationale=intent,
        confidence=1.0,
        tool_calls=list(tool_calls),
        delegations=list(delegations),
        response_text=intent if action_type == "respond" else None,
    )


def _project_response(
    response: LLMResponse,
) -> tuple[list[ToolCall], list[DelegationSpec], str]:
    """Split native tool calls + delegations and recover leaked JSON from text."""
    from lca.cognition.brain.prompt.leaked_tool_call import (
        recover_leaked_tool_calls,
    )

    leftover = (response.text or "").strip()
    native_calls = list(response.tool_calls or ())
    if not native_calls and leftover:
        leftover, recovered = recover_leaked_tool_calls(leftover)
        native_calls = recovered

    delegations: list[DelegationSpec] = []
    tool_calls: list[ToolCall] = []
    for tc in native_calls:
        if tc.name == _DELEGATE_TOOL_NAME:
            delegations.append(
                DelegationSpec(
                    subtask=str(tc.arguments.get("subtask", "")),
                    target_role=tc.arguments.get("target_role") or None,
                    target_agent_id=tc.arguments.get("target_agent_id") or None,
                )
            )
            continue
        tool_calls.append(
            ToolCall(
                call_id=tc.call_id or new_id("call"),
                tool_name=tc.name,
                arguments=dict(tc.arguments),
            )
        )
    return tool_calls, delegations, leftover


def _infer_action_type(
    *,
    tool_calls: list[ToolCall],
    delegations: list[DelegationSpec],
) -> str:
    """Pick the :class:`Decision.action_type` from the parsed payload.

    ``delegate`` is reported as ``delegate``; any native or leaked tool
    call becomes ``use_tool``; an empty payload is a ``respond``.
    """
    if delegations:
        return "delegate"
    if tool_calls:
        return "use_tool"
    return "respond"


__all__ = ["decision_parse"]
