"""美食广场管理处测试 —— 服务台账管理、档口登记、所有权控制。

美食广场管理处（PluginHost）是整个广场的运营中枢：
- 维护「服务台账」：哪个档口提供了什么设备（provide / get_service / remove_service）
- 管理「档口登记簿」：谁入驻了、谁退租了（register_handle / unregister_handle）
- 控制所有权：每个档口只能操作自己的设备，不能乱动别人的（remove_owned_services）
- 运营广播系统：全场广播事件（events / EventBus）
"""

from __future__ import annotations

import pytest

from lca.layer0_infra.plugin.kernel import (
    PluginHandle,
    PluginHost,
    PluginSpec,
)
from lca.layer0_infra.plugin.kernel._events import EventBus
from lca.layer0_infra.plugin.kernel._service_record import ServiceRecord
from lca.layer0_infra.plugin.kernel._types import PluginError

# ── helpers ────────────────────────────────────────────────


def _make_handle(entry_id: str = "p1") -> PluginHandle:
    """创建一个虚拟档口的运营档案，用于测试管理处逻辑。"""
    return PluginHandle(
        entry_id=entry_id,
        spec=PluginSpec(name=entry_id, apply=lambda ctx, cfg: None),
        config={},
        injected=(),
    )


# ── Handle registration ────────────────────────────────────


class TestHandleRegistration:
    """档口登记簿测试 —— 入驻、退租、重复登记、只读查询。"""

    def test_register_and_unregister(self) -> None:
        """一个档口入驻后出现在登记簿上，退租后消失。"""
        host = PluginHost()
        handle = _make_handle("p1")
        host.register_handle(handle)
        assert "p1" in host.handles
        assert host.handles["p1"] is handle

        removed = host.unregister_handle("p1")
        assert removed is handle
        assert "p1" not in host.handles

    def test_unregister_missing_returns_none(self) -> None:
        """没入驻过的档口办退租——管理处直接返回 None，不会报错。"""
        host = PluginHost()
        assert host.unregister_handle("nope") is None

    def test_duplicate_entry_id_raises(self) -> None:
        """同一个档口号不能入驻两次——先到先得，后来者被拒绝。"""
        host = PluginHost()
        host.register_handle(_make_handle("dup"))
        with pytest.raises(PluginError, match="Duplicate"):
            host.register_handle(_make_handle("dup"))

    def test_handles_is_read_only_mapping(self) -> None:
        """登记簿只可查阅，不可篡改——返回的是只读映射。"""
        from collections.abc import Mapping

        host = PluginHost()
        host.register_handle(_make_handle("a"))
        handles = host.handles
        assert isinstance(handles, Mapping)
        assert "a" in handles


# ── Service table ──────────────────────────────────────────


class TestServiceTable:
    """服务台账测试 —— 设备登记、领取、注销、所有权约束。"""

    def test_provide_and_get(self) -> None:
        """档口在广场登记一台设备后，其他档口就能领取它。"""
        host = PluginHost()
        h = _make_handle("p1")
        host.register_handle(h)
        host.provide(h, "svc_a", 42)
        assert host.get_service("svc_a") == 42

    def test_remove_service(self) -> None:
        """设备注销后，台账上就查不到了。"""
        host = PluginHost()
        h = _make_handle()
        host.register_handle(h)
        host.provide(h, "svc", "val")
        host.remove_service("svc")
        assert host.get_service("svc") is None

    def test_remove_missing_is_noop(self) -> None:
        """注销一台不存在的设备——无事发生，不会炸。"""
        host = PluginHost()
        host.remove_service("ghost")  # should not raise

    def test_empty_name_raises(self) -> None:
        """设备名称不能为空——管理处拒绝没有名字的服务。"""
        host = PluginHost()
        h = _make_handle()
        host.register_handle(h)
        with pytest.raises(ValueError, match="empty"):
            host.provide(h, "", 42)

    def test_duplicate_by_different_owner_raises(self) -> None:
        """两个档口不能同时提供同一台设备——先到先得，后来的被拒绝。"""
        host = PluginHost()
        h1 = _make_handle("a")
        h2 = _make_handle("b")
        host.register_handle(h1)
        host.register_handle(h2)
        host.provide(h1, "shared", 1)
        with pytest.raises(PluginError, match="already provided"):
            host.provide(h2, "shared", 2)

    def test_same_owner_reprovide_updates_value(self) -> None:
        """同一个档口可以更新自己登记的设备的值——换个型号不算重复。"""
        host = PluginHost()
        h = _make_handle("p1")
        host.register_handle(h)
        host.provide(h, "svc", 1)
        host.provide(h, "svc", 2)
        assert host.get_service("svc") == 2

    def test_get_service_record(self) -> None:
        """查看设备的完整档案——包含设备值和归属档口编号。"""
        host = PluginHost()
        h = _make_handle()
        host.register_handle(h)
        host.provide(h, "svc", "v")
        rec = host.get_service_record("svc")
        assert rec is not None
        assert isinstance(rec, ServiceRecord)
        assert rec.value == "v"
        assert rec.owner_id == "p1"

    def test_get_service_record_missing(self) -> None:
        """查一台从未登记的设备档案——返回 None。"""
        host = PluginHost()
        assert host.get_service_record("nope") is None


# ── Service availability ───────────────────────────────────


class TestServiceAvailability:
    """设备可用性测试 —— 有些设备登记了但暂时不可用（比如正在维修）。"""

    def test_get_default_when_missing(self) -> None:
        """领取不存在的设备时，可以拿到默认值（或者 None）。"""
        host = PluginHost()
        assert host.get_service("nope") is None
        assert host.get_service("nope", "fallback") == "fallback"

    def test_respects_available_flag_true(self) -> None:
        """设备标记为可用时，正常领取。"""
        host = PluginHost()
        h = _make_handle()
        host.register_handle(h)
        host.provide(h, "svc", "val", check=lambda: True)
        assert host.get_service("svc") == "val"

    def test_respects_available_flag_false(self) -> None:
        """设备标记为不可用时，领取返回 None 或默认值——虽然台账上有记录。"""
        host = PluginHost()
        h = _make_handle()
        host.register_handle(h)
        host.provide(h, "svc", "val", check=lambda: False)
        assert host.get_service("svc") is None
        assert host.get_service("svc", "fb") == "fb"

    def test_record_still_visible_when_unavailable(self) -> None:
        """即使设备不可用，档案仍然可查——管理处知道它在那儿，只是现在不能借。"""
        host = PluginHost()
        h = _make_handle()
        host.register_handle(h)
        host.provide(h, "svc", "val", check=lambda: False)
        rec = host.get_service_record("svc")
        assert rec is not None
        assert rec.value == "val"
        assert rec.available is False


# ── Ownership ──────────────────────────────────────────────


class TestOwnership:
    """所有权控制测试 —— 每个档口只能清理自己的设备，不能动别人的。"""

    def test_remove_owned_only_removes_own(self) -> None:
        """档口退租时只带走自己的设备，其他档口的设备纹丝不动。"""
        host = PluginHost()
        h1 = _make_handle("a")
        h2 = _make_handle("b")
        host.register_handle(h1)
        host.register_handle(h2)
        host.provide(h1, "svc_a", 1)
        host.provide(h2, "svc_b", 2)

        removed = host.remove_owned_services(h1)
        assert removed == ["svc_a"]
        assert host.get_service("svc_a") is None
        assert host.get_service("svc_b") == 2

    def test_remove_owned_returns_all_names(self) -> None:
        """档口提供了多台设备时，退租清理返回所有设备名，台账全部清空。"""
        host = PluginHost()
        h = _make_handle("p1")
        host.register_handle(h)
        host.provide(h, "x", 1)
        host.provide(h, "y", 2)
        host.provide(h, "z", 3)
        removed = sorted(host.remove_owned_services(h))
        assert removed == ["x", "y", "z"]
        assert host.get_service("x") is None
        assert host.get_service("y") is None
        assert host.get_service("z") is None

    def test_remove_owned_empty_when_nothing_provided(self) -> None:
        """档口没提供过任何设备，退租时清理列表为空。"""
        host = PluginHost()
        h = _make_handle()
        host.register_handle(h)
        assert host.remove_owned_services(h) == []


# ── Event bus integration ─────────────────────────────────


class TestEventBusIntegration:
    """广场广播系统测试 —— 事件总线集成。"""

    def test_events_is_event_bus(self) -> None:
        """管理处配备了标准的广播系统。"""
        host = PluginHost()
        assert isinstance(host.events, EventBus)

    def test_events_on_and_emit(self) -> None:
        """档口订阅广播后，管理处播报时能收到消息。"""
        host = PluginHost()
        captured: list[int] = []

        async def _run() -> None:
            host.events.on("owner", "tick", lambda v: captured.append(v))
            await host.events.emit("tick", 42)

        import asyncio

        asyncio.run(_run())
        assert captured == [42]

    def test_builtins_dict_exists(self) -> None:
        """管理处内置了一个空的服务抽屉——留作特殊用途。"""
        host = PluginHost()
        assert isinstance(host.builtins, dict)
        assert len(host.builtins) == 0
