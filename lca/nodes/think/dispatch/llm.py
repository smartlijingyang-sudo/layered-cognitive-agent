"""``think.llm.dispatch`` graph node (spec §E, ADR-0226 §4).

Single responsibility: invoke the LLM adapter once per think turn, persist
the assistant message + tool calls to the Session via
:class:`RunSessionWriter` BEFORE any tool execution (persist-before-execute
invariant, spec §C), and emit the ``LLMResponse`` + ``TokenUsage`` to the
downstream ``think.decision.parse`` node.

This is one of three single-responsibility nodes that replace the
retired ``think.reason.complete``:

- ``think.history.assemble`` (Task 2): writer → :class:`ModelVisibleRequest`
- ``think.llm.dispatch`` (Task 3): :class:`ModelVisibleRequest` → LLM call,
  journal ``surface/assistant_message`` + ``log/tool_call`` rows
- ``think.decision.parse`` (Task 3): :class:`LLMResponse` → :class:`Decision`

The orchestrator ``think.reason`` wires them via edges; the deleted
``complete`` node used to do all three jobs inline.

The :func:`@graph_node <graph_node>` decorator (ADR-0227) replaces the
manual ``NodeExecutor`` dataclass + ``@plugin(...)`` setup pair that lived
in :mod:`lca.plugins.think.llm_dispatch.execute` (PR2). Composite-key
registration under ``think::llm.call`` is preserved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.contracts.models.core.conversation.llm import LLMResponse, TokenUsage
from lca.nodes._decorator import graph_node

if TYPE_CHECKING:
    from lca.contracts.models.core.state.state import AgentState
    from lca.contracts.protocols.session.model.context import ModelVisibleRequest
    from lca.contracts.protocols.session.run_session_writer import (
        RunSessionWriterProtocol,
    )


@graph_node(
    id="llm.call",
    region="think",
    inputs=("state", "writer", "model_visible_request"),
    outputs=("llm_response", "usage"),
)
async def llm_dispatch(
    *,
    state: AgentState,
    writer: RunSessionWriterProtocol,
    model_visible_request: ModelVisibleRequest,
    adapter: Any,
) -> tuple[LLMResponse, TokenUsage]:
    """Call the LLM adapter with *model_visible_request* and persist the result.

    Step 1 — invoke ``adapter.complete(model_visible_request)``; the
    adapter is supplied by the executor from ``context.runtime`` so the
    pure fn stays I/O-portable (no globals, no env reads).
    Step 2 — persist the assistant message + tool calls to the Session
    via :class:`RunSessionWriter` BEFORE the next LLM call sees the
    history (persist-before-execute, spec §C).
    Step 3 — return ``(response, usage)`` for ``think.decision.parse``.

    The adapter contract: ``await adapter.complete(request)`` returns an
    :class:`LLMResponse`; usage is read off ``response.usage`` so the
    node does not depend on the adapter's internal accounting.
    """
    response: LLMResponse = await adapter.complete(model_visible_request)
    usage: TokenUsage | None = response.usage
    tool_calls = list(response.tool_calls or ())
    step = state.step
    writer.append_assistant_message(
        turn=step,
        step=step,
        role="assistant",
        content=response.text,
        tool_calls=[
            {
                "id": tc.call_id,
                "name": tc.name,
                "arguments": tc.arguments,
            }
            for tc in tool_calls
        ]
        or None,
        usage=usage,
    )
    for tc in tool_calls:
        writer.append_tool_call(
            turn=step,
            step=step,
            call_id=tc.call_id,
            name=tc.name,
            arguments=str(tc.arguments),
        )
    return response, usage or TokenUsage()


__all__ = ["llm_dispatch"]
