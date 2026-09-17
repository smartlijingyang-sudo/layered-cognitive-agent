"""Project one :class:`LLMResponse` into the parts a :class:`Decision` needs.

Single home for the native-tool-call → ``ToolCall`` mapping so the ADR-0047
wire verdict (``wire_status`` / ``wire_reason`` / ``wire_raw_preview``)
travels with every call. ``tool_wire_gate`` refuses to execute on that
verdict and ``think.decision.repair`` reads it to attempt a repair; a
projection that drops the fields downgrades a truncated payload to a generic
``missing_required_arguments`` error that does not name the real cause.

Leak recovery runs before intent extraction: :func:`parse_text_channel` returns
prose plus recovered calls without mutating ``response.text``, so the intent is
computed from the stripped leftover and leaked JSON is not double-counted as
answer text.

The text channel has a third outcome besides prose and a decoded call: protocol
markup that decoded to nothing. This mapping is the single home for that rule,
so all four consumers (``think.decision.parse``, ``decision.parse.response``,
``DefaultDecisionClassifier``, ``compose_action``) get it without each having to
remember it. Undecodable markup becomes an ADR-0047 incomplete-wire ``ToolCall``
with an empty name and the fragment in ``wire_raw_preview``: ``tool_wire_gate``
refuses to execute it and ``think.decision.repair`` rejects it on schema grounds,
which re-routes to a re-reason. The alternative — leaving it in ``intent`` — is
what lets a wire failure reach the user as a final answer and stop the loop on
``StopReason.CONTINUE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from lca.cognition.brain.prompt.leaked_tool_call import parse_text_channel
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import DelegationSpec, ToolCall

if TYPE_CHECKING:
    from lca.contracts.models.core.conversation.llm import LLMResponse

_DELEGATE_TOOL_NAME = "delegate"
_PREVIEW_CHARS = 400


@dataclass(frozen=True, slots=True)
class ResponseProjection:
    """Typed split of one completion: tool calls, delegations, answer prose."""

    tool_calls: tuple[ToolCall, ...]
    delegations: tuple[DelegationSpec, ...]
    intent: str


def _undecodable_wire_call(markup: str) -> ToolCall:
    """Express unreadable tool-call markup as an incomplete wire call.

    ``tool_name`` stays empty: the name is exactly what could not be read, and
    an empty name is what ``think.decision.repair`` rejects on schema grounds.
    """
    return ToolCall(
        call_id=new_id("call"),
        tool_name="",
        arguments={},
        wire_status="incomplete",
        wire_reason="unterminated_or_truncated_json",
        wire_raw_preview=markup[:_PREVIEW_CHARS],
    )


def project_llm_response(response: LLMResponse) -> ResponseProjection:
    """Map ``response.tool_calls`` + ``response.text`` onto Decision parts."""
    intent = (response.text or "").strip()
    native_calls = list(response.tool_calls or ())
    undecodable = ""
    if not native_calls and intent:
        channel = parse_text_channel(intent)
        intent = channel.prose
        native_calls = list(channel.calls)
        undecodable = channel.undecodable

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
    if undecodable and not tool_calls and not delegations:
        return ResponseProjection(
            tool_calls=(_undecodable_wire_call(undecodable),),
            delegations=(),
            intent="",
        )
    return ResponseProjection(
        tool_calls=tuple(tool_calls),
        delegations=tuple(delegations),
        intent=intent,
    )


__all__ = ["ResponseProjection", "project_llm_response"]
