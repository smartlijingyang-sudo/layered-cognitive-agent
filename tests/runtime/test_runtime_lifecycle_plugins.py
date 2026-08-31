"""Regression coverage for composable passive Agent Loop lifecycle publication."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from lca.contracts.capabilities import (
    RUNTIME_LIFECYCLE_PUBLISHER,
    RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY,
)
from lca.contracts.models.core.lifecycle import TaskStatus
from lca.contracts.models.core.result import Result
from lca.contracts.models.core.state import AgentState, Budget
from lca.contracts.protocols.runtime.runtime_lifecycle import (
    RuntimeBudgetSnapshot,
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
    RuntimeLifecycleSubscriberContribution,
)
from lca.plugins.providers.state import runtime_lifecycle, runtime_lifecycle_logging
from lca.runtime.runtime_event_publisher import (
    CompositeRuntimeLifecyclePublisher,
    InMemoryRuntimeLifecycleSubscriberRegistry,
    LifecyclePublisherFailureMode,
    RuntimeLifecyclePublisherError,
)
from lca.runtime.runtime_loop import CognitiveRuntime, _event_type_for_result


@dataclass
class _RecordingSubscriber:
    events: list[RuntimeLifecycleEvent]

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        self.events.append(event)


class _FailingSubscriber:
    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        del event
        raise RuntimeError("subscriber unavailable")


@dataclass
class _PluginContext:
    services: dict[str, object] = field(default_factory=dict)

    def provide(self, key: object, value: object, **kwargs: object) -> None:
        del kwargs
        self.services[str(key)] = value

    def require(self, key: object) -> object:
        return self.services[str(key)]


@dataclass
class _Bindings:
    lifecycle_publisher: object

    def plan_ref(self) -> str:
        return "plan://runtime-lifecycle-test"


def _event(
    event_type: RuntimeLifecycleEventType = RuntimeLifecycleEventType.STARTED,
) -> RuntimeLifecycleEvent:
    return RuntimeLifecycleEvent(
        type=event_type,
        trace_id="trace-lifecycle",
        plan_ref="plan://runtime-lifecycle-test",
        status=TaskStatus.WORKING,
        step=2,
        budget=RuntimeBudgetSnapshot(
            max_tokens=100,
            max_cost_usd=1.0,
            max_steps=10,
            max_wall_clock_seconds=30,
            used_tokens=20,
            used_cost_usd=0.2,
            used_steps=2,
        ),
    )


@pytest.mark.asyncio
async def test_registry_orders_contributions_and_composite_freezes_snapshot() -> None:
    registry = InMemoryRuntimeLifecycleSubscriberRegistry()
    events: list[RuntimeLifecycleEvent] = []
    registry.register(
        RuntimeLifecycleSubscriberContribution("late", _RecordingSubscriber(events), 200)
    )
    registry.register(
        RuntimeLifecycleSubscriberContribution("early", _RecordingSubscriber(events), 10)
    )

    publisher = CompositeRuntimeLifecyclePublisher(registry.snapshot())
    registry.register(
        RuntimeLifecycleSubscriberContribution("later", _RecordingSubscriber(events), 300)
    )
    await publisher.publish(_event())

    assert [item.id for item in publisher.contributions] == ["early", "late"]
    assert len(events) == 2
    with pytest.raises(KeyError, match="already registered"):
        registry.register(
            RuntimeLifecycleSubscriberContribution("early", _RecordingSubscriber(events))
        )


@pytest.mark.asyncio
async def test_subscriber_failure_is_fail_open_by_default_but_strict_mode_fails_closed() -> None:
    event = _event()
    permissive = CompositeRuntimeLifecyclePublisher(
        (RuntimeLifecycleSubscriberContribution("unavailable", _FailingSubscriber()),)
    )
    await permissive.publish(event)

    strict = CompositeRuntimeLifecyclePublisher(
        (RuntimeLifecycleSubscriberContribution("audit", _FailingSubscriber()),),
        failure_mode=LifecyclePublisherFailureMode.FAIL_CLOSED,
    )
    with pytest.raises(RuntimeLifecyclePublisherError, match=r"'audit'.*'started'"):
        await strict.publish(event)


@pytest.mark.asyncio
async def test_plugins_contribute_then_freeze_default_lifecycle_logging() -> None:
    registry = InMemoryRuntimeLifecycleSubscriberRegistry()
    logging_context = _PluginContext({RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key: registry})
    await runtime_lifecycle_logging.setup.setup(
        logging_context,
        runtime_lifecycle_logging.Config(),
    )

    provider_context = _PluginContext({RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key: registry})
    await runtime_lifecycle.setup.setup(provider_context, runtime_lifecycle.Config())
    publisher = provider_context.services[RUNTIME_LIFECYCLE_PUBLISHER.key]

    assert isinstance(publisher, CompositeRuntimeLifecyclePublisher)
    assert publisher.failure_mode is LifecyclePublisherFailureMode.FAIL_OPEN
    assert [item.id for item in publisher.contributions] == ["structured-log"]


@pytest.mark.asyncio
async def test_runtime_terminal_projection_exposes_only_carrier_safe_metadata() -> None:
    events: list[RuntimeLifecycleEvent] = []
    runtime = CognitiveRuntime(cast("Any", _Bindings(_RecordingSubscriber(events))))
    state = AgentState(
        trace_id="trace-from-state",
        task="sensitive task must not be published",
        budget=Budget(max_steps=8, used_steps=3),
    )
    result = Result(
        trace_id="trace-from-result",
        status=TaskStatus.INPUT_REQUIRED,
        final_state_ref="state://durable/3",
        total_steps=3,
        budget_used=Budget(used_steps=3),
        extra={
            "phase_cursor": {"node_id": "act.approval"},
            "journal_seq_end": 11,
            "approval_request": {"secret": "must stay out of lifecycle event"},
        },
    )

    await runtime._publish_terminal_event(state, result)

    assert len(events) == 1
    published = events[0]
    assert published.type is RuntimeLifecycleEventType.INPUT_REQUIRED
    assert published.trace_id == "trace-from-result"
    assert published.state_ref == "state://durable/3"
    assert published.phase_cursor == "act.approval"
    assert published.journal_sequence == 11
    assert published.budget.max_steps == 8
    assert not hasattr(published, "task")
    assert not hasattr(published, "approval_request")


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (TaskStatus.COMPLETED, RuntimeLifecycleEventType.COMPLETED),
        (TaskStatus.PARTIAL, RuntimeLifecycleEventType.PARTIAL),
        (TaskStatus.INPUT_REQUIRED, RuntimeLifecycleEventType.INPUT_REQUIRED),
        (TaskStatus.CANCELED, RuntimeLifecycleEventType.CANCELED),
        (TaskStatus.FAILED, RuntimeLifecycleEventType.FAILED),
    ],
)
def test_terminal_status_maps_into_closed_lifecycle_event_type(
    status: TaskStatus,
    expected: RuntimeLifecycleEventType,
) -> None:
    result = Result(
        trace_id="trace",
        status=status,
        final_state_ref="state://result",
        total_steps=0,
        budget_used=Budget(),
    )

    assert _event_type_for_result(result) is expected
