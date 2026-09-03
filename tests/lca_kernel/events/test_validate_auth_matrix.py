"""ADR-0180 D3：EventMechanism.validate_auth_matrix 盖章 4 测试。

plugin manifest 鉴权声明 vs yaml SSOT 互校验：
- event_publishes 内每个 category 必须在 yaml publishers 白名单
  内对应 plugin class 一致
- event_subscribes 同理
- 不匹配 → AuthMatrixMismatchError

plugin_id 必须是 plugin class 全路径，与 yaml 中 publishers/subscribers
解析后的 class 全路径对齐（不接短 plugin_id 字符串）。
"""

from __future__ import annotations

import pytest

from lca.contracts.event import Category
from lca_kernel.events import EventMechanism
from lca_kernel.events.errors import AuthMatrixMismatchError
from lca_kernel.events.payloads import EventPluginSpec


def _delegation_cache_path() -> str:
    return "lca.plugins.events.publishers.delegation_cache.plugin.DelegationCachePlugin"


def _journal_sink_path() -> str:
    return "lca.plugins.events.sinks.journal.sink.JournalSink"


def test_validate_auth_matrix_pass(mechanism: EventMechanism) -> None:
    """合法 spec：EventMechanism.validate_auth_matrix 应通过。"""
    spec = EventPluginSpec(
        plugin_id=_delegation_cache_path(),
        event_publishes=frozenset({Category.TEAM_DELEGATION_CACHE_HIT}),
    )
    # 不抛错即为通过
    mechanism.validate_auth_matrix([spec])


def test_validate_auth_matrix_empty_ok(mechanism: EventMechanism) -> None:
    """空 spec 集合：no-op 通过。"""
    mechanism.validate_auth_matrix([])


def test_validate_auth_matrix_publish_mismatch(mechanism: EventMechanism) -> None:
    """plugin class 不在 yaml publishers 白名单 → raise AuthMatrixMismatchError。"""
    spec = EventPluginSpec(
        plugin_id="some.rogue.plugin.Path",   # 不在 yaml publishers
        event_publishes=frozenset({Category.TEAM_DELEGATION_CACHE_HIT}),
    )
    with pytest.raises(AuthMatrixMismatchError) as exc_info:
        mechanism.validate_auth_matrix([spec])
    assert exc_info.value.plugin_id == "some.rogue.plugin.Path"
    assert Category.TEAM_DELEGATION_CACHE_HIT.value in exc_info.value.missing_publish


def test_validate_auth_matrix_subscribe_mismatch(
    mechanism: EventMechanism,
) -> None:
    """plugin class 不在 yaml subscribers 白名单 → raise AuthMatrixMismatchError。"""
    spec = EventPluginSpec(
        plugin_id="some.rogue.subscriber.Path",
        event_subscribes=frozenset({Category.TEAM_DELEGATION_CACHE_HIT}),
    )
    with pytest.raises(AuthMatrixMismatchError) as exc_info:
        mechanism.validate_auth_matrix([spec])
    assert exc_info.value.plugin_id == "some.rogue.subscriber.Path"
    assert Category.TEAM_DELEGATION_CACHE_HIT.value in exc_info.value.missing_subscribe


def test_validate_auth_matrix_both_mismatch(mechanism: EventMechanism) -> None:
    """publish + subscribe 都未授权 → raise，两侧都填充。"""
    spec = EventPluginSpec(
        plugin_id="some.rogue.both.Path",
        event_publishes=frozenset({Category.TEAM_DELEGATION_CACHE_HIT}),
        event_subscribes=frozenset({Category.TEAM_DELEGATION_CACHE_HIT}),
    )
    with pytest.raises(AuthMatrixMismatchError) as exc_info:
        mechanism.validate_auth_matrix([spec])
    assert exc_info.value.missing_publish
    assert exc_info.value.missing_subscribe


def test_validate_auth_matrix_journal_sink_passes(
    mechanism: EventMechanism,
) -> None:
    """JournalSink 已在 yaml subscribers 白名单 → subscribe 校验通过。"""
    spec = EventPluginSpec(
        plugin_id=_journal_sink_path(),
        event_subscribes=frozenset({Category.TEAM_DELEGATION_CACHE_HIT}),
    )
    mechanism.validate_auth_matrix([spec])


def test_event_plugin_spec_to_dict_roundtrip() -> None:
    """EventPluginSpec.to_dict 形态：plugin_id + 列表化 categories。"""
    spec = EventPluginSpec(
        plugin_id="x.Y.Z",
        event_publishes=frozenset({Category.TEAM_DELEGATION_CACHE_HIT}),
    )
    d = spec.to_dict()
    assert d["plugin_id"] == "x.Y.Z"
    assert d["event_publishes"] == [Category.TEAM_DELEGATION_CACHE_HIT.value]
    assert d["event_subscribes"] == []
