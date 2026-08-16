"""
能力系统集成——CapabilityHub（公共服务台）+ Seam 三角色验证 + Plugin 协同。

美食广场设有一个「公共服务台」(CapabilityHub)，所有基础能力——大模型接口、
推理引擎、记忆存储等——都挂载在上面，供各个档口随时领取。

本模块验证三件事：
1. **公共服务台本身**：挂载、领取、查找、属性访问、重复挂载报错、空键报错
2. **能力三角验证**(Seam)：每个能力必须有 Definition（定义）、Provider（提供者）、
   Consumer（消费者）三个角色，缺一不可
3. **Plugin 与能力系统的协同**：档口开业时通过 ctx.require 从服务台领取能力
"""

from __future__ import annotations

from typing import Any

import pytest

from lca.contracts.mechanisms.capability import (
    REQUIRED_SEAM_KEYS,
    MissingCapabilityError,
)
from lca.contracts.mechanisms.seam import (
    SeamRegistry,
    SeamRole,
    consume,
    require_complete,
)
from lca.layer0_infra.capability.hub import CapabilityHub
from lca.layer4_app.capability_boot import (
    boot_capabilities,
)

# ── Test 1: CapabilityHub basic operations ───────────────────


def test_capability_hub_mount_require_get_keys_attr() -> None:
    """公共服务台的完整操作手册：挂载服务 → 领取 → 查找 → 列出所有服务 → 属性访问 →
    各种报错场景（缺失、重复挂载、空键）。

    就像服务台的工作流程：
    - 把服务挂上架子（mount）
    - 档口来领取（require），领不到就报错（MissingCapabilityError）
    - 温和地查找（get），找不到只返回 None 不报错
    - 查看架子上都有什么（keys）
    - 用名字直接拿（属性访问），不存在的名字报 AttributeError
    - 同一个位置不能放两样东西（重复挂载报 RuntimeError）
    - 空标签的服务不允许上架（空键报 ValueError）
    """
    hub = CapabilityHub()

    # Mount and require
    svc = {"name": "test-service"}
    hub.mount("my_key", svc)
    assert hub.require("my_key") is svc

    # get returns None for missing
    assert hub.get("nonexistent") is None

    # keys lists all mounted
    hub.mount("other_key", "other_value")
    assert set(hub.keys()) == {"my_key", "other_key"}

    # Attribute access works
    assert hub.my_key is svc
    assert hub.other_key == "other_value"

    # Missing capability via attribute raises AttributeError
    with pytest.raises(AttributeError):
        _ = hub.missing_key

    # Require missing raises MissingCapabilityError
    with pytest.raises(MissingCapabilityError):
        hub.require("missing_key")

    # Double mount raises
    with pytest.raises(RuntimeError, match="already mounted"):
        hub.mount("my_key", "another_value")

    # Empty key raises
    with pytest.raises(ValueError, match="empty"):
        hub.mount("", "value")


# ── Test 2: Seam catalog completeness ────────────────────────


def test_seam_catalog_all_required_keys_have_three_roles() -> None:
    """能力三角验证：为每个 REQUIRED_SEAM_KEY 注册 Definition、Provider、Consumer 三个角色
    → 全部完整 → require_complete 顺利通过。

    美食广场规定：每项核心能力必须有「规格书」（Definition）、「谁来干」（Provider）、
    「谁来用」（Consumer）三方。这里我们为每个能力键都凑齐三个角色，
    然后调用 require_complete 做全面体检——全部合格。
    """
    # Use a fresh registry to avoid polluting global state
    registry = SeamRegistry()

    # Register a minimal catalog for all seam keys
    for key in REQUIRED_SEAM_KEYS:
        registry.register(type(f"Def_{key.value}", (), {}), key.value, SeamRole.DEFINITION)
        registry.register(type(f"Prov_{key.value}", (), {}), key.value, SeamRole.PROVIDER)
        registry.register(type(f"Cons_{key.value}", (), {}), key.value, SeamRole.CONSUMER)

    # All complete
    for key in REQUIRED_SEAM_KEYS:
        assert registry.is_complete(key.value), f"seam {key.value} should be complete"

    # require_complete passes
    require_complete(*(key.value for key in REQUIRED_SEAM_KEYS), registry=registry)


def test_seam_catalog_incomplete_raises() -> None:
    """能力三角缺失：只注册了 Definition 和 Provider，缺了 Consumer → require_complete 报错。

    一个档口有规格书、有供应商，但没人来用——这不算完整的能力配置。
    require_complete 会立刻指出：你的三角缺了一角！
    """
    registry = SeamRegistry()
    registry.register(type("Def", (), {}), "llm", SeamRole.DEFINITION)
    registry.register(type("Prov", (), {}), "llm", SeamRole.PROVIDER)
    # Missing CONSUMER

    from lca.contracts.mechanisms.seam import IncompleteSeamError

    with pytest.raises(IncompleteSeamError):
        require_complete("llm", registry=registry)


# ── Test 3: Boot integration ─────────────────────────────────


def test_boot_capabilities_returns_hub_with_all_keys() -> None:
    """一键开业：boot_capabilities() 返回的服务台上，每个 REQUIRED_SEAM_KEY 都已挂载好。

    物业经理按下「一键开业」按钮，所有核心能力自动挂上服务台。
    我们逐个检查：每个能力键都不是空的——开业成功。
    """
    hub = boot_capabilities()
    for key in REQUIRED_SEAM_KEYS:
        assert hub.get(key.value) is not None, f"key {key.value} not mounted"


# ── Test 4: consume gate with real catalog ───────────────────


def test_consume_gate_registered_consumer_passes() -> None:
    """消费者准入验证：注册过的消费者能领取服务，未注册的消费者被拒之门外。

    美食广场的安保系统：MyConsumer 是登记在册的合法消费者，
    它可以顺利通过 consume 关卡领取 llm 服务。
    但 Stranger（未登记的陌生人）来领服务时——保安直接拦住。
    """
    registry = SeamRegistry()

    class MyDefinition:
        pass

    class MyProvider:
        pass

    class MyConsumer:
        pass

    class Stranger:
        pass

    registry.register(MyDefinition, "llm", SeamRole.DEFINITION)
    registry.register(MyProvider, "llm", SeamRole.PROVIDER)
    registry.register(MyConsumer, "llm", SeamRole.CONSUMER)

    provider_instance = MyProvider()

    # Registered consumer passes
    result = consume("llm", provider_instance, MyConsumer, registry=registry)
    assert result is provider_instance

    # Unregistered consumer rejected
    from lca.contracts.mechanisms.seam import UnauthorizedConsumerError

    with pytest.raises(UnauthorizedConsumerError):
        consume("llm", provider_instance, Stranger, registry=registry)


def test_consume_no_consumers_registered_passes_through() -> None:
    """宽松模式：某个能力还没有注册任何消费者 → consume 放行，不做阻拦。

    如果一项能力还没有人来领用，系统不会死板地要求「必须有人来领」——
    它只是安静地放行。就像一家新店还没客人，门开着，随时等客来。
    """
    registry = SeamRegistry()
    registry.register(type("Def", (), {}), "llm", SeamRole.DEFINITION)

    provider = "some_provider"
    result = consume("llm", provider, str, registry=registry)
    assert result is provider


# ── Test 5: Plugin system + capability system interop ────────


@pytest.mark.asyncio
async def test_plugin_system_capability_system_interop() -> None:
    """公共服务台与档口系统的完美配合：
    把 LLM Definition 挂上服务台 → 档口通过 ctx.require 领取 Definition
    → Provider 把自己注册到 Definition 上。

    这是整个美食广场的「终极验证」：
    公共服务台(CapabilityHub)挂着一份 LLM 规格书(Definition)。
    一个 Provider 档口开业时把规格书挂到 PluginHost 的服务表上。
    一个 Reasoner 档口开业时通过 ctx.require("llm") 领取规格书，
    然后把自己作为 Provider 注册到规格书上——完成了能力三角的最后一环。
    """
    from lca.layer0_infra.plugin.kernel import (
        PluginHandle,
        PluginHost,
        PluginSpec,
        PluginState,
        reconcile,
    )

    # Set up CapabilityHub with a mock LLM Definition
    hub = CapabilityHub()
    mock_llm_def = {"type": "llm_definition", "providers": {}}
    hub.mount("llm", mock_llm_def)

    # Create a plugin that accesses llm via ctx.require
    def plugin_apply(ctx: Any, cfg: Any) -> None:
        llm_def = ctx.require("llm")
        # Plugin registers itself as a provider on the Definition
        llm_def["providers"]["mock"] = {"adapter": "mock_adapter"}
        ctx.mount("my_reasoner", {"uses": llm_def})

    host = PluginHost()
    spec = PluginSpec(
        name="reasoner_plugin",
        apply=plugin_apply,
        inject=("llm",),
        provides="my_reasoner",
    )

    # Pre-mount 'llm' in the plugin host so the dependency is met
    provider_handle = PluginHandle(
        entry_id="_llm_provider",
        spec=PluginSpec(name="_llm_provider", apply=lambda ctx, cfg: None, provides="llm"),
        config={},
        injected=(),
    )
    host.register_handle(provider_handle)

    # Manually mount the llm service before reconcile

    # We need 'llm' to be in the service table for the reasoner plugin.
    # Use a provider plugin that mounts the CapabilityHub's llm.
    def mount_llm(ctx: Any, cfg: Any) -> None:
        ctx.mount("llm", mock_llm_def)

    provider_handle.spec = PluginSpec(name="_llm_provider", apply=mount_llm, provides="llm")

    # Now register the reasoner plugin
    reasoner_handle = PluginHandle(
        entry_id="reasoner_plugin",
        spec=spec,
        config={},
        injected=("llm",),
    )
    host.register_handle(reasoner_handle)

    await reconcile(host)

    assert provider_handle.state is PluginState.ACTIVE
    assert reasoner_handle.state is PluginState.ACTIVE

    # Verify the provider was registered on the Definition via the plugin
    assert "mock" in mock_llm_def["providers"]
    assert mock_llm_def["providers"]["mock"]["adapter"] == "mock_adapter"

    # Verify the reasoner service was mounted
    reasoner_svc = host.get_service("my_reasoner")
    assert reasoner_svc is not None
    assert reasoner_svc["uses"] is mock_llm_def
