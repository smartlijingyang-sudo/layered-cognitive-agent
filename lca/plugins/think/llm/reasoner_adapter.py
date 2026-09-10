"""LLM-backed Reasoner / Classifier / Gate adapter.

ADR-0219 §10.11: the think subgraph's reasoner / decision_classifier /
decision_gate / skill_router / supports_shortcut capabilities all read
the LLM wire through this adapter. The adapter wraps the active
:class:`LLMAdapter` (provided by ``lca-llm-resolver``) and exposes the
typed Reasoner Protocol methods:

- ``generate_thoughts(state)`` → ``LLMResponse`` (think.shortcut)
- ``build_turn_plan(state)`` → ``TurnPlan`` (think.reason.plan)
- ``render_turn(state, plan)`` → ``TurnRender`` (think.reason.render)
- ``complete_turn(state, render)`` → ``LLMResponse`` (think.reason.complete)

The adapter is the only place that knows the prompt shape; the inner
subgraph stays an LLM-agnostic graph of typed ports. If the LLM wire is
unavailable (``LLMAdapter`` raises), the adapter raises a typed
:exc:`LLMUnavailableError` so the runtime emits a fail-loud EP rather
than silently falling back to a stub response.

delete-when: once the inner subgraph executors themselves call the
LLM adapter directly (rather than reading a Reasoner instance via
``context.runtime``), this module folds into one of the inner-node
plugins.
"""

from __future__ import annotations

from typing import Any

from lca.contracts.models.core.conversation.llm import LLMResponse
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols import LLMAdapter
from lca.infrastructure.llm.openai_client import LLMUnavailableError

_DEFAULT_PROMPT = (
    "You are the think subgraph of an LCA cognitive agent. "
    "Given the user's task and current state, produce a single JSON "
    "object with keys ``thought`` (string), ``plan`` (object), "
    "``render`` (object), and ``response_text`` (string). The keys "
    "are read by typed downstream ports in the think subgraph."
)


class LLMReasoner:
    """LLM-backed Reasoner that fronts an :class:`LLMAdapter`.

    The LLM wire is the single source of truth for thought generation.
    Each method shapes a prompt around the call site (think / plan /
    render / complete) and routes through ``adapter.complete``. The
    inner subgraph consumes the typed return values; the prompt
    format is private to this module.
    """

    def __init__(self, *, adapter: LLMAdapter) -> None:
        self._adapter = adapter

    async def generate_thoughts(self, state: AgentState) -> LLMResponse:
        prompt = self._render_prompt(state, slot="thought")
        return await self._call(prompt)

    async def build_turn_plan(self, state: AgentState) -> dict[str, Any]:
        prompt = self._render_prompt(state, slot="plan")
        response = await self._call(prompt)
        return _json_or_text(response, default_key="plan")

    async def render_turn(
        self,
        state: AgentState,
        plan: dict[str, Any] | None,
    ) -> dict[str, Any]:
        prompt = self._render_prompt(state, slot="render", plan=plan)
        response = await self._call(prompt)
        return _json_or_text(response, default_key="render")

    async def complete_turn(
        self,
        state: AgentState,
        render: dict[str, Any] | None,
    ) -> LLMResponse:
        prompt = self._render_prompt(state, slot="complete", render=render)
        return await self._call(prompt)

    def _render_prompt(
        self,
        state: AgentState,
        *,
        slot: str,
        plan: dict[str, Any] | None = None,
        render: dict[str, Any] | None = None,
    ) -> str:
        body = {
            "slot": slot,
            "task": getattr(state, "task", ""),
            "working_memory": getattr(state, "working_memory", {}),
            "active_template": getattr(state, "active_template", None),
            "plan": plan,
            "render": render,
        }
        return f"{_DEFAULT_PROMPT}\n\nstate={body!r}"

    async def _call(self, prompt: str) -> LLMResponse:
        try:
            return await self._adapter.complete(prompt)
        except Exception as exc:  # noqa: BLE001 - adapter surface is broad
            raise LLMUnavailableError(
                f"think subgraph LLM call failed: {type(exc).__name__}: {exc}"
            ) from exc


def _json_or_text(response: LLMResponse, *, default_key: str) -> dict[str, Any]:
    """Decode the adapter response into a plain dict for the typed port.

    The LLM is asked to return JSON; we tolerate raw text by wrapping it
    under ``default_key``. The inner subgraph only reads
    :class:`dict[str, Any]` payloads, so a string-wrapped shape keeps the
    typed fold alive even when the model returns prose instead of JSON.
    """
    text = response.text or ""
    import json

    try:
        decoded = json.loads(text)
    except (TypeError, ValueError):
        return {default_key: text}
    if isinstance(decoded, dict):
        return decoded
    return {default_key: decoded}


__all__ = ["LLMReasoner"]