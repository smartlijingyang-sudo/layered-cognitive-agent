"""Legacy facade for the ``runs/execute`` carrier surface.

ADR-0122 / PR-3. The previous implementation duplicated the run lifecycle
twelve times across this module (``execute_run``, ``schedule_run``,
``resume_run``, ``_freeze_bindings``, ``_stage_machine_attachments``,
``_RunLifecycleCoordinator`` etc.) and ran alongside
:class:`RunLifecycleCoordinator` as a parallel production path. The
duplication caused the ambient-scope bug ``run_f03bd17f77f1``: the
legacy path bound ``run_file_store_scope`` but the new path did not, and a
missing call in either path silently degraded think.main to a synchronous
``RuntimeError``.

This module is now a thin facade. Real lifecycle / hub / scope work lives
in:

- :mod:`lca.plugins.transport.webserver.handlers.runs.lifecycle`
  — :class:`RunLifecycleCoordinator.execute` / ``resume``
- :mod:`lca.plugins.transport.webserver.handlers.runs.execute.execution_environment`
  — :class:`RunExecutionEnvironment.prepare` (binds :class:`RunAmbit`)
- :mod:`lca.plugins.transport.webserver.handlers.runs.execute.scheduling`
  — :func:`schedule_run` (asyncio task handle)
- :mod:`lca.plugins.transport.webserver.handlers.runs.execute.environment_bindings`
  — bindings / driver / provider resolution
- :mod:`lca.plugins.transport.webserver.handlers.runs.execute.loop_drivers`
  — :class:`CognitiveRunDriver`

The four symbols still imported by handlers + tests are re-exported
verbatim; nothing in this module owns carrier-side state.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lca.contracts.models.core.conversation import ConversationTurn
from lca.contracts.protocols.runtime.infra import MachineResolver
from lca.plugins.transport.webserver.handlers.runs.execute.scheduling import (
    schedule_run as schedule_run,
)
from lca.plugins.transport.webserver.handlers.runs.observability.identity import (
    AgentRef,
)
from lca.plugins.transport.webserver.handlers.runs.session.session import (
    RunRegistry,
    RunSession,
)

__all__ = [
    "create_run_session",
    "execute_run",
    "llm_status",
    "resume_run",
    "schedule_run",
]


def llm_status(ctx: Any) -> dict[str, bool]:
    """Whether the boot tree's resolver can hand out a real adapter."""
    try:
        resolver = ctx.inject("llm_resolver")
    except KeyError:
        return {"llm_available": False}
    return {"llm_available": resolver.is_available()}


def create_run_session(
    registry: RunRegistry,
    *,
    question: str,
    user_text: str,
    mode: str = "solo",
    attachment_ids: Sequence[str] = (),
    prior_turns: Sequence[ConversationTurn] = (),
    agent: AgentRef | None = None,
    device_id: str = "",
    plane: str = "",
    extra_plane: str = "",
    execution_target: str = "",
    ctx: Any | None = None,
) -> RunSession:
    """Build a RunSession through the unified factory.

    The historical implementation owned the body inline; it has been
    reduced to a one-line delegation so this module carries no carrier
    state. ADR-0122 / PR-3.
    """
    if ctx is None:
        from lca.application.api import get_or_create_default_ctx

        ctx = get_or_create_default_ctx()

    from lca.plugins.transport.webserver.handlers.runs.session.setup import (
        RunSessionFactory,
    )
    from lca.plugins.transport.webserver.handlers.runs.session.setup_types import (
        RunSessionRequest,
    )

    return RunSessionFactory(registry, ctx=ctx).create(
        RunSessionRequest(
            question=question,
            user_text=user_text,
            mode=mode,
            attachment_ids=tuple(
                str(i).strip() for i in attachment_ids if str(i).strip()
            ),
            prior_turns=tuple(prior_turns),
            agent=agent,
            device_id=device_id.strip(),
            plane=plane.strip(),
            extra_plane=extra_plane.strip(),
            execution_target=execution_target.strip(),
        )
    )


async def execute_run(
    registry: RunRegistry,
    *,
    run_id: str,
    question: str,
    mode: str = "solo",
    ctx: Any | None = None,
    machine_resolver: MachineResolver | None = None,
) -> None:
    """Backwards-compat alias for the unified lifecycle entry point.

    Historical implementations carried a full body inline (the parallel
    path that lost ``run_file_store_scope``). It is now a thin delegation
    to :class:`RunLifecycleCoordinator.execute` so there is exactly one
    run path left in the codebase.
    """
    # Late-bound attribute lookup so test patches (patch.object on the
    # ``execute`` module) take effect at call time.
    import lca.plugins.transport.webserver.handlers.runs.execute as _self_pkg

    await _self_pkg.RunLifecycleCoordinator(
        registry, machine_resolver=machine_resolver
    ).execute(
        run_id=run_id,
        question=question,
        mode=mode,
        ctx=ctx,
    )


async def resume_run(session: RunSession, registry: RunRegistry, answer: str) -> None:
    """Backwards-compat alias for the unified resume entry point."""
    import lca.plugins.transport.webserver.handlers.runs.execute as _self_pkg

    await _self_pkg.RunLifecycleCoordinator(registry).resume(session, answer=answer)
