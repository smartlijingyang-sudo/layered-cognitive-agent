"""Register ``/runs`` + ``/v1/sessions`` route groups (PR-4 routes-runs-sessions).

handler 内部继续复用 ``gateway.runs.api.command_endpoints`` /
``gateway.runs.api.query_endpoints`` / ``gateway.session_routes`` 的现有
实现;本 PR 只 plugin 化路由注册,不重构 handler 内部(留给 PR-5 清理跨层 import)。
"""

from __future__ import annotations

from typing import Any

from starlette.routing import Route

from gateway.runs.api.command_endpoints import (
    answer_run,
    cancel_run,
    create_run,
)
from gateway.runs.api.query_endpoints import (
    get_run,
    get_run_doctor,
    get_run_evidence,
    get_run_profile,
    stream_run_live,
)
from gateway.session_routes import (
    command_answer,
    command_cancel,
    command_inject,
    command_steer,
    create_session,
    get_snapshot,
    send_message,
    stream_events,
)
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
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

# PR-7 (本批):把 ``/runs/{run_id}/profile`` 与 ``/runs/{run_id}/evidence/{ref}``
# 从 ``gateway.routes.build_routes`` 迁过来,build_routes 退役 —— plugin 是
# 唯一 route catalog SSOT (ADR-0115 §决定 6)。
ROUTES: tuple[Route, ...] = (
    Route("/runs", create_run, methods=["POST", "OPTIONS"]),
    Route("/runs/{run_id}", get_run, methods=["GET"]),
    Route("/runs/{run_id}/live", stream_run_live, methods=["GET", "OPTIONS"]),
    Route("/runs/{run_id}/doctor", get_run_doctor, methods=["GET"]),
    Route("/runs/{run_id}/profile", get_run_profile, methods=["GET"]),
    Route("/runs/{run_id}/evidence/{ref:path}", get_run_evidence, methods=["GET"]),
    Route("/runs/{run_id}/cancel", cancel_run, methods=["POST", "OPTIONS"]),
    Route("/runs/{run_id}/answer", answer_run, methods=["POST", "OPTIONS"]),
    Route("/v1/sessions", create_session, methods=["POST", "OPTIONS"]),
    Route("/v1/sessions/{session_id}/messages", send_message, methods=["POST", "OPTIONS"]),
    Route("/v1/sessions/{session_id}/snapshot", get_snapshot, methods=["GET", "OPTIONS"]),
    Route("/v1/sessions/{session_id}/events", stream_events, methods=["GET", "OPTIONS"]),
    Route("/v1/sessions/{session_id}/commands/answer", command_answer, methods=["POST", "OPTIONS"]),
    Route("/v1/sessions/{session_id}/commands/cancel", command_cancel, methods=["POST", "OPTIONS"]),
    Route("/v1/sessions/{session_id}/commands/steer", command_steer, methods=["POST", "OPTIONS"]),
    Route("/v1/sessions/{session_id}/commands/inject", command_inject, methods=["POST", "OPTIONS"]),
)


@plugin(
    id="lca-gateway-routes-runs-sessions",
    provides=(),
    requires=("gateway_router",),
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    description="Register /runs (7) + /v1/sessions (8) routes.",
    test_suite="tests.lca_plugins.transport.webserver.test_runs_sessions",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G9_INTERACTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-gateway-routes-runs-sessions.served",),
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("gateway_router",),
        emits=("gateway_runs_sessions_route.registered",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Any) -> None:
    router = ctx.require("gateway_router")
    # PluginContext Protocol does not expose ``effect()``;the underlying
    # :class:`cordis.Context` does. Reach it through the audited facade.
    inner: Any = ctx._runtime()  # type: ignore[attr-defined]
    for route in ROUTES:
        dispose = router.register_http(route)
        inner.effect(dispose, label=f"route:{route.path}")
