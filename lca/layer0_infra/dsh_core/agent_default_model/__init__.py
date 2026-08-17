"""1:1 port of ``@deepseek-ai/dsh-agent-default-model``.

Default model selection for an Agent without a session-specific selection.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import ClassVar, NewType

from lca.layer0_infra.plugin.kernel._context import PluginContext
from lca.layer0_infra.plugin.kernel._service import Service

# ---------------------------------------------------------------------------
# Types from ``@deepseek-ai/dsh-llm`` (full port pending)
# ---------------------------------------------------------------------------

ReasoningEffortId = NewType("ReasoningEffortId", str)
"""Brand an adapter-owned reasoning-effort identifier."""


def _ReasoningEffortId(id: str) -> ReasoningEffortId:  # noqa: N802
    return ReasoningEffortId(id)


# ---------------------------------------------------------------------------
# Types from ``@deepseek-ai/dsh-agent`` (full port pending)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelSelection:
    """Agent-facing model selection projected from stored settings."""

    provider: str
    model: str
    reasoning_effort: ReasoningEffortId | None = None


# ---------------------------------------------------------------------------
# Settings constants (from ``@deepseek-ai/dsh-settings``)
# ---------------------------------------------------------------------------

AGENT_DEFAULT_MODEL_SETTINGS_NAMESPACE: str = "agent-default-model"
"""Settings namespace carrying the default model selection for future Agents."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AgentDefaultModelSettings:
    """Stored and composed default model selection."""

    provider: str
    model: str
    reasoning_effort: str | None = None


@dataclass(frozen=True)
class Config:
    """Composition entry for the default model selection."""

    provider: str
    model: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _selection(settings: AgentDefaultModelSettings) -> ModelSelection:
    """Project stored settings onto the Agent-facing selection type."""
    return ModelSelection(
        provider=settings.provider,
        model=settings.model,
        reasoning_effort=(
            _ReasoningEffortId(settings.reasoning_effort)
            if settings.reasoning_effort is not None
            else None
        ),
    )


# ---------------------------------------------------------------------------
# Settings wiring (from ``@deepseek-ai/dsh-settings``)
# ---------------------------------------------------------------------------


def _install_settings_section(
    ctx: PluginContext,
    ns: str,
    entry: AgentDefaultModelSettings,
    *,
    set_source: object,  # Callable[[Callable[[], AgentDefaultModelSettings]], None]
    on_change: Callable[[], None],
) -> None:
    """Install the canonical optional-settings consumer wiring.

    While a settings service exists, register *ns* with the consumer's
    composition entry as the ``base`` layer and point the source thunk at
    the resolved scope; when the service goes away, fall back to the entry.
    """
    set_source_fn: Callable[[Callable[[], AgentDefaultModelSettings]], None] = set_source  # type: ignore[assignment]

    async def _setup(sctx: PluginContext) -> None:
        settings_svc = sctx.get("settings")
        if settings_svc is None:
            return
        scope = settings_svc.register(
            ns,
            base={
                "provider": entry.provider,
                "model": entry.model,
            },
        )
        set_source_fn(lambda: _settings_to_model(scope.get()))

        def _dispose() -> None:
            from lca.layer0_infra.dsh_core.scope import scope_of

            if scope_of(ctx) is not None:
                return  # agent scope disposing — skip fallback
            set_source_fn(lambda: entry)
            on_change()

        sctx.effect(_dispose, label="agent-default-model settings disposer")
        on_change()

        def _watcher(_next_val: object, _prev_val: object) -> None:
            from lca.layer0_infra.dsh_core.scope import scope_of

            if scope_of(ctx) is not None:
                return
            on_change()

        scope.watch(_watcher)

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(ctx.inject(("settings",), _setup))
        task.add_done_callback(lambda _: None)
    except RuntimeError:
        pass  # no running loop — settings not available


def _settings_to_model(raw: object) -> AgentDefaultModelSettings:
    """Project a resolved settings scope value onto the settings dataclass."""
    if isinstance(raw, dict):
        return AgentDefaultModelSettings(
            provider=raw.get("provider", ""),
            model=raw.get("model", ""),
            reasoning_effort=raw.get("reasoningEffort") or raw.get("reasoning_effort"),
        )
    if isinstance(raw, AgentDefaultModelSettings):
        return raw
    return AgentDefaultModelSettings(provider="", model="")


# ---------------------------------------------------------------------------
# Schema (validates stored settings documents)
# ---------------------------------------------------------------------------

AGENT_DEFAULT_MODEL_SETTINGS_SCHEMA: dict[str, str] = {
    "provider": "string",
    "model": "string",
    "reasoningEffort": "string?",
}
"""Schema of the default Agent model settings section."""


# ---------------------------------------------------------------------------
# AgentDefaultModelConfig service
# ---------------------------------------------------------------------------


class AgentDefaultModelConfig(Service):
    """Owns the default model selection independently of any Host or transport.

    The composition entry remains usable without a settings provider; when one
    is mounted, its user layer is read live.
    """

    name: ClassVar[str] = "agentDefaultModel"

    def __init__(self, ctx: PluginContext, config: Config | None = None) -> None:
        cfg = config or Config(provider="", model="")
        self._entry = AgentDefaultModelSettings(provider=cfg.provider, model=cfg.model)
        self._source: Callable[[], AgentDefaultModelSettings] = lambda: self._entry

        super().__init__(ctx, cfg)

        _install_settings_section(
            ctx,
            AGENT_DEFAULT_MODEL_SETTINGS_NAMESPACE,
            self._entry,
            set_source=lambda current: setattr(self, "_source", current),
            on_change=lambda: None,
        )

    def current_selection(self) -> ModelSelection:
        """Read the current default model selection.

        Returns:
            A detached provider, model, and optional reasoning selection.
        """
        return _selection(self._source())

    async def save_selection(self, next_: ModelSelection) -> None:
        """Save the complete default model selection.

        A deployment without a settings provider keeps its composition entry.
        """
        settings_svc = self.ctx.get("settings")
        if settings_svc is None:
            return
        section: dict[str, str] = {
            "provider": next_.provider,
            "model": next_.model,
        }
        if next_.reasoning_effort is not None:
            section["reasoningEffort"] = str(next_.reasoning_effort)
        await settings_svc.replace(AGENT_DEFAULT_MODEL_SETTINGS_NAMESPACE, section)
