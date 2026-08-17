"""1:1 port of ``@deepseek-ai/dsh-agent/model-selection.ts``."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lca.layer0_infra.dsh_core.session._llm_types import LlmCallConfig

# ---------------------------------------------------------------------------
# ReasoningEffortId — adapter-owned reasoning effort identifier
# ---------------------------------------------------------------------------

ReasoningEffortId = str


# ---------------------------------------------------------------------------
# ModelSelection
# ---------------------------------------------------------------------------


@dataclass
class ModelSelection:
    """Complete provider, model, and optional reasoning effort selected for one live Agent."""

    provider: str
    """Registered provider route."""
    model: str
    """Provider-owned model id."""
    reasoning_effort: ReasoningEffortId | None = None
    """Adapter-owned reasoning effort, or provider/default behavior when absent."""


# ---------------------------------------------------------------------------
# ModelSelectionRef
# ---------------------------------------------------------------------------


@dataclass
class ModelSelectionRef:
    """Mutable model selection plus the value captured for the current step."""

    current: ModelSelection | None = None
    """Model selected for the next step that enters prompt assembly."""
    assembled: ModelSelection | None = None
    """Selection captured when the current step entered prompt assembly."""


# ---------------------------------------------------------------------------
# install_model_selection
# ---------------------------------------------------------------------------


def install_model_selection(
    agent_ctx: Any,
    selection: ModelSelectionRef,
) -> Callable[[], None]:
    """Couple one mutable selection to Agent-scoped prompt assembly and request routing.

    Prompt assembly snapshots the selected model before delegating, then applies
    its provider/model pair and effort to request config so a concurrent switch
    takes effect on a later step instead of splitting the two surfaces.  An
    absent selected effort clears any inherited effort, restoring the selected
    model's provider/default behavior.

    Args:
        agent_ctx: The selected Agent's scoped context.
        selection: Mutable selection owned by the calling entry point.

    Returns:
        Disposer for both scoped waterfall listeners.
    """

    async def _on_assemble(assembly: Any, context: Any, next_fn: Callable) -> Any:
        selected = selection.current
        assembled = await next_fn()
        selection.assembled = selected
        if selected is None:
            return assembled
        return {
            **assembled,
            "variables": {
                **assembled.get("variables", {}),
                "provider": selected.provider,
                "model": selected.model,
            },
        }

    async def _on_request(payload: Any, next_fn: Callable) -> LlmCallConfig:
        resolved: LlmCallConfig = await next_fn()
        selected = selection.assembled
        if selected is None:
            return resolved
        # Strip inherited effort, then re-apply the selected one if present
        base_kwargs: dict[str, Any] = {
            "provider": selected.provider,
            "model": selected.model,
        }
        if selected.reasoning_effort is not None:
            base_kwargs["reasoningEffort"] = selected.reasoning_effort
        # Preserve all other resolved fields except reasoningEffort
        return LlmCallConfig(
            provider=base_kwargs["provider"],
            model=base_kwargs["model"],
            reasoningEffort=base_kwargs.get("reasoningEffort"),
            maxTokens=resolved.maxTokens,
            temperature=resolved.temperature,
            topP=resolved.topP,
        )

    dispose_assembly = agent_ctx.on("system-prompt/assemble", _on_assemble)
    dispose_request = agent_ctx.on("agent/request", _on_request)

    def dispose() -> None:
        dispose_assembly()
        dispose_request()

    return dispose
