"""Project one :class:`LLMResponse` into the parts a :class:`Decision` needs.

Single home for the native-tool-call → ``ToolCall`` mapping so the ADR-0047
wire verdict (``wire_status`` / ``wire_reason`` / ``wire_raw_preview``)
travels with every call. ``tool_wire_gate`` refuses to execute on that
verdict and ``think.decision.repair`` reads it to attempt a repair; a
projection that drops the fields downgrades a truncated payload to a generic
``missing_required_arguments`` error that does not name the real cause.

Leak recovery runs before intent extraction: ``recover_leaked_tool_calls``
returns new prose plus recovered calls without mutating ``response.text``, so
the intent is computed from the stripped leftover and leaked JSON is not
double-counted as answer text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.cognition.brain.prompt.leaked_tool_call import recover_leaked_tool_calls
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import DelegationSpec, ToolCall

if TYPE_CHECKING:
    from lca.contracts.models.core.conversation.llm import LLMResponse

_DELEGATE_TOOL_NAME = "delegate"


@dataclass(frozen=True, slots=True)
class ResponseProjection:
    """Typed split of one completion: tool calls, delegations, answer prose."""

    tool_calls: tuple[ToolCall, ...]
    delegations: tuple[DelegationSpec, ...]
    intent: str


def project_llm_response(response: LLMResponse) -> ResponseProjection:
    """Map ``response.tool_calls`` + ``response.text`` onto Decision parts."""
    intent = (response.text or "").strip()
    native_calls = list(response.tool_calls or ())
    if not native_calls and intent:
        intent, recovered = recover_leaked_tool_calls(intent)
        native_calls = recovered

    delegations: list[DelegationSpec] = []
    tool_calls: list[ToolCall] = []
    for call in native_calls:
        if call.name == _DELEGATE_TOOL_NAME:
            delegations.append(
                DelegationSpec(
                    subtask=str(call.arguments.get("subtask", "")),
                    target_role=call.arguments.get("target_role") or None,
                    target_agent_id=call.arguments.get("target_agent_id") or None,
                )
            )
            continue
        tool_calls.append(
            ToolCall(
                call_id=call.call_id or new_id("call"),
                tool_name=call.name,
                arguments=dict(call.arguments),
                wire_status=str(getattr(call, "wire_status", None) or "ok"),
                wire_reason=str(getattr(call, "wire_reason", None) or ""),
                wire_raw_preview=str(getattr(call, "wire_raw_preview", None) or ""),
            )
        )
    return ResponseProjection(
        tool_calls=tuple(tool_calls),
        delegations=tuple(delegations),
        intent=intent,
    )


__all__ = ["ResponseProjection", "project_llm_response"]
