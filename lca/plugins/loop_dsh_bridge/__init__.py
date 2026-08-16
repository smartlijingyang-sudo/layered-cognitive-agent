"""DSH Bridge loop provider plugin — spec Phase D.

Wraps the existing DSH runtime as an ``AgentLoopFactory`` so the harness
spine can treat DSH the same as any other loop provider. The gateway
selects this plugin via profile/preset instead of an if/else branch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from lca.contracts.harness.agent import AgentHandle, AgentOptions
from lca.contracts.harness.plugin import PluginKind, PluginManifest
from lca.harness.agent.handle import OwnerAgentHandle
from lca.harness.session.inbox import Inbox
from lca.plugins.loop_dsh_bridge.live_agent import DshBridgeConfig, DshLiveAgent

_log = structlog.get_logger(__name__)

manifest = PluginManifest(
    id="lca.loop.dsh_bridge",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.PROVIDER,
    requires=("session_store",),
    optional_requires=("dsh_settings", "machine_transport"),
)


@dataclass(frozen=True)
class DshBridgeLoopFactory:
    """AgentLoopFactory that creates DSH-backed LiveAgents.

    Config is passed via ``AgentOptions.provider`` carrying the bridge
    config dict, or via scope-resolved services.
    """

    async def create(
        self,
        scope: Any,
        identity: Any,
        options: AgentOptions,
        *,
        resume_session: str | None = None,
    ) -> AgentHandle:
        session_store = scope.resolve("session_store")
        bridge_config = _resolve_bridge_config(scope, options)
        session_id = getattr(identity, "session_id", None) or str(identity)
        inbox = Inbox(session_store)
        live = DshLiveAgent(
            store=session_store,
            inbox=inbox,
            config=bridge_config,
            identity_id=session_id,
        )
        return OwnerAgentHandle(live)


def _resolve_bridge_config(scope: Any, options: AgentOptions) -> DshBridgeConfig:
    """Extract DshBridgeConfig from scope services or options."""
    # Try scope-resolved services first
    transport = _try_resolve(scope, "machine_transport")
    machine_id = _try_resolve(scope, "machine_id") or ""
    cwd = _try_resolve(scope, "machine_cwd") or ""
    settings = _try_resolve(scope, "dsh_settings")
    runs_dir = _try_resolve(scope, "runs_dir")

    if transport and machine_id and cwd:
        return DshBridgeConfig(
            machine_id=machine_id,
            cwd=cwd,
            transport=transport,
            settings=settings,
            runs_dir=runs_dir,
        )

    # Fallback: config from options metadata
    raise ValueError(
        "DshBridgeLoopFactory requires machine_transport, machine_id, and machine_cwd "
        "in scope or bridge config"
    )


def _try_resolve(scope: Any, key: str) -> Any:
    try:
        return scope.resolve(key)
    except Exception:
        return None


def apply(ctx: Any, config: dict[str, Any]) -> None:
    """Register DshBridgeLoopFactory in the plugin context."""
    factory = DshBridgeLoopFactory()
    ctx.mount("lca.loop.dsh_bridge", factory)
