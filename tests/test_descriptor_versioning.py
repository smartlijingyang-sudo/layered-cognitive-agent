"""EventDescriptor version / payload_schema_version(ADR-0065 L4 / PR-3)。

- descriptor.version 默认 1
- descriptor.payload_schema_version 默认 1
- 字段可读、可序列化、等价
"""

from __future__ import annotations

from dataclasses import asdict

from lca.contracts.models.observability.event import (
    EventAudience,
    EventDescriptor,
    EventDurability,
    EventPlane,
    EventSensitivity,
)


def test_default_version_is_one() -> None:
    d = EventDescriptor(
        type_name="TestEvent",
        plane=EventPlane.STRUCTURAL,
        domain="test",
        emitter="test",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.OPERATOR,
        sensitivity=EventSensitivity.INTERNAL,
    )
    assert d.version == 1
    assert d.payload_schema_version == 1


def test_custom_versions_are_stored() -> None:
    d = EventDescriptor(
        type_name="TestEvent",
        plane=EventPlane.STRUCTURAL,
        domain="test",
        emitter="test",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.OPERATOR,
        sensitivity=EventSensitivity.INTERNAL,
        version=3,
        payload_schema_version=2,
    )
    assert d.version == 3
    assert d.payload_schema_version == 2
    payload = asdict(d)
    assert payload["version"] == 3
    assert payload["payload_schema_version"] == 2


def test_descriptor_frozen_blocks_version_mutation() -> None:
    d = EventDescriptor(
        type_name="X",
        plane=EventPlane.STRUCTURAL,
        domain="x",
        emitter="x",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.OPERATOR,
        sensitivity=EventSensitivity.INTERNAL,
    )
    try:
        d.version = 999  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("EventDescriptor must be frozen")
