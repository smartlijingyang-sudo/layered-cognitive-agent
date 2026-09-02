"""Build one coherent legacy RunSession from request and runtime bindings.

ADR-0167 D11 简化:
    - 不再注入 ``StepLifecycleStore``;改构造 ``StepCoordinator``。
    - deriver (StepTreeAccumulator / Narrative / Graph) 由 transport
      在 ``RunSessionBuilder.build`` 阶段构造并 subscribe 到 spine。
    - journal.json 落盘由 StepTreeAccumulatorDeriver.flush() 触发。
    - narrative.md 落盘由 NarrativeDeriver.write() 触发。
    - phase_graph.dot 落盘由 GraphDeriver.flush() 触发。
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from typing import Any, cast

from lca.contracts.atoms.ids import new_id
from lca.contracts.mechanisms.capability import MissingCapabilityError, require_capability
from lca.contracts.observability.run_journal import RunJournalFactory
from lca.infrastructure.observability.spine.derivers.step_tree_accumulator import (
    StepTreeAccumulatorDeriver,
)
from lca.infrastructure.observability.writable_matrix.registry import (
    WritableFaceRegistry,
)
from lca.plugins.transport.webserver.handlers.runs.observability.binding import assemble_run_hub
from lca.plugins.transport.webserver.handlers.runs.observability.identity import default_agent_ref
from lca.plugins.transport.webserver.handlers.runs.session.session import RunRegistry, RunSession
from lca.plugins.transport.webserver.handlers.runs.session.setup_types import RunSessionRequest
from lca.runtime.journal_setup import BuildJournalMetadata, build_step_coordinator

log = logging.getLogger(__name__)


class RunSessionBuilder:
    """Own identity allocation, carrier normalization, and run-local assembly."""

    def __init__(self, registry: RunRegistry, *, ctx: Any) -> None:
        self._registry = registry
        self._ctx = ctx

    def build(self, request: RunSessionRequest) -> RunSession:
        """Build a journal-enabled session without publishing it to the registry.

        ADR-0167 D11: 在 builder 阶段构造 ``StepCoordinator`` + 装配
        per-run derivers。 derivers 必须 subscribe 到 ``event_spine``
        才能累积 events → journal.json / narrative.md / phase_graph.dot。
        """
        run_id = new_id("run")
        trace_id = new_id("trace")
        started_at = time.time()
        agent = request.agent if request.agent is not None else default_agent_ref()
        cleaned_attachment_ids = _clean_attachment_ids(request.attachment_ids)

        journal_factory = cast(
            "RunJournalFactory", require_capability(self._ctx, "run_ledger_factory")
        )

        # ── 1) 构造 StepCoordinator (WritableFaceRegistry 已 bind) ──
        try:
            registry = require_capability(self._ctx, "writable_face_registry")
        except MissingCapabilityError:
            # 缺 registry 时降级为 NullStorage 5 面 — 测试场景 / 单元测试用;
            # 生产 profile 必须显式装 writable.matrix.default。
            registry = WritableFaceRegistry()
            from lca.infrastructure.observability.writable_matrix import (
                LineCoalescer,
                NdjsonSerializer,
                NullStorage,
                SpineEmitter,
                StandardDriver,
            )
            registry.register("emitter", SpineEmitter())
            registry.register("driver", StandardDriver())
            registry.register("coalescer", LineCoalescer())
            registry.register("serializer", NdjsonSerializer())
            registry.register("storage", NullStorage())
        if not isinstance(registry, WritableFaceRegistry):
            raise RuntimeError(
                f"writable_face_registry must be WritableFaceRegistry,"
                f" got {type(registry).__name__}"
            )

        coordinator = build_step_coordinator(
            registry=registry,
            run_id=run_id,
            trace_id=trace_id,
            metadata=BuildJournalMetadata(
                agent_role=agent.name or agent.agent_id or "",
                strategy_key=request.mode or "solo",
                objective=request.user_text or "",
                started_at=started_at,
            ),
        )

        # ── 2) 构造 per-run deriver (subscribe 到 spine event_spine) ──
        locator = self._registry.locator()
        run_dir = locator.run_dir(run_id) if locator is not None else None

        spine_core = require_capability(self._ctx, "event_spine")
        # duck-type: SpineCore 有 .event_spine; tests / stub 提供裸 EventSpine
        event_spine = getattr(spine_core, "event_spine", None) or spine_core

        step_tree_deriver: StepTreeAccumulatorDeriver | None = None
        if run_dir is not None:
            step_tree_deriver = StepTreeAccumulatorDeriver(
                run_id=run_id,
                run_dir=run_dir,
                agent_role=agent.name or agent.agent_id or "",
                strategy_key=request.mode or "solo",
                plan_ref="",
            )
            event_spine.subscribe(step_tree_deriver.on_event)
            log.debug(
                "run_session_builder: subscribed step_tree deriver run=%s dir=%s",
                run_id, run_dir,
            )

        # ── 3) 注入 factory → 拿 LiveTail + 空 step_tree_writer ──
        components = journal_factory.create_run_components(
            jsonl_path=self._registry.jsonl_path_for(run_id),
        )

        # ── 4) 把 step_tree_deriver + narrative_writer 装到 bundle ──
        bundle = components.step_tree_writer
        # bundle 是 frozen dataclass (_StepTreeBundle); 字段替换
        if bundle is not None and step_tree_deriver is not None:
            from dataclasses import replace as _dc_replace

            components = components.__class__(
                writer=components.writer,
                tail=components.tail,
                step_tree_writer=_dc_replace(
                    bundle,
                    deriver=step_tree_deriver,
                ),
            )

        # ── 5) assemble hub ──
        hub = assemble_run_hub(
            jsonl_writer=components.writer,
            tail=components.tail,
            ctx=self._ctx,
            extra_projectors=(self._registry.bind_process_journal(journal_factory),),
        )

        return RunSession(
            run_id=run_id,
            trace_id=trace_id,
            jsonl_path=self._registry.jsonl_path_for(run_id),
            tail=components.tail,
            hub=hub,
            thread_tree_writer=step_tree_deriver,
            coordinator=coordinator,
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
            locator=locator,
        )


def _clean_attachment_ids(values: Sequence[str]) -> tuple[str, ...]:
    """Normalize attachment carriers at the edge of session construction."""
    return tuple(str(item).strip() for item in values if str(item).strip())


__all__ = ["RunSessionBuilder"]
