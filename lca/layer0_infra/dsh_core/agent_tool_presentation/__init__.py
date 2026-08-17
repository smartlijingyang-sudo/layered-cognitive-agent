"""1:1 port of ``@deepseek-ai/dsh-agent-tool-presentation``.

Agent-plane presentation selector: the row an agent preset carries to say
which form of its tools the model sees.

The tool registry itself stays on the host plane — the agent loop's
scheduler, the API proxy's presenters, and every tool plugin are all its
consumers, so it cannot move into a preset.  What a preset CAN own is the
presentation: ``ctx.tools.present_as()`` declares it for the mounting SCOPE,
which is the preset's standing mount, so the declaration covers every agent
joined to that preset and a Code Mode preset runs beside native ones in one
process.  One row per composition, not one per session.

A code mode needs a TypeScript code runtime, which is a host-plane service.
This row therefore waits for it rather than assuming it: a preset selecting
Code Mode against a deployment that composes no runtime fails at mount, named
in the preset's own activation audit, instead of at the first prompt.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from lca.layer0_infra.plugin.kernel._context import PluginContext

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

ToolPresentationMode = Literal["native", "code", "both"]
"""The form this agent's model sees."""

# ---------------------------------------------------------------------------
# Plugin metadata
# ---------------------------------------------------------------------------

name: str = "tool-presentation"
"""Cordis plugin name."""

inject: tuple[str, ...] = ("tools",)
"""Required services.

``codeRuntime`` is NOT listed: a ``native`` row must mount in a deployment
that composes no runtime, and the mode-dependent wait is declared inside
:func:`apply` instead.
"""

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Config:
    """Plugin config."""

    mode: ToolPresentationMode
    """The form this agent's model sees.

    ``native`` sends every visible schema, ``code`` sends only ``run_code``
    plus a generated SDK, ``both`` sends both.  Required rather than
    defaulted: the deployment default is what a preset without this row
    already gets, so an omitted value would mean the row was composed for
    nothing.
    """


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def apply(ctx: PluginContext, config: Config) -> None:
    """Declare the tool presentation for every agent this composition covers.

    Args:
        ctx: The mounting composition's scope context (a preset's standing scope).
        config: The selected presentation.
    """
    # ``present_as`` is itself the effect — it registers through the calling
    # context and hands back that exact disposer — so the declaration unwinds
    # with this row without a second wrapper owning it.
    if config.mode == "native":
        ctx.get("tools").present_as("native")
        return

    # The wait is the loud failure: an entry still pending on ``codeRuntime``
    # is what ``dsh-agent-presets`` reports as an unusable row, naming this id.
    async def _with_runtime(runtime_ctx: PluginContext) -> None:
        runtime_ctx.get("tools").present_as(config.mode)

    import asyncio

    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(ctx.inject(("codeRuntime",), _with_runtime))
        task.add_done_callback(lambda _: None)
    except RuntimeError:
        pass  # no running loop — codeRuntime not available
