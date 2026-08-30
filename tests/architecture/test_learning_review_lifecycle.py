"""Acceptance tests for the candidate-only terminal learning-review bridge."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pytest

from lca.contracts.capabilities import (
    LEARNING_FAILURE_ANALYZER,
    LEARNING_REVIEW_SERVICE,
    LEARNING_REVIEW_TICKET_STORE,
    LEARNING_SKILL_ACQUIRER,
    RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY,
)
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.protocols.runtime_lifecycle import (
    RuntimeBudgetSnapshot,
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
)
from lca.harness.profile.plan_compiler import compile_plan
from lca.harness.profile.resolve import resolve_profile
from lca.infrastructure.learning.review_ticket_store import InMemoryLearningReviewTicketStore
from lca.runtime.runtime_event_publisher import (
    InMemoryRuntimeLifecycleSubscriberRegistry,
)
from lca.plugins.insight.failure_analyzer import FailureAnalyzerService
from lca.plugins.learning import review_lifecycle
from lca.plugins.learning.review_lifecycle import (
    LearningReviewService,
    LearningReviewTicketStatus,
)
from lca.plugins.skill.auto_acquire import AutoAcquireSkillService

REPO = Path(__file__).resolve().parents[2]


@dataclass
class _PluginContext:
    services: dict[str, object] = field(default_factory=dict)

    def provide(self, key: object, value: object, **kwargs: object) -> None:
        del kwargs
        self.services[str(key)] = value

    def require(self, key: object) -> object:
        return self.services[str(key)]


def _event(
    event_type: RuntimeLifecycleEventType,
    status: TaskStatus,
    *,
    trace_id: str = "trace-learning-review",
) -> RuntimeLifecycleEvent:
    return RuntimeLifecycleEvent(
        type=event_type,
        trace_id=trace_id,
        plan_ref="plan://learning-review-test",
        status=status,
        step=4,
        state_ref="state://learning-review-test/4",
        journal_sequence=18,
        budget=RuntimeBudgetSnapshot(
            max_tokens=1000,
            max_cost_usd=1.0,
            max_steps=8,
            max_wall_clock_seconds=60,
            used_tokens=500,
            used_cost_usd=0.5,
            used_steps=4,
        ),
    )


def _service(*, max_pending: int = 4) -> LearningReviewService:
    return LearningReviewService(
        enabled=True,
        allowed_statuses=frozenset({TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.PARTIAL}),
        max_pending=max_pending,
        lease_seconds=300,
        ticket_store=InMemoryLearningReviewTicketStore(),
        skill_acquirer=AutoAcquireSkillService(
            enabled=True,
            min_confidence=0.7,
            min_evidence=3,
        ),
        failure_analyzer=FailureAnalyzerService(
            enabled=True,
            triggers=frozenset({"budget_exceeded"}),
        ),
    )


def test_self_improving_profile_declares_review_service_and_freezes_it_before_publisher() -> None:
    """Review must be a real Profile capability registered before publisher freeze."""

    resolved = resolve_profile("profiles/self-improving-minimal.yaml")
    compile_plan(resolved)
    ids = [plugin.id for plugin in resolved.plugins]
    provided = {
        capability
        for plugin in resolved.plugins
        for capability in plugin.definition.provided_capability_keys
    }

    assert LEARNING_REVIEW_SERVICE.key in provided
    assert ids.index("lca-learning-review-lifecycle-subscriber") < ids.index(
        "lca-runtime-lifecycle-publisher"
    )


def test_only_terminal_events_create_idempotent_reference_tickets() -> None:
    """Phase/start events never produce a learning request, and replay is idempotent."""

    service = _service()
    started = _event(RuntimeLifecycleEventType.STARTED, TaskStatus.WORKING)
    completed = _event(RuntimeLifecycleEventType.COMPLETED, TaskStatus.COMPLETED)

    assert service.enqueue_terminal_event(started) is None
    first = service.enqueue_terminal_event(completed)
    second = service.enqueue_terminal_event(completed)

    assert first is not None
    assert first == second
    assert first.trace_id == completed.trace_id
    assert first.plan_ref == completed.plan_ref
    assert first.state_ref == completed.state_ref
    assert first.journal_sequence == completed.journal_sequence
    assert len(service.tickets) == 1
    assert not hasattr(first, "task")
    assert not hasattr(first, "approval_request")


def test_pending_queue_fails_closed_without_evicting_unreviewed_evidence() -> None:
    """A full review queue rejects a new ticket instead of silently discarding one."""

    service = _service(max_pending=1)
    first = service.enqueue_terminal_event(
        _event(RuntimeLifecycleEventType.COMPLETED, TaskStatus.COMPLETED, trace_id="trace-1")
    )
    second = service.enqueue_terminal_event(
        _event(RuntimeLifecycleEventType.FAILED, TaskStatus.FAILED, trace_id="trace-2")
    )

    assert first is not None
    assert second is None
    assert service.tickets == (first,)


def test_claimed_success_assessment_only_returns_evidence_gated_draft() -> None:
    """A completed ticket may ask existing candidate services for a non-promoted draft."""

    service = _service()
    ticket = service.enqueue_terminal_event(
        _event(RuntimeLifecycleEventType.COMPLETED, TaskStatus.COMPLETED)
    )
    assert ticket is not None
    claimed = service.claim_next()
    assert claimed is not None
    assert claimed.ticket_id == ticket.ticket_id
    assert claimed.status is LearningReviewTicketStatus.CLAIMED

    assessment = service.assess_success(
        ticket.ticket_id,
        procedure="Validate the declared capability graph before executing a run.",
        confidence=0.8,
        evidence_refs=("journal://18", "state://4", "artifact://summary"),
    )

    assert assessment.skill_candidate is not None
    assert assessment.skill_candidate.status == "draft"
    assert assessment.failure_analysis is None
    assert service.tickets[0].status is LearningReviewTicketStatus.ASSESSED


def test_failure_assessment_respects_configured_trigger_and_terminal_status() -> None:
    """Only failed/partial tickets may route to the preconfigured read-only analyzer."""

    service = _service()
    ticket = service.enqueue_terminal_event(
        _event(RuntimeLifecycleEventType.FAILED, TaskStatus.FAILED)
    )
    assert ticket is not None
    assert service.claim_next() is not None

    rejected = service.assess_failure(
        ticket.ticket_id,
        trigger="tool_error",
        evidence_refs=("journal://18",),
    )
    assert rejected.failure_analysis is None

    service = _service()
    ticket = service.enqueue_terminal_event(
        _event(RuntimeLifecycleEventType.FAILED, TaskStatus.FAILED)
    )
    assert ticket is not None
    assert service.claim_next() is not None
    assessment = service.assess_failure(
        ticket.ticket_id,
        trigger="budget_exceeded",
        evidence_refs=("journal://18",),
        summary="The run exhausted its declared step budget.",
    )

    assert assessment.failure_analysis is not None
    assert assessment.failure_analysis.run_ref == ticket.trace_id
    assert "Do not modify grants" in assessment.failure_analysis.suggestions[1]


def test_assessment_rejects_mismatched_terminal_semantics() -> None:
    """A ticket type cannot be reinterpreted as the opposite learning outcome."""

    service = _service()
    ticket = service.enqueue_terminal_event(
        _event(RuntimeLifecycleEventType.COMPLETED, TaskStatus.COMPLETED)
    )
    assert ticket is not None
    assert service.claim_next() is not None

    with pytest.raises(ValueError, match="failed or partial"):
        service.assess_failure(
            ticket.ticket_id,
            trigger="budget_exceeded",
            evidence_refs=("journal://18",),
        )


@pytest.mark.asyncio
async def test_plugin_registers_passive_subscriber_and_profile_owned_service() -> None:
    """Plugin boot binds the same service to the registry and its capability seam."""

    registry = InMemoryRuntimeLifecycleSubscriberRegistry()
    context = _PluginContext(
        {
            RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key: registry,
            LEARNING_SKILL_ACQUIRER.key: AutoAcquireSkillService(True, 0.7, 3),
            LEARNING_FAILURE_ANALYZER.key: FailureAnalyzerService(
                True,
                frozenset({"budget_exceeded"}),
            ),
            LEARNING_REVIEW_TICKET_STORE.key: InMemoryLearningReviewTicketStore(),
        }
    )

    await review_lifecycle.setup.setup(context, review_lifecycle.Config())
    service = context.services[LEARNING_REVIEW_SERVICE.key]

    assert isinstance(service, LearningReviewService)
    assert [item.id for item in registry.snapshot()] == ["learning-review"]
    await service.publish(_event(RuntimeLifecycleEventType.COMPLETED, TaskStatus.COMPLETED))
    assert len(service.tickets) == 1


def test_learning_review_source_cannot_materialize_skills_or_publish_profiles() -> None:
    """The post-turn bridge remains a candidate-only seam with no write bypass."""

    sources = "\n".join(
        (REPO / path).read_text(encoding="utf-8")
        for path in (
            "lca/plugins/learning/review_lifecycle.py",
            "lca/plugins/learning/review_service.py",
        )
    )

    assert "install_package(" not in sources
    assert "write_text(" not in sources
    assert "publish_profile(" not in sources
    assert "AgentState" not in sources
    assert "EffectGateway" not in sources
