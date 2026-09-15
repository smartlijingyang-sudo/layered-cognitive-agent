"""``think.history.assemble`` graph node (spec §D).

Single responsibility: derive the :class:`ModelVisibleRequest` from
:class:`RunSessionWriter` by orphan-dropping dangling tool/result messages.

Mirrors OpenAI Agents SDK's ``drop_orphan_function_calls`` pattern at every
LLM-call preparation step. The orphan-drop lives on
:meth:`RunSessionWriter.derive_messages`; this node is the typed-boundary
adapter that wires the writer into the think subgraph's LLM dispatch port.

The :func:`@graph_node <graph_node>` decorator (ADR-0227) replaces the
manual ``NodeExecutor`` dataclass + ``@plugin(...)`` setup pair that lived
in :mod:`lca.plugins.think.history_assemble.execute` (PR2). Composite-key
registration under ``think::history.derive`` is preserved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from lca.contracts.protocols.session.model.context import ModelVisibleRequest
from lca.nodes._decorator import graph_node

if TYPE_CHECKING:
    from lca.contracts.models.core.state.state import AgentState
    from lca.contracts.protocols.session.run_session_writer import (
        RunSessionWriterProtocol,
    )


@graph_node(
    id="history.derive",
    region="think",
    inputs=("state", "writer"),
    outputs=("model_visible_request",),
)
async def history_assemble(
    *,
    state: AgentState,
    writer: RunSessionWriterProtocol,
) -> ModelVisibleRequest:
    """Build the model-visible request from the bound Session writer.

    Step 1 — derive the OpenAI messages list with orphan-drop already applied
    (see :meth:`RunSessionWriter.derive_messages`).
    Step 2 — source the system prompt from the writer's folded
    :class:`EpochHeader`; absent header → empty string.
    Step 3 — emit an empty ``tools`` tuple; Task 3 lands the tool registry
    wiring on the writer (PR2 will close that loop).
    """
    del state  # reserved for future state-aware history filtering (Task 3+)
    messages = writer.derive_messages()
    header = writer.request_header()
    system = _system_from_header(header)
    tools: tuple[dict[str, Any], ...] = ()
    return ModelVisibleRequest(messages=messages, system=system, tools=tools)


def _system_from_header(header: Any) -> str:
    """Extract the system prompt string from a folded ``EpochHeader``.

    Headers come back as :class:`lca_kernel.events.fold.fold.EpochHeader`
    or duck-typed stand-ins (e.g. the in-memory test fixture). Both expose
    ``.system``; ``None``/missing → empty string.
    """
    if header is None:
        return ""
    system = getattr(header, "system", None)
    if isinstance(system, str):
        return system
    return ""


__all__ = ["history_assemble"]
