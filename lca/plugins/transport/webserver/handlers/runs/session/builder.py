"""Build one coherent legacy RunSession from request and runtime bindings."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any, cast

from lca.contracts.atoms.ids import new_id
from lca.contracts.mechanisms.capability import require_capability
from lca.contracts.observability.run_journal import RunJournalFactory
from lca.plugins.transport.webserver.handlers.runs.observability.binding import assemble_run_hub
from lca.plugins.transport.webserver.handlers.runs.observability.identity import default_agent_ref
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry, RunSession
from lca.plugins.transport.webserver.handlers.runs.session.setup_types import RunSessionRequest


class RunSessionBuilder:
    """Own identity allocation, carrier normalization, and run-local assembly.

    The builder does not register sessions or emit diagnostics. Those are
    lifecycle concerns owned by the setup coordinator and its collaborators.
    """

    def __init__(self, registry: RunRegistry, *, ctx: Any) -> None:
        self._registry = registry
        self._ctx = ctx

    def build(self, request: RunSessionRequest) -> RunSession:
        """Build a journal-enabled session without publishing it to the registry.

        ADR-0164 Phase 7: 在 builder 阶段就准备 ``StepLifecycleStore``
        并注入到 journal factory, 否则 ``step_tree_bundle.backend``
        会一直是 None, ``journal.json`` 永远不会落盘。
        """
        run_id = new_id("run")
        trace_id = new_id("trace")
        started_at = time.time()
        agent = request.agent if request.agent is not None else default_agent_ref()
        cleaned_attachment_ids = _clean_attachment_ids(request.attachment_ids)

        journal_factory = cast(
            "RunJournalFactory", require_capability(self._ctx, "run_ledger_factory")
        )
        # 1) 直接用 identity 字段造 lifecycle store (不依赖 tail/hub)
        from lca.runtime.journal_setup import BuildJournalMetadata, build_step_lifecycle_store

        lifecycle_store = build_step_lifecycle_store(
            run_id=run_id,
            trace_id=trace_id,
            metadata=BuildJournalMetadata(
                agent_role=agent.name or agent.agent_id or "",
                strategy_key=request.mode or "solo",
                objective=request.user_text or "",
                started_at=started_at,
            ),
        )
        # 2) 注入 factory → backend 拿到 store
        components = journal_factory.create_run_components(
            jsonl_path=self._registry.jsonl_path_for(run_id),
            lifecycle_store=lifecycle_store,
        )
        # 3) 组装 hub
        hub = assemble_run_hub(
            jsonl_writer=components.writer,
            tail=components.tail,
            ctx=self._ctx,
            extra_projectors=(self._registry.bind_process_journal(journal_factory),),
        )
        # 4) 一次构造完整 session
        return RunSession(
            run_id=run_id,
            trace_id=trace_id,
            jsonl_path=self._registry.jsonl_path_for(run_id),
            tail=components.tail,
            hub=hub,
            lifecycle_store=lifecycle_store,
            step_tree_bundle=components.step_tree_writer,
            question=request.question,
            user_text=request.user_text,
            mode=request.mode,
            prior_turns=tuple(request.prior_turns),
            attachment_ids=cleaned_attachment_ids,
            agent=agent,
            device_id=request.device_id.strip(),
            plane=request.plane.strip(),
            extra_plane=request.extra_plane.strip(),
            execution_target=request.execution_target.strip(),
            started_at=started_at,
            locator=self._registry.locator(),
        )


def _clean_attachment_ids(values: Sequence[str]) -> tuple[str, ...]:
    """Normalize attachment carriers at the edge of session construction."""
    return tuple(str(item).strip() for item in values if str(item).strip())


__all__ = ["RunSessionBuilder"]
