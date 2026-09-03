"""ADR-0180 试点：EventRegistry 加载测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from lca.contracts.event import Category, EventPayload, Plane
from lca_kernel.events.errors import UnknownCategoryError
from lca_kernel.events.mechanism import _DEFAULT_CONFIG_DIR
from lca_kernel.events.registry import EventRegistry, EventSpec


def test_default_registry_loads() -> None:
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    assert len(registry.specs) >= 1
    spec = registry.specs[0]
    assert spec.category == Category.TEAM_DELEGATION_CACHE_HIT
    assert spec.plane is Plane.STRUCTURAL
    assert spec.payload_class is not None
    assert issubclass(spec.payload_class, EventPayload)


def test_publishers_subscribers_resolved_to_types() -> None:
    registry = EventRegistry.load(_DEFAULT_CONFIG_DIR)
    cat = Category.TEAM_DELEGATION_CACHE_HIT
    # publishers / subscribers 是 typed Python type 对象（不是字符串）
    assert all(isinstance(p, type) for p in registry.publishers[cat])
    assert all(isinstance(s, type) for s in registry.subscribers[cat])


def test_registry_contract_fields_are_closed_set() -> None:
    """ADR-0183 PR-6：registry 契约字段闭集（死配置字段已删除，断言不回归）。"""
    assert set(EventRegistry.__dataclass_fields__) == {
        "specs",
        "publishers",
        "subscribers",
        "consumer_rules",
        "payload_by_category",
    }
    assert set(EventSpec.__dataclass_fields__) == {
        "category",
        "plane",
        "payload_class",
        "fields",
        "publishers",
        "subscribers",
    }


def test_unresolvable_payload_class_raises(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        """
events:
  - category: team.delegation.cache_hit
    plane: lca.contracts.event.Plane.STRUCTURAL
    payload_class: totally.nonexistent.module.MissingClass
"""
    )
    with pytest.raises(UnknownCategoryError, match=r"totally\.nonexistent\.module\.MissingClass"):
        EventRegistry.load(tmp_path)


def test_unresolvable_publisher_class_raises(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        """
events:
  - category: team.delegation.cache_hit
    plane: lca.contracts.event.Plane.STRUCTURAL
    payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit
    publishers:
      - totally.nonexistent.module.MissingPublisher
"""
    )
    with pytest.raises(UnknownCategoryError, match=r"MissingPublisher"):
        EventRegistry.load(tmp_path)


def test_unresolvable_plane_raises(tmp_path: Path) -> None:
    bad_yaml = tmp_path / "bad.yaml"
    bad_yaml.write_text(
        """
events:
  - category: team.delegation.cache_hit
    plane: lca.contracts.event.Plane.NOT_A_MEMBER
    payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit
"""
    )
    with pytest.raises(UnknownCategoryError, match=r"不存在"):
        EventRegistry.load(tmp_path)


def test_duplicate_category_raises(tmp_path: Path) -> None:
    dup_yaml = tmp_path / "dup.yaml"
    dup_yaml.write_text(
        """
events:
  - category: team.delegation.cache_hit
    plane: lca.contracts.event.Plane.STRUCTURAL
    payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit
  - category: team.delegation.cache_hit
    plane: lca.contracts.event.Plane.STRUCTURAL
    payload_class: lca_kernel.events.payloads.TeamDelegationCacheHit
"""
    )
    with pytest.raises(ValueError, match="多处登记"):
        EventRegistry.load(tmp_path)


def test_empty_config_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="事件配置 SSOT 目录为空"):
        EventRegistry.load(tmp_path)
