"""spine.yaml 加载 + 鉴权矩阵 SSOT（ADR-0181 D3）。"""
from __future__ import annotations

from pathlib import Path

from lca.contracts.event import Category
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.registry import EventRegistry


def test_spine_yaml_loads_spine_events_after_pr5() -> None:
    """spine.yaml PR-5 后：PR-4 48 + PR-5 24 = 72。

    删-when：spine.yaml 退化为单一 cognition 测试时（本测试断言的事件数）。
    """
    config_dir = Path(__file__).resolve().parents[3] / "lca_kernel" / "events" / "config"
    registry = EventRegistry.load(config_dir)
    spine_specs = [s for s in registry.specs if s.category.value.startswith("spine.")]
    assert len(spine_specs) == 72, f"spine.yaml PR-5 应 72 个事件（PR-4 48 + writable 7 + phase 13 + phase_graph 4）；found {len(spine_specs)}"
    spec = spine_specs[0]
    assert spec.category == Category("spine.cognition.brain.perceive.start")
    assert spec.payload_class is SpineEventPayload


def test_spine_publisher_resolved() -> None:
    """spine.yaml publishers 字段 → ReflectorClass type 对象。"""
    config_dir = Path(__file__).resolve().parents[3] / "lca_kernel" / "events" / "config"
    registry = EventRegistry.load(config_dir)
    cat = Category("spine.cognition.brain.perceive.start")
    pubs = registry.publishers[cat]
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    assert ReflectorClass in pubs


def test_spine_subscribers_resolved() -> None:
    """spine.yaml subscribers 字段 → sink + subscriber plugin type 对象。"""
    config_dir = Path(__file__).resolve().parents[3] / "lca_kernel" / "events" / "config"
    registry = EventRegistry.load(config_dir)
    cat = Category("spine.cognition.brain.perceive.start")
    subs = registry.subscribers[cat]
    from lca.plugins.events.sinks.spine_chain_sink.sink import SpineChainSink
    from lca.plugins.events.subscribers.console_projector.subscriber import (
        ConsoleProjectorSubscriber,
    )
    from lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber import (
        SpineStepTreeAccumulator,
    )

    assert SpineChainSink in subs
    assert SpineStepTreeAccumulator in subs
    assert ConsoleProjectorSubscriber in subs
