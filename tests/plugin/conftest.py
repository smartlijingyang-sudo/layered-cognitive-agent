"""共享测试装置 —— 美食广场的「施工工具箱」。

这里提供所有测试共用的 builder 函数和 pytest fixture。
每个 builder 都用美食广场的隐喻来命名，让测试代码读起来像在讲故事。

核心概念映射：

    美食广场概念          →   代码构造器               →   用途
    ─────────────────────────────────────────────────────────────
    开一个空档口          →   make_stall()              →   造一个空 PluginHandle
    写一份入驻申请        →   make_application()        →   造一个 PluginSpec
    美食广场管理处        →   make_plaza()              →   造一个 PluginHost
    档口与广场的交互窗口  →   make_service_window()     →   造一个 PluginContext
    招商手册的一条记录    →   make_lease()              →   造一个 PluginEntry
    模拟一个档口模块      →   make_stall_module()       →   造一个假 plugin module
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from lca.contracts.mechanisms.plugin import PluginConfig
from lca.layer0_infra.plugin.kernel import (
    PluginHandle,
    PluginHost,
    PluginSpec,
    PluginState,
)
from lca.layer0_infra.plugin.kernel._context import PluginContext
from lca.layer0_infra.plugin.loader._entry import PluginEntry
from lca.layer0_infra.plugin.loader._loader import Loader

# ── 建造「档口模块」：模拟一个有 name/inject/provides/apply 的插件 ──────


def make_stall_module(
    name: str,
    inject: tuple[str, ...] = (),
    provides: str | None = None,
    *,
    on_apply: Callable[[Any, Any], Any] | None = None,
    config_cls: type[PluginConfig] = PluginConfig,
    is_class: bool = False,
) -> Any:
    """开一个模拟档口。

    相当于造一个「有名字、声明了依赖、能提供某种服务、有开业流程」的插件模块。

    Args:
        name: 档口名称（插件 name）
        inject: 这个档口开业前必须就位的设备列表（依赖声明）
        provides: 这个档口向广场提供的设备/服务键
        on_apply: 开业时执行的操作（ctx, config）→ Any
        config_cls: 配置校验类（默认空配置）
        is_class: 是否是类形态的插件（Service 子类）
    """
    if is_class:

        class StallClass:
            pass

        StallClass.name = name
        StallClass.inject = inject
        StallClass.provides = provides
        StallClass.Config = config_cls
        if on_apply is not None:
            StallClass.apply = staticmethod(on_apply)
        else:
            StallClass.apply = staticmethod(lambda ctx, cfg: None)
        return StallClass

    class Module:
        pass

    mod = Module()
    mod.name = name
    mod.inject = inject
    mod.provides = provides
    mod.Config = config_cls

    def apply(ctx: Any, config: Any) -> Any:
        if on_apply is not None:
            return on_apply(ctx, config)

    mod.apply = apply
    return mod


# ── 建造「招商记录」：一条 YAML 对应的 PluginEntry ──────────────────


def make_lease(
    id: str,
    module: Any = None,
    *,
    config: dict[str, Any] | None = None,
    disabled: bool = False,
    inject: tuple[str, ...] | dict[str, Any] | None = None,
) -> PluginEntry:
    """写一份招商记录。

    相当于美食广场招商手册里的一行：
    「编号=id 的档口，卖的是 module 这门手艺，配置是 config，
    如果 disabled 就不让它开。」
    """
    return PluginEntry(
        id=id,
        module=module,
        config=config or {},
        disabled=disabled,
        inject=inject,
    )


# ── 建造「服务窗口」：PluginContext（档口与广场的交互界面）────────────


def make_service_window(
    *,
    entry_id: str = "test",
    injected: tuple[str, ...] = (),
    state: PluginState = PluginState.LOADING,
) -> PluginContext:
    """开一个服务窗口。

    这是档口与美食广场管理处的唯一交互界面。
    通过它，档口可以 mount 设备、require 设备、注册 effect、监听广播。

    Args:
        entry_id: 档口编号
        injected: 档口声明需要的设备列表
        state: 档口当前营业状态
    """
    host = PluginHost()
    handle = PluginHandle(
        entry_id=entry_id,
        spec=PluginSpec(name=entry_id, apply=lambda ctx, cfg: None),
        config={},
        injected=injected,
        state=state,
    )
    host.register_handle(handle)
    return PluginContext(host, handle)


# ── Pytest Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def plaza() -> PluginHost:
    """一个空的美食广场管理处。"""
    return PluginHost()


@pytest.fixture
def basic_stall() -> PluginHandle:
    """一个最简档口：无依赖、无服务提供、状态 PENDING。"""
    return PluginHandle(
        entry_id="basic-stall",
        spec=PluginSpec(name="basic-stall", apply=lambda ctx, cfg: None),
        config={},
        injected=(),
    )


@pytest.fixture
async def busy_plaza() -> PluginHost:
    """一个已经有两个档口在营业的美食广场。

    「饮料站」(provides 'drinks') → 无依赖，已开业
    「调酒师」(inject 'drinks', provides 'cocktails') → 依赖饮料站，已开业
    """
    drinks_mod = make_stall_module("drinks", provides="drinks")
    cocktails_mod = make_stall_module("cocktails", inject=("drinks",), provides="cocktails")
    tree = await Loader().load(
        [
            PluginEntry(id="drinks", module=drinks_mod, config={}),
            PluginEntry(id="cocktails", module=cocktails_mod, config={}),
        ]
    )
    return tree.host
