"""Data-driven scripted LLM: role → sequence of LLMResponse objects.

Fails closed when a role exhausts its script (no silent generic answers
unless explicitly configured with default_respond=True).

Responses use native tool_calls for delegate/use_tool actions (aligned
with the function-calling pipeline); respond() produces plain text.
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from lca.contracts.atoms.enums import LLMStreamEventType
from lca.contracts.atoms.ids import new_id
from lca.contracts.models.core.llm import LLMResponse, LLMStreamEvent, NativeToolCall
from lca.contracts.protocols import LLMAdapter

_ROLE_RE = re.compile(r"^ROLE:\s*(.+)$", re.MULTILINE)

_DELEGATE_TOOL_NAME = "delegate"


def respond(text: str = "ok", *, confidence: float = 0.9) -> LLMResponse:
    """Produce a plain-text RESPOND response."""
    return LLMResponse(text=text, model="scripted-llm")


def delegate(target_role: str, subtask: str = "please handle") -> LLMResponse:
    """Produce a single delegate tool-call response."""
    return LLMResponse(
        text="",
        model="scripted-llm",
        tool_calls=[
            NativeToolCall(
                call_id=new_id("call"),
                name=_DELEGATE_TOOL_NAME,
                arguments={"target_role": target_role, "subtask": subtask},
            )
        ],
    )


def multi_delegate(targets: Sequence[tuple[str, str]]) -> LLMResponse:
    """Produce a multi-delegate tool-call response (one tool call per target)."""
    return LLMResponse(
        text="",
        model="scripted-llm",
        tool_calls=[
            NativeToolCall(
                call_id=new_id("call"),
                name=_DELEGATE_TOOL_NAME,
                arguments={"target_role": role, "subtask": task},
            )
            for role, task in targets
        ],
    )


def use_tool(tool_name: str, arguments: dict[str, Any]) -> LLMResponse:
    """Produce a use_tool tool-call response."""
    return LLMResponse(
        text="",
        model="scripted-llm",
        tool_calls=[
            NativeToolCall(
                call_id=new_id("call"),
                name=tool_name,
                arguments=arguments,
            )
        ],
    )


class ScriptedLLMAdapter(LLMAdapter):
    """Table/sequence-driven LLM for CI-safe full-stack team tests."""

    name = "scripted-llm"

    def __init__(
        self,
        scripts: Mapping[str, Sequence[LLMResponse | str]] | None = None,
        *,
        default_respond: bool = True,
        default_text: str = "scripted default response",
    ) -> None:
        self._scripts: dict[str, list[LLMResponse | str]] = {
            k: list(v) for k, v in (scripts or {}).items()
        }
        self._cursors: dict[str, int] = dict.fromkeys(self._scripts, 0)
        self._default_respond = default_respond
        self._default_text = default_text
        self.calls: list[tuple[str, str]] = []

    def set_script(self, role: str, responses: Sequence[LLMResponse | str]) -> None:
        self._scripts[role] = list(responses)
        self._cursors[role] = 0

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        role = self._extract_role(prompt) or "*"
        self.calls.append((role, prompt[:200]))
        queue = self._next(role)
        if queue is not None:
            # Handle both LLMResponse objects and plain strings (for backward compatibility)
            if isinstance(queue, str):
                return LLMResponse(text=queue, model="scripted-llm")
            return queue
        if role != "*" and "*" in self._scripts:
            queue = self._next("*")
            if queue is not None:
                if isinstance(queue, str):
                    return LLMResponse(text=queue, model="scripted-llm")
                return queue
        if self._default_respond:
            return respond(f"{self._default_text} ({role})")
        raise LookupError(
            f"ScriptedLLM has no remaining response for role={role!r}. "
            f"Calls so far: {len(self.calls)}. Define a script or enable default_respond."
        )

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[LLMStreamEvent]:
        response = await self.complete(prompt, **kwargs)
        if response.tool_calls:
            for tc in response.tool_calls:
                import json

                args_json = json.dumps(tc.arguments, ensure_ascii=False)
                yield LLMStreamEvent(
                    type=LLMStreamEventType.FUNCTION_CALL_ARGUMENTS_DELTA,
                    tool_call_id=tc.call_id,
                    tool_name=tc.name,
                    arguments_delta=args_json,
                )
        else:
            yield LLMStreamEvent(type=LLMStreamEventType.OUTPUT_TEXT_DELTA, text=response.text)
        yield LLMStreamEvent(type=LLMStreamEventType.COMPLETED, response=response)

    def _next(self, role: str) -> LLMResponse | str | None:
        seq = self._scripts.get(role)
        if not seq:
            return None
        idx = self._cursors.get(role, 0)
        if idx >= len(seq):
            # Repeat last response for multi-step loops (swarm/debate)
            return seq[-1]
        self._cursors[role] = idx + 1
        return seq[idx]

    @staticmethod
    def _extract_role(prompt: str) -> str | None:
        m = _ROLE_RE.search(prompt)
        return m.group(1).strip() if m else None
