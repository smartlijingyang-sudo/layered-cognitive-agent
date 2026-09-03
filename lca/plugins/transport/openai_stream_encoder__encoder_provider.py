"""Agent journal -> OpenAI ChatCompletion streaming encoder (ADR-0099).

Single-direction, single-IO translator: takes the dataclass journal
events emitted by ``record()`` and yields SSE-formatted bytes that
match the OpenAI ChatCompletion streaming contract. LobeHub's
``model-runtime/openaiCompatibleFactory`` consumes this wire natively
—no LobeHub patches required.

The encoder is purposefully stateless and pure-functional. Already-executed
tools are rendered as ``delta.content`` markdown: OpenAI ``delta.tool_calls``
is a request for the *client* to run tools, and LobeHub's native
``GeneralChatAgent`` will ``call_tool`` whenever ``toolsCalling.length > 0``.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

from lca.plugins.transport.openai_stream_encoder__chunk_provider import OpenAIChatChunkBuilder


class _SupportsEventType(Protocol):
    """Anything with a string ``event_type`` plus dataclass-y fields."""

    event_type: str


class OpenAIStreamEncoder:
    """Translate a journal event stream into OpenAI ChatCompletion SSE bytes.

    Gateway owns one encoder per SSE response. The encoder does not
    introspect event contents beyond the small set of supported
    event types; everything else is silently ignored (those events
    remain on the journal/OTel plane only).
    """

    # Event type labels we care about — defined as constants so a future
    # SSR-0096-style envelope migration only touches one place.
    REASONING_DELTA = "ReasoningDelta"
    REASONING_COMPLETED = "ReasoningCompleted"
    STEP_TEXT_DELTA = "StepTextDelta"
    TOOL_STARTED = "ToolStarted"
    TOOL_INVOKED = "ToolInvoked"
    TOOL_DENIED = "ToolDenied"
    AGENT_RUN_FINISHED = "AgentRunFinished"
    TEAM_RUN_FINISHED = "TeamRunFinished"

    async def encode(
        self,
        stream: AsyncIterator[_SupportsEventType],
        *,
        chunk_builder: OpenAIChatChunkBuilder,
    ) -> AsyncIterator[bytes]:
        """Yield SSE ``data: ...`` lines for the journal event stream.

        ``done()`` is emitted only when an ``AgentRunFinished`` /
        ``TeamRunFinished`` event is seen, OR when the source stream
        ends naturally. The caller is expected to consume this
        generator exactly once per SSE response — feeding an async
        generator of any length is fine.
        """
        terminated = False
        async for event in stream:
            et = getattr(event, "event_type", "") or type(event).__name__
            if et == self.REASONING_DELTA:
                token = str(getattr(event, "text_delta", "") or "")
                if token:
                    yield chunk_builder.append_reasoning(token)
            elif et == self.REASONING_COMPLETED:
                # Thinking-duration is tracked client-side via the openai.ts
                # parser; we do not need to send any extra wire frame for it.
                continue
            elif et == self.STEP_TEXT_DELTA:
                if getattr(event, "channel", "decision") != "answer":
                    continue
                token = str(getattr(event, "text_delta", "") or "")
                if token:
                    yield chunk_builder.append_content(token)
            elif et == self.TOOL_STARTED:
                text = self._render_tool_started(event)
                if text:
                    yield chunk_builder.append_content(text)
            elif et == self.TOOL_INVOKED:
                text = self._render_tool_invoked(event)
                if text:
                    yield chunk_builder.append_content(text)
            elif et == self.TOOL_DENIED:
                reason = str(getattr(event, "reason", "") or "denied")
                yield chunk_builder.append_content(f"\n\n_tool denied: {reason}_\n\n")
            elif et in {self.AGENT_RUN_FINISHED, self.TEAM_RUN_FINISHED}:
                yield chunk_builder.finish_reason("stop")
                terminated = True
                break
            # Anything else (Casting/Decision/Step/Sandbox*): journal/OTel only
        if not terminated:
            # Source stream drained without a Finished event — close cleanly.
            pass
        yield chunk_builder.done()

    # ── private helpers ────────────────────────────────────────────

    def _render_tool_started(self, event: Any) -> str:
        name = str(getattr(event, "tool_name", "") or "tool")
        arguments = self._extract_arguments(event)
        if arguments and arguments != "{}":
            return f"\n\n**{name}** `{arguments}`\n"
        return f"\n\n**{name}**\n"

    def _render_tool_invoked(self, event: Any) -> str:
        if bool(getattr(event, "ok", True)) is False:
            err = getattr(event, "error", "") or "tool failed"
            return f"\n\n_tool failed: {err}_\n\n"
        files = getattr(event, "files", ()) or ()
        if files:
            return "\n\n" + self._render_files(files) + "\n\n"
        # ADR-0101 PR-2:ToolInvoked 不再有 output_text;输出走 evidence 平面
        # (output_ref)。encoder 此时只能展示 "completed" 标记;真实内容由
        # lobehub 渲染层经 ref 异步拉取。
        return "\n\n_tool completed_\n\n"

    @staticmethod
    def _extract_arguments(event: Any) -> str:
        """Serialize tool arguments as a JSON string.

        ADR-0101 PR-2:tool 事件 dataclass 不再有 typed 6-key / plugin_state /
        arguments_preview。参数走 inline ``arguments``(evidence 不可用退路)
        或 ``arguments_ref``(evidence 平面)。encoder 读 inline ``arguments``;
        evidence 路径下返回空 dict(前端走 ref 拉取)。
        """
        collected: dict[str, Any] = {}
        arguments = getattr(event, "arguments", None) or {}
        if isinstance(arguments, dict):
            for key, value in arguments.items():
                if value not in (None, ""):
                    collected[key] = value
        return json.dumps(collected, ensure_ascii=False, default=str)

    @staticmethod
    def _render_files(files: Any) -> str:
        lines = ["**Artifacts**", ""]
        for f in files:
            name = getattr(f, "name", None) or (f.get("name") if isinstance(f, dict) else "")
            url = getattr(f, "url", None) or (f.get("url") if isinstance(f, dict) else "")
            if not url:
                continue
            lines.append(f"- [{name}]({url})")
        return "\n".join(lines) if len(lines) > 2 else "(no artifacts)"


__all__ = ["OpenAIStreamEncoder"]
