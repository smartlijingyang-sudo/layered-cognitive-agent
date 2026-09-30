"""catalog 装载层（:mod:`lca_kernel.events.registry.catalog`）的聚焦测试。

覆盖 yaml → typed 事件描述的解析：``events`` 段产出 :class:`EventSpec`，
顶层 ``consumer_rules`` 段产出 :class:`_ConsumerRuleTokens` raw 形态；
观测目录 yaml（``lca.observability.*`` schema）与非事件 yaml 被跳过。
"""

from __future__ import annotations

from pathlib import Path

from lca.contracts.event import Category, Plane
from lca_kernel.events.registry.catalog import load_catalog


def test_load_catalog_returns_descriptors_and_rule_tokens(tmp_path: Path) -> None:
    """小型 yaml catalog → EventSpec 描述 + consumer rule tokens。"""
    (tmp_path / "catalog.yaml").write_text(
        """
consumer_rules:
  - prefix: "team."
    subscribers:
      - lca.plugins.events.sinks.spine_file_sink.sink.SpineFileSink
events:
  - category: team.delegation.cache_hit
    plane: lca.contracts.event.Plane.STRUCTURAL
    payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit
    publishers:
      - lca.loop.fact_gateway.DefaultFactGateway
    fields:
      trace: "true"
"""
    )
    specs, rules = load_catalog(tmp_path)
    assert len(specs) == 1
    assert len(rules) == 1
    spec = specs[0]
    assert spec.category == Category.TEAM_DELEGATION_CACHE_HIT
    assert spec.plane is Plane.STRUCTURAL
    assert spec.publishers_tokens == ("lca.loop.fact_gateway.DefaultFactGateway",)
    assert spec.subscribers_tokens == ()
    assert spec.fields == {"trace": "true"}
    assert rules[0].prefix == "team."
    assert rules[0].subscribers_tokens == (
        "lca.plugins.events.sinks.spine_file_sink.sink.SpineFileSink",
    )


def test_load_catalog_skips_observability_and_non_event_yaml(tmp_path: Path) -> None:
    """观测目录 yaml（lca.observability.* schema）与非事件 yaml 不产出 spec。"""
    (tmp_path / "observability.yaml").write_text(
        """
schema: lca.observability.spine
events:
  - category: spine.kernel.run.start
"""
    )
    (tmp_path / "not_events.yaml").write_text(
        """
some: other
config: true
"""
    )
    specs, rules = load_catalog(tmp_path)
    assert specs == []
    assert rules == []


def test_load_catalog_empty_dir_raises(tmp_path: Path) -> None:
    """目录下无 yaml → FileNotFoundError（与 EventRegistry.load 同语义）。"""
    try:
        load_catalog(tmp_path)
    except FileNotFoundError as exc:
        assert "事件配置 SSOT 目录为空" in str(exc)
    else:  # pragma: no cover - 失败分支必须抛
        raise AssertionError("load_catalog 空目录应抛 FileNotFoundError")


def test_load_catalog_sorts_yaml_files(tmp_path: Path) -> None:
    """多文件按路径排序加载，保证目录装载顺序确定。"""
    (tmp_path / "b.yaml").write_text(
        """
events:
  - category: spine.cognition.brain.perceive.start
    plane: lca.contracts.event.Plane.STRUCTURAL
    payload_class: lca_kernel.events.payloads.SpineEventPayload
"""
    )
    (tmp_path / "a.yaml").write_text(
        """
events:
  - category: team.delegation.cache_hit
    plane: lca.contracts.event.Plane.STRUCTURAL
    payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit
"""
    )
    specs, _ = load_catalog(tmp_path)
    assert [s.category for s in specs] == [
        Category.TEAM_DELEGATION_CACHE_HIT,
        Category("spine.cognition.brain.perceive.start"),
    ]
