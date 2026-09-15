"""Protocol for the run-scoped session writer (spec §B, ADR-0226).

Every consumer of the conversation-history write path goes through this
Protocol. The concrete default implementation lives at
:mod:`lca.runtime.session.run_session_writer.RunSessionWriter`. Bind-site
construction is at :func:`lca.session.lifecycle.bind.bind_run_event_session_from_store`.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from lca.contracts.models.session.call_id import CallId
from lca.contracts.models.session.epoch_header import EpochHeader
from lca.contracts.models.session.event_ref import EventRef
from lca.contracts.models.session.message import Message
from lca.contracts.models.session.token_usage import TokenUsage
from lca.contracts.models.session.tool_call import ToolCall
from lca.contracts.models.session.tool_error import ToolError


@runtime_checkable
class RunSessionWriterProtocol(Protocol):
    """Owner of the run-scoped Session; single surface append path.

    All append methods route through :class:`SessionProtocol.append` with the
    DSH-aligned surface event taxonomy (``surface/user_message``,
    ``surface/assistant_message``, ``surface/tool_result``, ``log/tool_call``).
    Fail-loud on unbound Session — no silent ``None`` return, no ContextVar
    lookup.
    """

    def append_user_message(
        self,
        *,
        message_id: str,
        role: Literal["user", "human"],
        content: str,
    ) -> EventRef: ...

    def append_assistant_message(
        self,
        *,
        turn: int,
        step: int,
        role: Literal["assistant"],
        content: str | None,
        tool_calls: list[ToolCall] | None,
        usage: TokenUsage | None,
    ) -> EventRef: ...

    def append_tool_call(
        self,
        *,
        turn: int,
        step: int,
        call_id: CallId,
        name: str,
        arguments: str,
    ) -> EventRef: ...

    def append_tool_result(
        self,
        *,
        turn: int,
        step: int,
        call_id: CallId,
        content: str,
        error: ToolError | None,
        meta: Any | None,
    ) -> EventRef: ...

    def derive_messages(self) -> list[Message]: ...

    def request_header(self) -> EpochHeader | None: ...


__all__ = ["RunSessionWriterProtocol"]
