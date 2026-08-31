"""EventDescriptorRegistry 装配 + ambient 解析回归测试（ADR-0065 L4 收尾）。

覆盖三条路径：
1. **ambient ContextVar 优先**——``bind_descriptors`` 后 ``descriptor_for``
   解析到的是绑定的 registry，而非 module fallback。
2. **fallback 兜底**——未 boot 时 ``descriptor_for`` 走 module 懒加载。
3. **RunStore 显式注册**——传入 ``descriptor_registry`` 后 ``_apply_policy``
   用它查描述符（自定义描述符可见，未登记则 fail-fast）。
4. **嵌套不泄漏**——``bind_descriptors`` 嵌套不污染外层 ambient。
"""

from __future__ import annotations

import pytest
from lca.infrastructure.observability.events.event_catalog import descriptor_for
from lca.infrastructure.observability.events.event_descriptor_env import (
    bind_descriptors,
    current_descriptors,
)
from lca.infrastructure.observability.events.event_descriptor_registry import (
    InMemoryEventDescriptorRegistry,
)

from lca.contracts.models.observability.journal import LlmCallCompleted


@pytest.fixture
def fresh_registry() -> InMemoryEventDescriptorRegistry:
    """空 registry；测试用例可按需 register。"""
    return InMemoryEventDescriptorRegistry()


def test_ambient_registry_overrides_fallback(
    fresh_registry: InMemoryEventDescriptorRegistry,
) -> None:
    """bind_descriptors 后 ambient 优先。"""
    fresh_registry.register(_make_descriptor("LlmCallCompleted"), replace=False)
    assert current_descriptors() is None
    with bind_descriptors(fresh_registry):
        descriptor = descriptor_for(LlmCallCompleted(model="m"))
        assert descriptor.type_name == "LlmCallCompleted"
        assert current_descriptors() is fresh_registry
    assert current_descriptors() is None


def test_fallback_used_when_no_ambient() -> None:
    """无 ambient 时 descriptor_for 走 module fallback（49 个内置）。"""
    descriptor = descriptor_for("LlmCallCompleted")
    assert descriptor.type_name == "LlmCallCompleted"
    # fallback 必须能找到所有内置事件类型
    assert descriptor_for("AgentRunStarted").type_name == "AgentRunStarted"
    assert descriptor_for("ToolInvoked").type_name == "ToolInvoked"


def test_nested_bind_does_not_leak() -> None:
    """嵌套 bind_descriptors 退出后不污染外层 ambient。"""
    inner = InMemoryEventDescriptorRegistry()
    outer = InMemoryEventDescriptorRegistry()
    with bind_descriptors(outer):
        assert current_descriptors() is outer
        with bind_descriptors(inner):
            assert current_descriptors() is inner
        assert current_descriptors() is outer
    assert current_descriptors() is None


def test_run_store_uses_injected_registry(
    fresh_registry: InMemoryEventDescriptorRegistry,
) -> None:
    """RunStore.__init__ 显式 registry 走 self._descriptor_registry 路径。"""
    from lca.infrastructure.observability.journal.engine.engine import RunStore

    fresh_registry.register(_make_descriptor("LlmCallCompleted"), replace=False)
    store = RunStore(descriptor_registry=fresh_registry)
    assert store._descriptor_registry is fresh_registry

    # append 走 _apply_policy → fresh_registry.require(LlmCallCompleted)
    stamped = store.append(LlmCallCompleted(model="test", ok=True))
    assert stamped.seq == 1
    assert stamped.event_type == "LlmCallCompleted"


def test_run_store_falls_back_when_no_registry() -> None:
    """不传 registry → 走 descriptor_for()（ambient 或 module 兜底）。"""
    from lca.infrastructure.observability.journal.engine.engine import RunStore

    store = RunStore()  # descriptor_registry 默认 None
    assert store._descriptor_registry is None
    stamped = store.append(LlmCallCompleted(model="m", ok=True))
    assert stamped.seq == 1


def test_custom_descriptor_visible_only_in_bound_scope(
    fresh_registry: InMemoryEventDescriptorRegistry,
) -> None:
    """ambient registry 注入的自定义描述符在 scope 内可见；scope 外找不到。"""
    from lca.contracts.models.observability.event import EventDescriptor

    custom_descriptor = EventDescriptor(
        type_name="CustomPluginEvent",
        plane="surface",  # type: ignore[arg-type]
        domain="custom",
        emitter="test",
        durability="required",
        audience="operator",
        sensitivity="internal",
    )
    fresh_registry.register(custom_descriptor, replace=False)

    with bind_descriptors(fresh_registry):
        # 在 ambient scope 内能找到
        descriptor = descriptor_for("CustomPluginEvent")
        assert descriptor.emitter == "test"

    # 退出 scope 后 ambient registry 不再生效 → fallback 找不到 → KeyError
    with pytest.raises(KeyError, match="未登记的运行事件描述符"):
        descriptor_for("CustomPluginEvent")


def _make_descriptor(type_name: str):
    """构造一个测试用的 EventDescriptor（type_name 仅用作标识）。"""
    from lca.contracts.models.observability.event import EventDescriptor

    return EventDescriptor(
        type_name=type_name,
        plane="structural",  # type: ignore[arg-type]
        domain="test",
        emitter="test",
        durability="required",
        audience="operator",
        sensitivity="internal",
    )
