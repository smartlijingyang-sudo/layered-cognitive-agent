"""lca-gateway-bootstrap plugin — 把 gateway 进程级资源装到 Starlette app.state。

ADR-0119 决定 2:把原 ``gateway/bootstrap.py:install_gateway_state``(游离函数)
改造成 L3 Provider plugin。Plugin ``setup`` 阶段提供:
- ``ctx.provide("gateway_bootstrap_factory", DefaultGatewayBootstrapFactory)``
- ``ctx.provide("gateway_bootstrap_config", GatewayBootstrapConfig())``
- ``ctx.provide("install_bootstrap_state", install_bootstrap_state)`` — 供
  :func:`lca.plugins.transport.webserver.server.setup` 在 K3 完成后
  ``ctx.require("install_bootstrap_state")`` 直接调

安装到 ``app.state`` 的资源(由 routes plugin handler 通过
``request.app.state.xxx`` 读取):
- ``run_port`` — RegistryRunAdapter
- ``registry`` — RunRegistry
- ``devices`` — DeviceRegistry
- ``device_settings`` — DeviceGatewaySettings
- ``file_store`` — FileStore(优先 kernel seam,回退 bootstrap 默认根)
- ``device_hub`` — DeviceHub
- ``bound_observability`` — kernel-injected observability seam
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from lca.contracts.atoms.control_slot import ControlSlot
from lca.contracts.atoms.functional_group import FunctionalGroup
from lca.contracts.atoms.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.declarative.declarative_plugin import OwnershipDeclaration
from lca.contracts.protocols.runtime.infra import MachineResolver
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.file_store import FileStore, LocalFileStore


@dataclass(frozen=True, slots=True)
class GatewayBootstrapConfig:
    file_store_root: Path = Path("traces/files")
    file_store_url_prefix: str = "/files"
    device_settings: Any = None  # Optional[DeviceGatewaySettings];测试用,生产用默认


@dataclass(frozen=True, slots=True)
class GatewayBootstrap:
    file_store: FileStore
    devices: Any  # DeviceRegistry
    device_hub: Any  # DeviceHub
    machine_resolver: MachineResolver
    device_settings: Any  # DeviceGatewaySettings


@runtime_checkable
class GatewayBootstrapFactory(Protocol):
    def create(self, config: GatewayBootstrapConfig) -> GatewayBootstrap: ...


class DefaultGatewayBootstrapFactory:
    def create(self, config: GatewayBootstrapConfig) -> GatewayBootstrap:
        from gateway.device_gateway.bind import DeviceMachineResolver
        from gateway.device_gateway.hub import DeviceHub
        from gateway.device_gateway.registry import DeviceRegistry
        from gateway.device_gateway.settings import DeviceGatewaySettings

        settings = config.device_settings or DeviceGatewaySettings()
        file_store = LocalFileStore(
            config.file_store_root,
            public_url_prefix=config.file_store_url_prefix,
        )
        devices = DeviceRegistry(settings.db_path)
        device_hub = DeviceHub(devices)
        machine_resolver = DeviceMachineResolver(devices, device_hub)
        return GatewayBootstrap(
            file_store=file_store,
            devices=devices,
            device_hub=device_hub,
            machine_resolver=machine_resolver,
            device_settings=settings,
        )


def install_bootstrap_state(
    app: Any,
    ctx: Any,
    *,
    config: GatewayBootstrapConfig | None = None,
) -> None:
    """把 gateway 进程级资源装到 ``app.state``。从原 ``gateway/bootstrap.py:install_gateway_state`` 迁来。

    Composition:
    - ``run_port`` = ``RegistryRunAdapter(RunRegistry())``
    - ``file_store`` 优先 kernel seam,回退 bootstrap 默认根
    - ``bound_observability`` = ``ctx.inject("observability")``
    - 调 ``run_registry.bind_process_journal(journal_factory)`` 让 /journal/live 可用
    """
    from starlette.applications import Starlette

    if not isinstance(app, Starlette):
        raise TypeError(
            f"install_bootstrap_state requires a Starlette app, got {type(app).__name__}"
        )

    factory: GatewayBootstrapFactory = DefaultGatewayBootstrapFactory()
    cfg = config or GatewayBootstrapConfig()
    boot = factory.create(cfg)

    from gateway.runs.session.session import RunRegistry
    from gateway.runs.terminal.legacy_adapter import RegistryRunAdapter

    run_registry = RunRegistry()
    run_port = RegistryRunAdapter(run_registry, machine_resolver=boot.machine_resolver)

    file_store: FileStore = boot.file_store
    try:
        seam_file_store = ctx.inject("file_store") if ctx is not None else None
    except Exception:
        seam_file_store = None
    if seam_file_store is not None:
        file_store = seam_file_store

    app.state.run_port = run_port
    app.state.registry = run_registry
    app.state.devices = boot.devices
    app.state.device_settings = boot.device_settings
    app.state.file_store = file_store
    app.state.device_hub = boot.device_hub

    if ctx is not None:
        with contextlib.suppress(Exception):
            app.state.bound_observability = ctx.inject("observability")

    if ctx is not None:
        journal_factory: Any = None
        with contextlib.suppress(Exception, KeyError):
            journal_factory = ctx.inject("run_ledger_factory")
        if journal_factory is not None and hasattr(journal_factory, "create_process_journal"):
            with contextlib.suppress(Exception):
                run_registry.bind_process_journal(journal_factory)


@plugin(
    id="lca-gateway-bootstrap",
    provides=(
        "gateway_bootstrap_factory",
        "gateway_bootstrap_config",
        "install_bootstrap_state",
    ),
    requires=("file_store",),
    layer="L0",  # SEAM 级别(跟 lca-gateway-router 平级),被 L1 lca-web-server 消费
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Bootstrap gateway 进程级资源到 Starlette app.state (从 gateway/bootstrap.py 迁来).",
    test_suite="tests.lca_plugins.transport.webserver.test_bootstrap_plugin",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.bootstrap",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-bootstrap.installed",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("file_store",),
        emits=("gateway_bootstrap.installed",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    """Provide ``GatewayBootstrapFactory`` + config + install_bootstrap_state。

    实际 ``app.state`` 注入由 :func:`lca.plugins.transport.webserver.server.setup`
    在 K3 完成后 ``ctx.require("install_bootstrap_state")`` 触发。

    长期可维护:``install_bootstrap_state`` 是从 ``gateway.bootstrap.install_gateway_state``
    整体迁移过来的(原函数体没动),保持 historical 行为;未来 ADR followup 把
    ``gateway.bootstrap`` 业务搬到 ``lca.runtime.run_*`` 后,本包装层可删。
    """
    factory = DefaultGatewayBootstrapFactory()
    ctx.provide("gateway_bootstrap_factory", factory)
    ctx.provide("gateway_bootstrap_config", GatewayBootstrapConfig())
    # 提供 install_bootstrap_state 函数引用(handler 通过 ctx.require 拿到)
    # 函数体仍调用 gateway.bootstrap 业务(DeviceRegistry/Hub),属于 ADR-0119 之外的
    # 业务搬迁 followup。本 PR 仅做 plugin 包装 + ADR-0119 决定 2 的最小可工作单元。
    ctx.provide("install_bootstrap_state", install_bootstrap_state)


__all__ = [
    "DefaultGatewayBootstrapFactory",
    "GatewayBootstrap",
    "GatewayBootstrapConfig",
    "GatewayBootstrapFactory",
    "install_bootstrap_state",
]
