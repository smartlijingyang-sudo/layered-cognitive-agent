"""EventDescriptorRegistry 行为测试（ADR-0063 PR-7 source inversion）。"""

from __future__ import annotations

from lca.contracts.models.observability.event import (
    EventAudience,
    EventDescriptor,
    EventDurability,
    EventSensitivity,
)
from lca.contracts.models.observability.journal import LlmCallCompleted
from lca.infrastructure.observability.event_catalog import (
    EVENT_DESCRIPTOR_REGISTRY,
    descriptor_for,
    may_export_externally,
)
from lca.infrastructure.observability.event_descriptor_registry import (
    DuplicateEventDescriptorError,
    InMemoryEventDescriptorRegistry,
    UnknownEventDescriptorError,
)


def test_bootstrap_registers_builtin_descriptors() -> None:
    """build_default_registry() 应填充 49 个内置 EventDescriptor。"""
    descriptors = list(EVENT_DESCRIPTOR_REGISTRY)
    assert len(descriptors) >= 40, f"内置 descriptor 数量异常：{len(descriptors)}"


def test_descriptor_for_returns_typed_descriptor() -> None:
    descriptor = descriptor_for("LlmCallCompleted")
    assert descriptor.type_name == "LlmCallCompleted"
    assert descriptor.durability is EventDurability.REQUIRED
    assert descriptor.audience is EventAudience.OPERATOR
    assert descriptor.otel_kind == "generation"


def test_descriptor_for_accepts_event_instance() -> None:
    descriptor = descriptor_for(LlmCallCompleted(model="m"))
    assert descriptor.type_name == "LlmCallCompleted"


def test_descriptor_for_unknown_event_raises_keyerror() -> None:
    import pytest

    with pytest.raises(KeyError, match="UnknownEvent"):
        descriptor_for("UnknownEvent")


def test_may_export_externally_filters_restricted() -> None:
    assert may_export_externally("LlmCallCompleted") is True
    assert may_export_externally("ReasoningDelta") is False
    assert may_export_externally("ReasoningCompleted") is False


def test_registry_get_returns_none_for_missing() -> None:
    registry = InMemoryEventDescriptorRegistry()
    assert registry.get("DoesNotExist") is None


def test_registry_require_raises_for_missing() -> None:
    import pytest

    registry = InMemoryEventDescriptorRegistry()
    with pytest.raises(UnknownEventDescriptorError):
        registry.require("DoesNotExist")


def test_registry_register_rejects_duplicate_by_default() -> None:
    registry = InMemoryEventDescriptorRegistry()
    descriptor = EventDescriptor(
        type_name="CustomEvent",
        plane="structural",
        domain="event",
        emitter="test.module",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.OPERATOR,
        sensitivity=EventSensitivity.INTERNAL,
    )
    registry.register(descriptor)
    import pytest

    with pytest.raises(DuplicateEventDescriptorError):
        registry.register(descriptor)


def test_registry_register_replace_overwrites() -> None:
    registry = InMemoryEventDescriptorRegistry()
    first = EventDescriptor(
        type_name="CustomEvent",
        plane="structural",
        domain="event",
        emitter="first.module",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.OPERATOR,
        sensitivity=EventSensitivity.INTERNAL,
    )
    second = EventDescriptor(
        type_name="CustomEvent",
        plane="structural",
        domain="event",
        emitter="second.module",
        durability=EventDurability.REQUIRED,
        audience=EventAudience.OPERATOR,
        sensitivity=EventSensitivity.INTERNAL,
    )
    registry.register(first)
    registry.register(second, replace=True)
    assert registry.require("CustomEvent").emitter == "second.module"


def test_registry_payload_class_for() -> None:
    payload = descriptor_for("LlmCallCompleted").payload_class
    assert payload is LlmCallCompleted
    assert EVENT_DESCRIPTOR_REGISTRY.payload_class_for("LlmCallCompleted") is LlmCallCompleted


def test_registry_iterator_returns_all_descriptors() -> None:
    names = set(EVENT_DESCRIPTOR_REGISTRY.all_type_names())
    assert {"TeamRunStarted", "AgentRunStarted", "LlmCallCompleted", "ToolInvoked"} <= names


def test_seam_provides_registry() -> None:
    """seam_event_descriptor 模块导入即可，且 setup 是 cordis Plugin 对象。"""
    from lca.plugins.seam_definitions.observability import event_descriptor as mod

    assert hasattr(mod, "setup")
    # setup 在 @plugin 装饰后是 Plugin 对象，不是原函数
    plugin_obj = mod.setup
    meta = getattr(plugin_obj, "meta", {})
    assert meta.get("id") == "lca-event-descriptor-registry"
    assert "event_descriptor_registry" in meta.get("provides", [])
