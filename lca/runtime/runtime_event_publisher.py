"""Composable passive lifecycle publication for declarative Agent Loop turns.

This module is deliberately outside phase transactions. Publishers receive only
frozen carrier-safe event values, and the runtime invokes them at turn
boundaries. Therefore a plugin can expose progress to logs, streams, or audit
systems without gaining a state, Journal, Reducer, or Effect-Gateway control
path.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

import structlog

from lca.contracts.protocols.runtime.runtime_lifecycle import (
    RuntimeLifecycleEvent,
    RuntimeLifecyclePublisher,
    RuntimeLifecycleSubscriber,
    RuntimeLifecycleSubscriberContribution,
    RuntimeLifecycleSubscriberRegistry,
)

_log = structlog.get_logger("lca.runtime.lifecycle")


class LifecyclePublisherFailureMode(StrEnum):
    """Declare whether a subscriber outage may fail the Agent Loop boundary."""

    FAIL_OPEN = "fail_open"
    FAIL_CLOSED = "fail_closed"


class RuntimeLifecyclePublisherError(RuntimeError):
    """Attribute a strict lifecycle subscriber failure to its contribution."""

    def __init__(self, contribution_id: str, event: RuntimeLifecycleEvent) -> None:
        super().__init__(
            "runtime lifecycle subscriber "
            f"{contribution_id!r} failed while publishing {event.type.value!r}"
        )
        self.contribution_id = contribution_id
        self.event_type = event.type


class InMemoryRuntimeLifecycleSubscriberRegistry(RuntimeLifecycleSubscriberRegistry):
    """Collect unique boot-time lifecycle subscriber contributions.

    Duplicate identifiers fail during profile boot instead of permitting load
    order to silently replace an audit or progress consumer. ``snapshot`` is
    deterministic, allowing the runtime binding to freeze its local publisher.
    """

    def __init__(self) -> None:
        self._contributions: dict[str, RuntimeLifecycleSubscriberContribution] = {}

    def register(self, contribution: RuntimeLifecycleSubscriberContribution) -> None:
        _validate_contribution(contribution)
        if contribution.id in self._contributions:
            raise KeyError(
                "runtime_lifecycle_subscriber_registry: contribution "
                f"{contribution.id!r} already registered"
            )
        self._contributions[contribution.id] = contribution

    def snapshot(self) -> tuple[RuntimeLifecycleSubscriberContribution, ...]:
        """Return a deterministic frozen ordering by priority and identity."""

        return tuple(
            sorted(self._contributions.values(), key=lambda item: (item.priority, item.id))
        )


class CompositeRuntimeLifecyclePublisher(RuntimeLifecyclePublisher):
    """Publish each event to a frozen, ordered set of passive subscribers."""

    def __init__(
        self,
        contributions: Sequence[RuntimeLifecycleSubscriberContribution] = (),
        *,
        failure_mode: LifecyclePublisherFailureMode = LifecyclePublisherFailureMode.FAIL_OPEN,
    ) -> None:
        for contribution in contributions:
            _validate_contribution(contribution)
        self._contributions = tuple(
            sorted(contributions, key=lambda item: (item.priority, item.id))
        )
        self._failure_mode = failure_mode

    @property
    def contributions(self) -> tuple[RuntimeLifecycleSubscriberContribution, ...]:
        """Expose the frozen contribution snapshot for diagnostics and tests."""

        return self._contributions

    @property
    def failure_mode(self) -> LifecyclePublisherFailureMode:
        """Return the profile-selected publication failure policy."""

        return self._failure_mode

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        """Publish without allowing a subscriber to mutate another's input."""

        for contribution in self._contributions:
            try:
                await contribution.subscriber.publish(event)
            except Exception as exc:
                self._handle_failure(contribution, event=event, error=exc)

    def _handle_failure(
        self,
        contribution: RuntimeLifecycleSubscriberContribution,
        *,
        event: RuntimeLifecycleEvent,
        error: Exception,
    ) -> None:
        if self._failure_mode is LifecyclePublisherFailureMode.FAIL_CLOSED:
            raise RuntimeLifecyclePublisherError(contribution.id, event) from error
        _log.warning(
            "runtime_lifecycle_subscriber_failed",
            subscriber_id=contribution.id,
            subscriber_type=type(contribution.subscriber).__name__,
            lifecycle_event=event.type.value,
            trace_id=event.trace_id,
            exc_info=True,
        )


class NullRuntimeLifecyclePublisher(RuntimeLifecyclePublisher):
    """Explicit no-op publisher for focused tests and publication-free fixtures."""

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        del event


class StructuredLogRuntimeLifecycleSubscriber(RuntimeLifecycleSubscriber):
    """Default safe projection of lifecycle events to structured application logs."""

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        _log.info(
            "runtime_lifecycle",
            lifecycle_event=event.type.value,
            trace_id=event.trace_id,
            plan_ref=event.plan_ref,
            status=event.status.value,
            step=event.step,
            state_ref=event.state_ref,
            phase_cursor=event.phase_cursor,
            journal_sequence=event.journal_sequence,
            used_steps=event.budget.used_steps,
            max_steps=event.budget.max_steps,
        )


def _validate_contribution(contribution: RuntimeLifecycleSubscriberContribution) -> None:
    """Validate open plugin input before the neutral registry accepts it."""

    if not isinstance(contribution, RuntimeLifecycleSubscriberContribution):
        raise TypeError(
            "runtime lifecycle subscriber registry requires RuntimeLifecycleSubscriberContribution"
        )
    if not contribution.id.strip():
        raise ValueError("runtime lifecycle subscriber contribution id must not be empty")
    if not isinstance(contribution.subscriber, RuntimeLifecycleSubscriber):
        raise TypeError(
            "runtime lifecycle subscriber contribution must implement RuntimeLifecycleSubscriber"
        )


__all__ = [
    "CompositeRuntimeLifecyclePublisher",
    "InMemoryRuntimeLifecycleSubscriberRegistry",
    "LifecyclePublisherFailureMode",
    "NullRuntimeLifecyclePublisher",
    "RuntimeLifecyclePublisherError",
    "StructuredLogRuntimeLifecycleSubscriber",
]
