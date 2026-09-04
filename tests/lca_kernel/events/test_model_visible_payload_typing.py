"""ADR-0185 PR-1:SpineLlmRequestHeaderPayload + SpineLlmRequestHeaderAssistantPayload
的类型化与 yaml 注册。

守住 PR-1 验收点(ADR-0185 §5 PR-1):
- :func:`EventRegistry.load` 不抛。
- ``spine.llm.request.header`` 与 ``spine.llm.request.header.assistant``
  两个 category 解析到 :mod:`lca_kernel.events.payloads_model_visible`
  中的 typed payload 类。
- yaml ``fields:`` schema 与 typed payload 类字段一致。
- :class:`Category` 枚举含两个新成员且 :func:`default_plane` 映射到
  ``Plane.OBSERVABILITY``。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.event import Category, Plane, default_plane
from lca_kernel.events.payloads_model_visible import (
    SpineLlmRequestHeaderAssistantPayload,
    SpineLlmRequestHeaderPayload,
)
from lca_kernel.events.registry import EventRegistry


def _config_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "lca_kernel" / "events" / "config"


def test_registry_load_does_not_raise() -> None:
    """spine.yaml 装载不抛(包括新 typed payload 类的解析)。"""
    EventRegistry.load(_config_dir())


def test_request_header_category_resolves_to_typed_payload() -> None:
    """``spine.llm.request.header`` → :class:`SpineLlmRequestHeaderPayload`。

    此前为 :class:`SpineEventPayload` 壳 payload;PR-1 替换为 typed 类,
    由 :class:`lca.plugins.events.publishers.model_visible` (PR-2) 唯一构造。
    """
    registry = EventRegistry.load(_config_dir())
    spec = next(s for s in registry.specs if s.category == Category.SPINE_LLM_REQUEST_HEADER)
    assert spec.payload_class is SpineLlmRequestHeaderPayload


def test_assistant_category_resolves_to_typed_payload() -> None:
    """``spine.llm.request.header.assistant`` → :class:`SpineLlmRequestHeaderAssistantPayload`。

    新增 category;修复 Note ``2026-09-03-model-visible-incomplete-projection``
    第 1 BUG(assistant 输出未投影)。
    """
    registry = EventRegistry.load(_config_dir())
    spec = next(
        s for s in registry.specs if s.category == Category.SPINE_LLM_REQUEST_HEADER_ASSISTANT
    )
    assert spec.payload_class is SpineLlmRequestHeaderAssistantPayload


def test_request_header_yaml_fields_match_typed_payload() -> None:
    """``spine.llm.request.header`` yaml fields 与 typed payload 字段一一对应。"""
    registry = EventRegistry.load(_config_dir())
    spec = next(s for s in registry.specs if s.category == Category.SPINE_LLM_REQUEST_HEADER)
    expected = {
        "step_id": "str",
        "incarnation": "int",
        "config": "json",
        "system": "str",
        "tools": "json",
        "messages": "json",
        "manifest": "json",
        "reason": "str",
        "previous_header_digest": "str",
    }
    assert spec.fields == expected
    typed_field_names = set(SpineLlmRequestHeaderPayload.model_fields) - {"category"}
    assert set(expected) == typed_field_names


def test_assistant_yaml_fields_match_typed_payload() -> None:
    """``spine.llm.request.header.assistant`` yaml fields 与 typed payload 字段一一对应。"""
    registry = EventRegistry.load(_config_dir())
    spec = next(
        s for s in registry.specs if s.category == Category.SPINE_LLM_REQUEST_HEADER_ASSISTANT
    )
    expected = {
        "step_id": "str",
        "incarnation": "int",
        "assistant_content": "str",
        "tool_calls": "json",
        "finish_reason": "str",
        "usage": "json",
        "header_digest": "str",
    }
    assert spec.fields == expected
    typed_field_names = set(SpineLlmRequestHeaderAssistantPayload.model_fields) - {"category"}
    assert set(expected) == typed_field_names


def test_category_enum_has_new_member() -> None:
    """:class:`Category` 枚举含 ``SPINE_LLM_REQUEST_HEADER_ASSISTANT``。"""
    assert Category.SPINE_LLM_REQUEST_HEADER_ASSISTANT == "spine.llm.request.header.assistant"


def test_both_categories_map_to_observability_plane() -> None:
    """两类 model-visible 事件 → :attr:`Plane.OBSERVABILITY`(对齐 spine 同形)。"""
    assert default_plane(Category.SPINE_LLM_REQUEST_HEADER) is Plane.OBSERVABILITY
    assert default_plane(Category.SPINE_LLM_REQUEST_HEADER_ASSISTANT) is Plane.OBSERVABILITY


def test_payload_classes_inherit_event_payload() -> None:
    """typed payload 必须继承 :class:`EventPayload`(机制 ``_resolve_class`` 基类校验)。"""
    from lca.contracts.event import EventPayload

    assert issubclass(SpineLlmRequestHeaderPayload, EventPayload)
    assert issubclass(SpineLlmRequestHeaderAssistantPayload, EventPayload)


def test_payload_classes_are_frozen_and_forbid_extra() -> None:
    """typed payload 是 ``ConfigDict(extra="forbid", frozen=True)``(D3)。"""
    for cls in (SpineLlmRequestHeaderPayload, SpineLlmRequestHeaderAssistantPayload):
        assert cls.model_config["extra"] == "forbid"
        assert cls.model_config["frozen"] is True
