"""Gateway startup infrastructure composition.

This module owns application-process infrastructure that must exist before the
Profile lifespan starts.  It deliberately has no module-level resource
singletons: every ``create_app`` call receives one explicit bootstrap product.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from gateway.device_gateway.bind import DeviceMachineResolver
from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.registry import DeviceRegistry
from gateway.device_gateway.settings import DeviceGatewaySettings
from lca.contracts.protocols.runtime.infra import MachineResolver
from lca.infrastructure.file_store import FileStore, LocalFileStore


@dataclass(frozen=True, slots=True)
class GatewayBootstrapConfig:
    """Concrete locations and URL policy for Gateway-owned infrastructure."""

    file_store_root: Path = Path("traces/files")
    file_store_url_prefix: str = "/files"
    device_settings: DeviceGatewaySettings | None = None


@dataclass(frozen=True, slots=True)
class GatewayBootstrap:
    """Explicit ownership bundle installed on one Starlette application."""

    file_store: FileStore
    devices: DeviceRegistry
    device_hub: DeviceHub
    machine_resolver: MachineResolver
    device_settings: DeviceGatewaySettings


@runtime_checkable
class GatewayBootstrapFactory(Protocol):
    """Create the application-scoped infrastructure used by Gateway routes."""

    def create(self, config: GatewayBootstrapConfig) -> GatewayBootstrap: ...


class DefaultGatewayBootstrapFactory(GatewayBootstrapFactory):
    """Filesystem and SQLite default for local Gateway deployment."""

    def create(self, config: GatewayBootstrapConfig) -> GatewayBootstrap:
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


def install_gateway_state(
    app: Any, ctx: Any, *, config: GatewayBootstrapConfig | None = None
) -> None:
    """Populate ``app.state.{run_port, file_store, devices, device_settings, registry}``.

    PR-7 (本批):PR-5 thin factory refactor 删掉 module-level 单例后,忘记把
    这些 gateway-side singletons 装回 ``app.state``,导致 ``/health``、
    ``/runs``、``/journal/live`` 等所有读 ``request.app.state.run_port``
    的路由 500。本函数是 PR-5 commit message 承诺「全替换在 ADR-0118」
    的兑现 —— 但实际触发是本批后端启动回归报告。

    Composition
    -----------
    - ``device_settings`` 来自 ``DeviceGatewaySettings()`` 默认,或
      ``config.device_settings`` 覆盖(测试用);
    - ``run_port`` 来自 ``RegistryRunAdapter(RunRegistry())`` —— 与旧
      ``gateway.app._registry`` 行为一致;
    - ``file_store`` 优先用 plugin 树提供的 ``file_store`` seam
      (kernel 注入),回退到 ``LocalFileStore(config.file_store_root)``。

    Parameters
    ----------
    app:
        Starlette application 实例;``app.state`` 被 mutate。
    ctx:
        Booted cordis Context;用于 inject 已注册的 seam。
    config:
        可选 ``GatewayBootstrapConfig``;为 None 时用默认 ``DefaultGatewayBootstrapFactory``。
    """
    from starlette.applications import Starlette

    if not isinstance(app, Starlette):
        raise TypeError(f"install_gateway_state requires a Starlette app, got {type(app).__name__}")

    factory: GatewayBootstrapFactory = DefaultGatewayBootstrapFactory()
    cfg = config or GatewayBootstrapConfig()
    boot = factory.create(cfg)

    # RunRegistry 是 gateway-internal 单例(没在 kernel 注册),就地构造。
    from gateway.runs.session.session import RunRegistry
    from gateway.runs.terminal.legacy_adapter import RegistryRunAdapter

    run_registry = RunRegistry()
    run_port = RegistryRunAdapter(run_registry, machine_resolver=boot.machine_resolver)

    # file_store 优先复用 kernel seam(允许 bootstrap_file_store 注入);
    # 回退到 bootstrap 默认根。
    file_store = boot.file_store
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

    # The /runs/{id}/evidence/{ref} endpoint resolves
    # ``request.app.state.bound_observability`` (see
    # ``gateway/runs/api/query_endpoints.py``); expose the kernel-injected
    # observability seam under the same key. If the seam isn't wired, the
    # endpoint will surface a 503 with a documented error.
    if ctx is not None:
        with contextlib.suppress(Exception):
            app.state.bound_observability = ctx.inject("observability")

    # Bind process-level journal projection so ``/journal/live`` works
    # without requiring a prior run creation. The factory comes from the
    # kernel seam (``lca.plugins.seams.observability.run_ledger`` provides
    # it as ``run_ledger_factory``); if the seam isn't wired we silently
    # skip (the endpoint will 500 with the documented "create a run through
    # a journal factory" error instead).
    if ctx is not None:
        journal_factory: Any = None
        # ``MissingCapabilityError`` inherits from ``KeyError`` (not Exception)
        # so we must catch both bases here.
        with contextlib.suppress(Exception, KeyError):
            journal_factory = ctx.inject("run_ledger_factory")
        if journal_factory is not None and hasattr(journal_factory, "create_process_journal"):
            with contextlib.suppress(Exception):
                run_registry.bind_process_journal(journal_factory)


__all__ = [
    "DefaultGatewayBootstrapFactory",
    "GatewayBootstrap",
    "GatewayBootstrapConfig",
    "GatewayBootstrapFactory",
    "install_gateway_state",
]
