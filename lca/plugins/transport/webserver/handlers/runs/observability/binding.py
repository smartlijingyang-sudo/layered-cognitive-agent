"""Bind observability projections for one Gateway run.

ADR-0167 D11 简化:
    - ``ensure_session_hub`` 不再 lazy 构造 lifecycle_store。
    - deriver (StepTreeAccumulator) 由 ``RunSessionBuilder.build`` 阶段
      构造 + subscribe 到 spine; lifecycle_store 字段已被删除。
    - 任何 ``ensure_session_hub`` 调用点都被保留,行为退化为"返回已 bind
      的 hub,或抛错"。 因为 RunSessionBuilder 现在总是把 hub 设上,
      真正的 fallback 不会发生 —— 但保留入口便于过渡期 regression。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.observability.run_journal import LiveRunProjection
from lca.contracts.protocols import JournalProjector
from lca.infrastructure.observability import BoundObservability
from lca.infrastructure.observability.facade.settings import ObservabilitySettings
from lca.plugins.transport.webserver.handlers.runs.session.session import RunSession


def assemble_run_hub(
    *,
    jsonl_writer: JournalProjector,
    tail: LiveRunProjection,
    ctx: Any,
    settings: ObservabilitySettings | None = None,
    extra_projectors: Sequence[JournalProjector] = (),
) -> BoundObservability:
    """Extend boot observability with immutable projections for one run."""
    del settings
    from lca.harness.observability import make_minimal_bound

    try:
        base: BoundObservability = require_capability(ctx, "observability")
    except MissingCapabilityError:
        from lca.infrastructure.observability.adapters.policy import AttributePolicy
        from lca.infrastructure.observability.facade import BoundObservability as FacadeBound

        minimal = make_minimal_bound()
        return FacadeBound(
            journal=minimal.journal,
            tracer=minimal.tracer,
            policy=AttributePolicy(),
            scorers=minimal.scorers,
        )

    run_bound = base.with_journal_projection(jsonl_writer)
    run_bound = run_bound.with_journal_projection(tail)
    for projection in extra_projectors:
        run_bound = run_bound.with_journal_projection(projection)
    return run_bound


def ensure_session_hub(
    session: RunSession, *, ctx: Any
) -> BoundObservability:
    """Return the already-bound hub on the session.

    ADR-0167 D11: RunSessionBuilder 在 ``build`` 阶段已经把 hub 装上, 任何
    后续 ensure_session_hub 调用都假定 hub 已存在。如果 session 没 hub,
    抛 RuntimeError (迁移期 guard; 不允许无 hub 静默 lazy 装)。
    """
    if session.hub is None:
        raise RuntimeError(
            "ensure_session_hub: session.hub is None; "
            "RunSessionBuilder.build must be called before lifecycle.start"
        )
    return session.hub


__all__ = [
    "assemble_run_hub",
    "ensure_session_hub",
]
