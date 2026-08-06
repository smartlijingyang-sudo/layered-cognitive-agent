"""Data-driven scripted LLM: role → sequence of JSON Decision strings.

Fails closed when a role exhausts its script (no silent generic answers
unless explicitly configured with default_respond=True).
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from lca.contracts.models.core.llm import LLMResponse
from lca.contracts.protocols import LLMAdapter

_ROLE_RE = re.compile(r"^ROLE:\s*(.+)$", re.MULTILINE)


def respond(text: str = "ok", *, confidence: float = 0.9) -> str:
    return json.dumps(
        {
            "action_type": "respond",
            "response_text": text,
            "rationale": "scripted respond",
            "confidence": confidence,
        },
        ensure_ascii=False,
    )


def delegate(target_role: str, subtask: str = "please handle") -> str:
    return json.dumps(
        {
            "action_type": "delegate",
            "target_role": target_role,
            "subtask": subtask,
            "rationale": "scripted delegate",
            "confidence": 0.95,
        },
        ensure_ascii=False,
    )


def multi_delegate(targets: Sequence[tuple[str, str]]) -> str:
    return json.dumps(
        {
            "action_type": "delegate",
            "delegations": [{"target_role": role, "subtask": task} for role, task in targets],
            "rationale": "scripted multi-delegate",
            "confidence": 0.95,
        },
        ensure_ascii=False,
    )


def use_tool(tool_name: str, arguments: dict[str, Any]) -> str:
    return json.dumps(
        {
            "action_type": "use_tool",
            "tool_name": tool_name,
            "arguments": arguments,
            "rationale": "scripted tool",
            "confidence": 0.95,
        },
        ensure_ascii=False,
    )


class ScriptedLLMAdapter(LLMAdapter):
    """Table/sequence-driven LLM for CI-safe full-stack team tests."""

    name = "scripted-llm"

    def __init__(
        self,
        scripts: Mapping[str, Sequence[str]] | None = None,
        *,
        default_respond: bool = True,
        default_text: str = "scripted default response",
    ) -> None:
        self._scripts: dict[str, list[str]] = {k: list(v) for k, v in (scripts or {}).items()}
        self._cursors: dict[str, int] = dict.fromkeys(self._scripts, 0)
        self._default_respond = default_respond
        self._default_text = default_text
        self.calls: list[tuple[str, str]] = []

    def set_script(self, role: str, responses: Sequence[str]) -> None:
        self._scripts[role] = list(responses)
        self._cursors[role] = 0

    async def complete(self, prompt: str, **kwargs: Any) -> LLMResponse:
        role = self._extract_role(prompt) or "*"
        self.calls.append((role, prompt[:200]))
        queue = self._next(role)
        if queue is not None:
            return self._respond(queue)
        if role != "*" and "*" in self._scripts:
            queue = self._next("*")
            if queue is not None:
                return self._respond(queue)
        if self._default_respond:
            return self._respond(respond(f"{self._default_text} ({role})"))
        raise LookupError(
            f"ScriptedLLM has no remaining response for role={role!r}. "
            f"Calls so far: {len(self.calls)}. Define a script or enable default_respond."
        )

    @staticmethod
    def _respond(text: str) -> LLMResponse:
        return LLMResponse(text=text, model="scripted-llm")

    async def stream(self, prompt: str, **kwargs: Any) -> AsyncIterator[str]:
        response = await self.complete(prompt, **kwargs)
        yield response.text

    def _next(self, role: str) -> str | None:
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
