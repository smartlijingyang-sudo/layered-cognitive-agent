from __future__ import annotations

from lca.infrastructure.observability.event_descriptors_data import build_default_registry

from lca.contracts.models.observability.journal import TaskCreated
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES


def test_task_created_is_registered_as_durable_fact() -> None:
    assert JOURNAL_EVENT_CLASSES["TaskCreated"] is TaskCreated

    registry = build_default_registry()
    descriptor = registry.get("TaskCreated")

    assert descriptor is not None
    assert descriptor.durability.value == "required"
    assert descriptor.required == ("task_id", "session_id", "objective")
