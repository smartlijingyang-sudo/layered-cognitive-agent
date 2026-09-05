"""spine.yaml 加载 + 鉴权矩阵 SSOT（ADR-0181 D3）。"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.event import Category
from lca_kernel.events.payloads import SpineEventPayload
from lca_kernel.events.registry import EventRegistry


def test_spine_yaml_loads_spine_events_after_pr6() -> None:
    """spine.yaml PR-6 后 + ADR-0185 PR-1 + loop cursor record_*: 101 + 7 = 108。

    删-when：spine.yaml 退化为单一 cognition 测试时（本测试断言的事件数）。

    ADR-0185 PR-1 新增 1 个 model-visible 类别（``spine.llm.request.header.assistant``）,
    替换 ``spine.llm.request.header`` shell entry 为 typed payload,替换不增数。
    loop cursor record_* + i17 self-observation 新增 7 个 spine 类别。
    """
    config_dir = Path(__file__).resolve().parents[3] / "lca_kernel" / "events" / "config"
    registry = EventRegistry.load(config_dir)
    spine_specs = [s for s in registry.specs if s.category.value.startswith("spine.")]
    assert len(spine_specs) == 108, (
        f"spine.yaml 应 108 个 spine 事件（101 + loop cursor/i17 7）；found {len(spine_specs)}"
    )
    spec = spine_specs[0]
    assert spec.category == Category("spine.cognition.brain.perceive.start")
    assert spec.payload_class is SpineEventPayload


def test_spine_publisher_resolved() -> None:
    """spine.yaml publishers 字段 → ReflectorClass type 对象。

    PR-5：yaml 改 id 形态后，``EventRegistry.load`` 缺 catalog → publishers
    解析为空。本测试改用 :func:`build_test_bus` 注入 catalog，与生产路径
    同形态。
    """
    from lca_kernel.events.test_catalog import build_test_bus

    bus = build_test_bus()
    cat = Category("spine.cognition.brain.perceive.start")
    pubs = bus.registry.publishers[cat]
    from lca.plugins.events.publishers.spine_reflector_cognition.plugin import (
        ReflectorClass,
    )

    assert ReflectorClass in pubs


def test_spine_subscribers_resolved() -> None:
    """spine.yaml consumer_rules 前缀规则 → 物化的订阅授权 type 集合。

    PR-5：catalog 注入后才解析；用 :func:`build_test_bus`。
    """
    from lca_kernel.events.test_catalog import build_test_bus

    bus = build_test_bus()
    cat = Category("spine.cognition.brain.perceive.start")
    subs = bus.registry.subscribers[cat]
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


def test_spine_consumer_rules_cover_all_categories() -> None:
    """顶层 consumer_rules：最少前缀规则覆盖全部 100 category。

    PR-5：catalog 注入后才解析；用 :func:`build_test_bus`。
    """
    from lca_kernel.events.test_catalog import build_test_bus

    bus = build_test_bus()
    registry = bus.registry
    assert {r.prefix for r in registry.consumer_rules} == {
        "spine.",
        "spine.cognition.brain.perceive.",
        "team.",
    }
    # perceive 子树命中两条规则：并集比兜底规则多 SpineStepTreeAccumulator
    from lca.plugins.events.subscribers.spine_step_tree_accumulator.subscriber import (
        SpineStepTreeAccumulator,
    )

    base = next(r.subscribers for r in registry.consumer_rules if r.prefix == "spine.")
    perceive = registry.subscribers[Category("spine.cognition.brain.perceive.start")]
    think = registry.subscribers[Category("spine.cognition.brain.think.start")]
    assert think == base
    assert perceive == base | {SpineStepTreeAccumulator}
