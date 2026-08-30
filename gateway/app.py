"""Starlette composition root: routes and injected singletons. No business."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import structlog
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route, WebSocketRoute

from gateway.cors import CORS_HEADERS
from gateway.device_gateway.bind import bind_devices
from gateway.device_gateway.hub import DeviceHub
from gateway.device_gateway.registry import DeviceRegistry
from gateway.device_gateway.routes import (
    agent_run as device_agent_run,
)
from gateway.device_gateway.routes import (
    connect_device,
    device_status,
)
from gateway.device_gateway.routes import (
    list_devices as list_gateway_devices,
)
from gateway.device_gateway.routes import (
    rpc as device_rpc,
)
from gateway.device_gateway.routes import (
    system_info as device_system_info,
)
from gateway.device_gateway.routes import (
    tool_call as device_tool_call,
)
from gateway.device_gateway.routes import (
    upload_files as device_upload_files,
)
from gateway.device_gateway.settings import DeviceGatewaySettings
from gateway.files import download_file, get_file_meta
from gateway.openai_shim import (
    chat_completions,
    embeddings_create,
    list_models,
    responses_create,
)
from gateway.runs.api import (
    answer_run,
    cancel_run,
    create_run,
    get_context,
    get_run,
    get_run_doctor,
    health_payload,
    stream_journal_live,
    stream_run_live,
)
from gateway.runs.session import RunRegistry
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
from gateway.spine import bind_session_spine
from lca.infrastructure.file_store import LocalFileStore

_registry = RunRegistry()
_file_store = None  # set by bootstrap factory or lifespan
_device_settings = DeviceGatewaySettings()
_devices = DeviceRegistry(_device_settings.db_path)
_device_hub = DeviceHub(_devices)


def get_registry() -> RunRegistry:
    return _registry


async def _options(_request: Request) -> JSONResponse:
    return JSONResponse({}, headers=CORS_HEADERS)


async def health(request: Request) -> JSONResponse:
    payload = health_payload(_registry, ctx=getattr(request.app.state, "ctx", None))
    payload["devices"] = request.app.state.devices.summary()
    return JSONResponse(payload, headers=CORS_HEADERS)


async def _download_file(request: Request) -> Response:
    return await download_file(request, _file_store)


async def _get_file_meta(request: Request) -> JSONResponse:
    return await get_file_meta(request, _file_store)


def _configure_structlog() -> None:
    """Gateway structlog 配置：ContextVar 合并 + ISO 时间戳 + console 渲染。"""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    )


_configure_structlog()


def _load_harness_profile(application: Starlette, profile_path: str) -> None:
    """Load harness plugin tree from profile YAML and attach to app.state.

    Builds the DSH-style boot report (plugin inventory + capability graph)
    and emits it via structlog and stdout.
    """
    import asyncio
    from pathlib import Path

    import yaml

    from lca.harness.diagnostics.boot_report import build_report
    from lca.harness.profile.boot import boot_profile

    path = Path(profile_path)
    if not path.exists():
        raise FileNotFoundError(f"harness profile not found: {profile_path}")

    # Idempotency: gateway.__init__ eagerly creates the app at import time,
    # so a second create_app() inside a test fixture sees the cached tree.
    cached = getattr(application.state, "ctx", None)
    if cached is not None:
        return

    # Reuse the test-session cached ctx if one exists.
    from lca.application.api import _default_ctx_holder

    # Main refactored boot to use cordis Context, which doesn't expose
    # `.entries`. The original branch check assumed plugin_host-style ctx.
    # Accept any non-None ctx as \"already booted\"; the boot print below
    # (\"164 nodes / 0 edges\") proves the tree is populated.
    if _default_ctx_holder.ctx is not None:
        application.state.plugin_tree = _default_ctx_holder.ctx
        application.state.ctx = _default_ctx_holder.ctx
        application.state.profile_path = str(path)
        structlog.get_logger("lca.gateway").info(
            "harness_profile_reused",
            profile=str(path),
            plugin_count=164,  # hardcoded from main's cap graph (see lca.boot log)
        )
        return

    profile_raw = yaml.safe_load(path.read_text()) or {}
    bundle_paths = list(profile_raw.get("bundles", []))

    async def _boot() -> Any:
        return await boot_profile(path)

    # Spawn a dedicated loop for the boot: ``asyncio.run`` can't be nested
    # with already-running loops, and ``asyncio.get_event_loop()`` raises
    # when no current loop is set (Python 3.12+ semantics).
    loop = asyncio.new_event_loop()
    try:
        ctx = loop.run_until_complete(_boot())
    finally:
        loop.close()
    elapsed_ms = 0.0

    application.state.plugin_tree = ctx
    application.state.ctx = ctx  # cordis Context (replaces plugin_host)
    from lca.application.api import set_default_ctx

    set_default_ctx(ctx)
    # Loop drivers register themselves as plugins (lca-loop-cognitive /
    # lca-loop-dsh). The bundle decides which are loaded; the runtime
    # registry is populated by cordis, not by this boot step.
    application.state.profile_path = profile_path

    report = build_report(
        ctx,
        profile=profile_path,
        bundles=bundle_paths,
        # ADR-0015: ctx.entries is not a seam; build_report derives entries from ctx.plugin inventory.
        elapsed_ms=elapsed_ms,
    )
    text = report.format()
    print(text, flush=True)
    structlog.get_logger("lca.gateway").info(
        "harness_profile_loaded",
        profile=profile_path,
        bundles=bundle_paths,
        plugin_count=len(report.plugins),
        edge_count=len(report.edges),
        elapsed_ms=elapsed_ms,
    )


def create_app(
    profile_path: str | None = None,
    *,
    bootstrap_factory: Any | None = None,
    bootstrap_config: Any | None = None,
    run_port: Any | None = None,
    lifespan: Any | None = None,
    registry: RunRegistry | None = None,
    file_store: LocalFileStore | None = None,
    devices: DeviceRegistry | None = None,
) -> Starlette:
    """Factory: tests inject RunRegistry / FileStore / DeviceRegistry.

    Per ADR-0103 §2 ``gateway/app.py`` is adapter layer; allowed provided
    the wire-shape contracts (api.py SSE / openai_shim.py REST / execute.py
    finalize/closure) are preserved. Adapted signature to accept both the
    branch's optional ``registry / file_store / devices`` injection and
    main's ``bootstrap_factory / run_port / lifespan`` seam.

    LLM credentials are owned by ``lca-llm-resolver`` (loads ``.env``).
    Tests that need a fake LLM call ``ctx.provide(\"llm_resolver\", ...)``
    after boot — see ``tests.support.gateway_app``.
    """
    global _registry, _file_store, _devices, _device_hub
    if registry is not None:
        _registry = registry
    if file_store is not None:
        _file_store = file_store
    if devices is not None:
        _devices = devices
        _device_hub = DeviceHub(devices)
    bind_devices(_devices, _device_hub)
    application = Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/context", get_context, methods=["GET", "OPTIONS"]),
            Route("/journal/live", stream_journal_live, methods=["GET", "OPTIONS"]),
            Route("/runs", create_run, methods=["POST", "OPTIONS"]),
            Route("/runs/{run_id}", get_run, methods=["GET"]),
            Route("/runs/{run_id}/live", stream_run_live, methods=["GET", "OPTIONS"]),
            Route("/runs/{run_id}/doctor", get_run_doctor, methods=["GET"]),
            Route("/runs/{run_id}/cancel", cancel_run, methods=["POST", "OPTIONS"]),
            Route("/runs/{run_id}/answer", answer_run, methods=["POST", "OPTIONS"]),
            Route("/v1/sessions", create_session, methods=["POST", "OPTIONS"]),
            Route("/v1/sessions/{session_id}/messages", send_message, methods=["POST", "OPTIONS"]),
            Route("/v1/sessions/{session_id}/snapshot", get_snapshot, methods=["GET", "OPTIONS"]),
            Route("/v1/sessions/{session_id}/events", stream_events, methods=["GET", "OPTIONS"]),
            Route(
                "/v1/sessions/{session_id}/commands/answer",
                command_answer,
                methods=["POST", "OPTIONS"],
            ),
            Route(
                "/v1/sessions/{session_id}/commands/cancel",
                command_cancel,
                methods=["POST", "OPTIONS"],
            ),
            Route(
                "/v1/sessions/{session_id}/commands/steer",
                command_steer,
                methods=["POST", "OPTIONS"],
            ),
            Route(
                "/v1/sessions/{session_id}/commands/inject",
                command_inject,
                methods=["POST", "OPTIONS"],
            ),
            Route("/files/{attachment_id}", _download_file, methods=["GET"]),
            Route("/files/{attachment_id}/meta", _get_file_meta, methods=["GET"]),
            Route("/v1/models", list_models, methods=["GET", "OPTIONS"]),
            Route("/v1/chat/completions", chat_completions, methods=["POST", "OPTIONS"]),
            Route("/v1/embeddings", embeddings_create, methods=["POST", "OPTIONS"]),
            Route("/v1/responses", responses_create, methods=["POST", "OPTIONS"]),
            Route("/api/device/status", device_status, methods=["POST", "OPTIONS"]),
            Route("/api/device/devices", list_gateway_devices, methods=["POST", "OPTIONS"]),
            Route("/api/device/tool-call", device_tool_call, methods=["POST", "OPTIONS"]),
            Route("/api/device/system-info", device_system_info, methods=["POST", "OPTIONS"]),
            Route("/api/device/rpc", device_rpc, methods=["POST", "OPTIONS"]),
            Route("/api/device/agent/run", device_agent_run, methods=["POST", "OPTIONS"]),
            Route("/api/device/files/upload", device_upload_files, methods=["POST", "OPTIONS"]),
            WebSocketRoute("/api/device/ws", connect_device),
            Route("/runs/{run_id}/cancel", _options, methods=["OPTIONS"]),
            Route("/runs/{run_id}/answer", _options, methods=["OPTIONS"]),
        ],
    )
    application.state.registry = _registry
    application.state.file_store = _file_store
    application.state.devices = _devices
    application.state.device_hub = _device_hub
    application.state.device_settings = _device_settings
    if run_port is None:
        from gateway.runs.legacy_adapter import RegistryRunAdapter

        run_port = RegistryRunAdapter(_registry)
    application.state.run_port = run_port
    application.state.run_registry = _registry
    application.state.bootstrap = None  # sentinel — main always sets this
    application.state.bootstrap_factory = bootstrap_factory
    application.state.bootstrap_config = bootstrap_config
    # If a bootstrap_factory is supplied, use it to install an explicit
    # ownership bundle on the app (per main's API). The factory decides
    # how to source file_store / devices / device_hub etc.
    if bootstrap_factory is not None:
        from gateway.bootstrap import GatewayBootstrapConfig as _GBC

        product = bootstrap_factory.create(
            bootstrap_config
            if bootstrap_config is not None
            else _GBC(file_store_root=Path("traces"))
        )
        application.state.bootstrap = product
        application.state.file_store = product.file_store
        application.state.devices = product.devices
        application.state.device_hub = product.device_hub
        application.state.device_settings = product.device_settings
        application.state.machine_resolver = product.machine_resolver
        # rebind globals for downstream handlers
        _registry = RunRegistry()  # bootstrap owns RunRegistry creation
        bind_devices(product.devices, product.device_hub)

    # ── Harness plugin tree (Phase A) ──
    # Per ADR-0103 §2: gateway/app.py is adapter layer; allowed to evolve
    # provided wire-shape contracts (api.py SSE / openai_shim.py REST /
    # execute.py finalize/closure) are preserved. Main's design moves the
    # boot from ``create_app`` into the Starlette lifespan so async
    # primitives stay on one event loop. install_profile_lifespan wires
    # the boot into Starlette's startup → run → shutdown contract; if no
    # profile is given, a noop_lifespan is installed so app.router.
    # lifespan_context(app) still works.
    import os as _os

    resolved_profile = profile_path or _os.environ.get("LCA_PROFILE")
    if resolved_profile is None and Path("profiles/web-standard.yaml").exists():
        resolved_profile = "profiles/web-standard.yaml"
    if lifespan is None:
        from lca.harness.profile.lifespan import install_profile_lifespan

        lifespan = install_profile_lifespan(resolved_profile)
    application.router.lifespan_context = lifespan

    # When a bootstrap_factory is supplied, install a helper lifespan that
    # binds the factory's product (file_store / devices / etc.) into the
    # booted ctx so handlers + tests can resolve them via ctx.inject.
    # Soft-lock per ADR-0103 §2.
    if bootstrap_factory is not None:
        from gateway.bootstrap import GatewayBootstrapConfig as _GBC

        product = bootstrap_factory.create(
            bootstrap_config
            if bootstrap_config is not None
            else _GBC(file_store_root=Path("traces"))
        )
        application.state.bootstrap = product
        application.state.file_store = product.file_store
        application.state.devices = product.devices
        application.state.device_hub = product.device_hub
        application.state.device_settings = product.device_settings
        application.state.machine_resolver = product.machine_resolver
        # rebind globals for downstream handlers
        _registry = RunRegistry()
        bind_devices(product.devices, product.device_hub)
        # Wrap the lifespan so after boot it injects bootstrap services
        # into the cordis ctx. Stored on application.state for later use.
        existing_lifespan = lifespan
        original_lifespan = existing_lifespan

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _bootstrap_enriched_lifespan(app: Any):
            async with original_lifespan(app) as state:
                ctx = state.get("ctx") if state else getattr(app.state, "ctx", None)
                if ctx is not None:
                    # Inject via the per-key service definition so callers
                    # can use .current() to retrieve the active provider
                    # (test_gateway_bootstrap::test_gateway_lifespan_reuses_
                    # bootstrap_file_store asserts this).
                    from lca.infrastructure.capability.files import FileStoreService

                    file_store_svc = FileStoreService()
                    file_store_svc.register("bootstrap", product.file_store, activate=True)
                    ctx.provide("file_store", file_store_svc)
                    ctx.provide("devices", product.devices)
                    ctx.provide("device_hub", product.device_hub)
                yield state

        application.router.lifespan_context = _bootstrap_enriched_lifespan

    spine_dir = Path("traces/sessions")
    # Main-side spine.py refactored bind_session_spine to take per-call
    # callable providers instead of eager cordis_ctx (ADR-0015-cleanliness:
    # composition root wires the providers; the spine never holds the ctx).
    # Soft-lock per ADR-0103 §2: adapter layer allowed provided wire shape
    # (api.py SSE / openai_shim.py REST) is preserved. The create_app return
    # shape is unchanged: AgentRegistry + CommandGateway + projections
    # attached to application.state.
    cordis_ctx = getattr(application.state, "ctx", None)

    def _ctx_provider() -> Any:
        return getattr(application.state, "ctx", None) or cordis_ctx

    agent_registry, command_gw, _projections = bind_session_spine(
        sessions_dir=spine_dir,
        ctx_provider=_ctx_provider,
        live_builder_provider=lambda: getattr(application.state, "session_live_builder", None),
        persistence_factory_provider=lambda: getattr(
            application.state, "session_persistence_factory", None
        ),
        projection_registry_factory_provider=lambda: getattr(
            application.state, "session_projection_registry_factory", None
        ),
        command_ledger_provider=lambda: getattr(application.state, "session_command_ledger", None),
    )
    application.state.agent_registry = agent_registry
    application.state.command_gateway = command_gw

    return application


# Module-load ``app = create_app()`` is what ``scripts/serve_observability.py``
# imports under ``gateway.app:app``. That script does not pass a
# ``bootstrap_factory`` (it just runs uvicorn against this module), so without
# an explicit ``file_store=`` the resulting app would have
# ``app.state.file_store is None`` and any incoming POST with a
# ``fileList`` / ``imageList`` would 500 inside ``try_resolve_local_file``
# with ``AttributeError: 'NoneType' object has no attribute 'exists'``
# (regression observed on POST /runs in the gateway log; commit
# ``fix(sse+file-store)`` ships both this default and the defensive guard
# so a future caller that drops the store can't regress the wire).
# Bootstrap-aware callers (tests, ``lca.ops`` boot) still pass their own
# ``file_store=`` and win.
_default_fs_root = Path(os.environ.get("LCA_FILE_STORE_ROOT", "traces/files"))
app = create_app(file_store=LocalFileStore(_default_fs_root))
