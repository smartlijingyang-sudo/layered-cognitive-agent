"""Tests for ADR-0187 PR-2 capability keys (assistant.* namespace).

钉 capability key 钉 (assistant.catalog / skill_overlay / evolve / jobs /
frontend_bridge) 已落进 ``lca.contracts.capabilities`` 登记表与
``CAPABILITIES_BY_KEY`` 自动索引；点分小写 + ``"assistant."`` 前缀 +
cardinality=``"one"`` 全部由本测试守住（PR-3+ 插件 ``provides`` 字段直接
import 这些常量）。
"""

from __future__ import annotations

from lca.contracts.capabilities import (
    ASSISTANT_CATALOG,
    ASSISTANT_EVOLVE,
    ASSISTANT_FRONTEND_BRIDGE,
    ASSISTANT_JOBS,
    ASSISTANT_SKILL_OVERLAY,
    CAPABILITIES_BY_KEY,
    Capability,
)

_ASSISTANT_CAPS = (
    ASSISTANT_CATALOG,
    ASSISTANT_SKILL_OVERLAY,
    ASSISTANT_EVOLVE,
    ASSISTANT_JOBS,
    ASSISTANT_FRONTEND_BRIDGE,
)


class TestAssistantCapabilityKeys:
    def test_keys_are_dot_lowercase(self) -> None:
        for cap in _ASSISTANT_CAPS:
            assert cap.key == cap.key.lower(), f"{cap.key!r} 包含非小写字符"
            assert " " not in cap.key
            assert cap.key.startswith("assistant."), f"{cap.key!r} 未带 assistant. 前缀"

    def test_expected_keys_present(self) -> None:
        for key in (
            "assistant.catalog",
            "assistant.skill_overlay",
            "assistant.evolve",
            "assistant.jobs",
            "assistant.frontend_bridge",
        ):
            assert key in CAPABILITIES_BY_KEY, f"capability {key!r} 未登记"

    def test_cardinality_is_one(self) -> None:
        """assistant.* capability 都是 ``"one"`` —— 拒绝并列多实现（§6 禁 God Catalog）。"""
        for cap in _ASSISTANT_CAPS:
            assert cap.cardinality == "one", (
                f"{cap.key!r} cardinality={cap.cardinality!r} 必须为 'one'"
            )

    def test_index_value_matches_constant(self) -> None:
        assert CAPABILITIES_BY_KEY["assistant.catalog"] is ASSISTANT_CATALOG
        assert CAPABILITIES_BY_KEY["assistant.skill_overlay"] is ASSISTANT_SKILL_OVERLAY
        assert CAPABILITIES_BY_KEY["assistant.evolve"] is ASSISTANT_EVOLVE
        assert CAPABILITIES_BY_KEY["assistant.jobs"] is ASSISTANT_JOBS
        assert CAPABILITIES_BY_KEY["assistant.frontend_bridge"] is ASSISTANT_FRONTEND_BRIDGE

    def test_no_duplicate_keys(self) -> None:
        """capabilities 模块 `_build_capability_index` 已守，但再加一次回归。"""
        seen: set[str] = set()
        for cap in _ASSISTANT_CAPS:
            assert cap.key not in seen, f"duplicate key {cap.key!r}"
            seen.add(cap.key)

    def test_keys_are_capability_instances(self) -> None:
        for cap in _ASSISTANT_CAPS:
            assert isinstance(cap, Capability)
