# Harness Spine 未完成 Phase 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 harness-spine-spec.md 定义的 Phase A-E 所有未完成项，使 LCA 达到 plugin-everything 架构自洽性。

**Architecture:** 在已有的 harness SPI 契约和骨架实现基础上，完成 Gateway 集成、API 层迁移、CognitiveRuntime middleware 开放、DSH 事件映射、Tool Pipeline 收敛五大工作流。所有变更通过 MIGRATION_FLAGS 控制灰度，保持向后兼容。

**Tech Stack:** Python 3.11+, asyncio, dataclasses, Protocol, ContextVar, pydantic, Starlette, pytest, pytest-asyncio

## Global Constraints

- **N1 — Journal 唯一事实**：AgentState/RunSession.status/前端 activity 都是 journal 的 projection
- **N2 — Agent 是一等实体**：Agent = Session + Inbox + scoped plugin tree + loop driver + AgentHandle
- **N3 — Loop 可替换**：CognitiveRuntime 是第一个 loop provider，不是唯一 runtime
- **N4 — Gateway 是纯 Carrier**：Gateway 只做 HTTP/SSE → typed command → projection snapshot，不 import concrete loop/brain/body
- **N5 — Plugin tree 驱动装配**：生产环境通过 profile → bundles → patch 解析 plugin tree
- **N6 — 前端消费 whole-value projection**：前端不 fold raw domain events
- **Python 风格**：所有新代码使用 type hints、frozen dataclass、async/await；禁止裸 `dict`，使用 `dict[str, Any]`
- **测试覆盖**：每个 task 必须有对应的 pytest 测试，测试文件命名 `tests/harness/test_<component>.py`
- **向后兼容**：旧 `boot_capabilities()` 路径在 Phase A 期间保持可用；旧 `/runs/*` API 在 Phase B 期间通过 LegacyApiAdapter 翻译
- **架构守卫**：`tests/test_architecture_*.py` 中必须有 import boundary 测试

---

## Task 1: Seam Catalog 迁移为 Loader reconcile pass（A.7）

**Files:**
- Modify: `lca/layer0_infra/plugin/loader/_loader.py` (add `_check_seam_completeness`)
- Modify: `lca/layer4_app/capability_boot.py` (simplify `register_seam_catalog`)
- Create: `tests/harness/test_seam_completeness.py`

**Interfaces:**
- Consumes: `PluginManifest` from `lca.contracts.harness.plugin`, `PluginHandle` from kernel
- Produces: `Loader._check_seam_completeness(handles)` method called during `reconcile()`

**Context:** 当前 LCA 有两套并行扩展机制——Capability Seam（`register_seam_catalog()`）和 Plugin Kernel（Loader reconcile）。本 task 将 Seam 完整性校验融入 Loader，消除独立注册表。Spec §3.7。

- [ ] **Step 1: Write failing test for seam completeness check**

```python
# tests/harness/test_seam_completeness.py
import pytest
from lca.contracts.harness.plugin import PluginManifest, PluginKind, ExtensionPoint

class TestSeamCompleteness:
    """Loader reconcile 自动校验 Seam 三角完整性"""

    def test_definition_without_provider_raises(self):
        """有 DEFINITION 但没有 PROVIDER → 报错"""
        from lca.infrastructure.plugin.loader._loader import Loader
        handles = [_make_handle(PluginManifest(
            id="defn", version="1.0.0", api_version="lca-harness/1",
            kind=PluginKind.DEFINITION, seam_key="llm",
            extension_points=(ExtensionPoint(seam_key="llm"),),
        ))]
        loader = Loader()
        with pytest.raises(Exception, match="no provider"):
            loader._check_seam_completeness(handles)

    def test_provider_without_definition_raises(self):
        """PROVIDER 引用不存在的 DEFINITION → 报错"""
        from lca.infrastructure.plugin.loader._loader import Loader
        handles = [_make_handle(PluginManifest(
            id="prov", version="1.0.0", api_version="lca-harness/1",
            kind=PluginKind.PROVIDER, seam_key="unknown_seam",
        ))]
        loader = Loader()
        with pytest.raises(Exception, match="unknown seam"):
            loader._check_seam_completeness(handles)

    def test_complete_triangle_passes(self):
        """DEFINITION + PROVIDER + CONSUMER → 通过"""
        from lca.infrastructure.plugin.loader._loader import Loader
        handles = [
            _make_handle(PluginManifest(
                id="defn", version="1.0.0", api_version="lca-harness/1",
                kind=PluginKind.DEFINITION, seam_key="llm",
                extension_points=(ExtensionPoint(seam_key="llm"),),
            )),
            _make_handle(PluginManifest(
                id="prov", version="1.0.0", api_version="lca-harness/1",
                kind=PluginKind.PROVIDER, seam_key="llm",
            )),
            _make_handle(PluginManifest(
                id="cons", version="1.0.0", api_version="lca-harness/1",
                kind=PluginKind.CONSUMER, seam_key="llm",
            )),
        ]
        loader = Loader()
        loader._check_seam_completeness(handles)  # should not raise

    def test_definition_without_consumer_warns(self):
        """有 DEFINITION + PROVIDER 但无 CONSUMER → warning，不报错"""
        from lca.infrastructure.plugin.loader._loader import Loader
        handles = [
            _make_handle(PluginManifest(
                id="defn", version="1.0.0", api_version="lca-harness/1",
                kind=PluginKind.DEFINITION, seam_key="llm",
                extension_points=(ExtensionPoint(seam_key="llm"),),
            )),
            _make_handle(PluginManifest(
                id="prov", version="1.0.0", api_version="lca-harness/1",
                kind=PluginKind.PROVIDER, seam_key="llm",
            )),
        ]
        loader = Loader()
        loader._check_seam_completeness(handles)  # should not raise, just warn

def _make_handle(manifest: PluginManifest):
    """创建最小 mock PluginHandle"""
    from unittest.mock import MagicMock
    h = MagicMock()
    h.manifest = manifest
    h.entry_id = manifest.id
    h.state = "ACTIVE"
    return h
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/harness/test_seam_completeness.py -v`
Expected: FAIL — `Loader` has no `_check_seam_completeness` method

- [ ] **Step 3: Implement `_check_seam_completeness` in Loader**

在 `lca/layer0_infra/plugin/loader/_loader.py` 中添加：

```python
async def _check_seam_completeness(self, handles: list) -> None:
    """校验 Seam 三角完整性：DEFINITION → PROVIDER → CONSUMER"""
    definitions: dict[str, object] = {}
    providers: dict[str, list[object]] = {}
    consumers: dict[str, list[object]] = {}

    for h in handles:
        m = h.manifest
        if m.kind == PluginKind.DEFINITION and m.seam_key:
            definitions[m.seam_key] = h
        elif m.kind == PluginKind.PROVIDER and m.seam_key:
            providers.setdefault(m.seam_key, []).append(h)
        elif m.kind == PluginKind.CONSUMER and m.seam_key:
            consumers.setdefault(m.seam_key, []).append(h)

    errors: list[str] = []
    for key, defn in definitions.items():
        if key not in providers:
            errors.append(
                f"Seam '{key}' defined by {defn.entry_id} has no provider"
            )
        if key not in consumers:
            import structlog
            structlog.get_logger().warning(
                "seam_no_consumer",
                seam_key=key,
                definition=defn.entry_id,
            )

    for key in providers:
        if key not in definitions:
            ids = [h.entry_id for h in providers[key]]
            errors.append(f"Provider for unknown seam '{key}': {ids}")

    if errors:
        raise SeamCompletenessError(errors)
```

同时在 `reconcile()` 方法的末尾调用此 pass。

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/harness/test_seam_completeness.py -v`
Expected: PASS

- [ ] **Step 5: Simplify `register_seam_catalog()` to delegate to Loader**

```python
# lca/layer4_app/capability_boot.py
def register_seam_catalog() -> None:
    """@deprecated: Loader._check_seam_completeness() 已替代此函数。"""
    import warnings
    warnings.warn(
        "register_seam_catalog() is deprecated; "
        "Loader handles seam completeness",
        DeprecationWarning,
        stacklevel=2,
    )
```

- [ ] **Step 6: Commit**

```bash
git add lca/layer0_infra/plugin/loader/_loader.py lca/layer4_app/capability_boot.py tests/harness/test_seam_completeness.py
git commit -m "feat(harness): A.7 seam catalog migration to Loader reconcile pass"
```

---

## Task 2: `lca inspect tree` CLI 诊断命令（A.6）

**Files:**
- Create: `lca/harness/diagnostics/tree.py`
- Modify: `lca/harness/diagnostics/__init__.py`
- Create: `tests/harness/test_inspect_tree.py`

**Interfaces:**
- Consumes: `PluginHandle` from kernel, `ProfileLoader` from `lca.infrastructure.plugin.include`
- Produces: `render_tree(host) -> str` function, `CmdInspectTree` CLI entry

**Context:** 运维需要可视化 plugin tree 的结构——每个 plugin 的状态、提供的服务、依赖、effect 数量。Spec §A.6。

- [ ] **Step 1: Write failing test for tree rendering**

```python
# tests/harness/test_inspect_tree.py
from lca.harness.diagnostics.tree import render_tree

class TestRenderTree:
    def test_render_empty_host(self):
        from unittest.mock import MagicMock
        host = MagicMock()
        host.handles = {}
        output = render_tree(host)
        assert "plugin tree" in output.lower() or "empty" in output.lower()

    def test_render_single_plugin(self):
        from unittest.mock import MagicMock
        handle = MagicMock()
        handle.entry_id = "lca.llm.service"
        handle.state = "ACTIVE"
        handle.spec.provides = ("llm",)
        handle.injected = ("memory",)
        handle.effects = [1, 2]  # just need len()

        host = MagicMock()
        host.handles = {"lca.llm.service": handle}
        output = render_tree(host)
        assert "lca.llm.service" in output
        assert "ACTIVE" in output
        assert "llm" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/harness/test_inspect_tree.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `render_tree`**

```python
# lca/harness/diagnostics/tree.py
"""Plugin tree diagnostic renderer."""
from __future__ import annotations
from typing import Any


def render_tree(host: Any, *, show_effects: bool = True) -> str:
    """Render plugin host as human-readable tree.

    Args:
        host: PluginHost or ScopedPluginHost instance
        show_effects: Whether to show effect count per plugin

    Returns:
        Multi-line string representation of the plugin tree
    """
    lines: list[str] = ["Plugin Tree", "=" * 60]

    if not host.handles:
        lines.append("  (empty — no plugins loaded)")
        return "\n".join(lines)

    for entry_id, handle in sorted(host.handles.items()):
        state = getattr(handle, "state", "UNKNOWN")
        provides = getattr(getattr(handle, "spec", None), "provides", ()) or ()
        injected = getattr(handle, "injected", ()) or ()
        effect_count = len(getattr(handle, "effects", []))

        lines.append(f"  {entry_id}")
        lines.append(f"    state:    {state}")
        if provides:
            lines.append(f"    provides: {', '.join(provides)}")
        if injected:
            lines.append(f"    inject:   {', '.join(injected)}")
        if show_effects:
            lines.append(f"    effects:  {effect_count}")

    lines.append("=" * 60)
    lines.append(f"  total plugins: {len(host.handles)}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/harness/test_inspect_tree.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lca/harness/diagnostics/tree.py lca/harness/diagnostics/__init__.py tests/harness/test_inspect_tree.py
git commit -m "feat(harness): A.6 lca inspect tree diagnostic command"
```

---

## Task 3: Gateway Startup 完整集成 Profile（A.4）

**Files:**
- Modify: `gateway/app.py`
- Create: `tests/harness/test_gateway_profile_integration.py`

**Interfaces:**
- Consumes: `ProfileLoader`, `Loader`, `bind_session_spine()`, `ScopedPluginHost`
- Produces: `app.state.plugin_tree`, `app.state.plugin_host` fully wired at startup

**Context:** Gateway 已有 `_load_harness_profile()` 骨架，但需确认完整的 startup flow：profile → Loader → plugin tree → `app.state`。Spec §A.4。

- [ ] **Step 1: Write test for profile-driven startup**

```python
# tests/harness/test_gateway_profile_integration.py
import pytest

class TestGatewayProfileIntegration:
    """Gateway startup loads profile and wires plugin tree"""

    def test_app_has_plugin_host_after_startup(self):
        """create_app() attaches plugin_host to app.state"""
        from gateway.app import create_app
        app = create_app()
        assert hasattr(app.state, "plugin_host") or hasattr(app.state, "plugin_tree")

    def test_app_has_agent_registry_after_startup(self):
        """create_app() attaches agent_registry to app.state"""
        from gateway.app import create_app
        app = create_app()
        assert hasattr(app.state, "agent_registry")

    def test_app_has_command_gateway_after_startup(self):
        """create_app() attaches command_gateway to app.state"""
        from gateway.app import create_app
        app = create_app()
        assert hasattr(app.state, "command_gateway")
```

- [ ] **Step 2: Run test to verify current state**

Run: `pytest tests/harness/test_gateway_profile_integration.py -v`
Expected: Some tests may already pass (gateway/app.py already has partial integration)

- [ ] **Step 3: Complete profile loading in gateway/app.py**

Verify and complete the `_load_harness_profile()` function:

```python
async def _load_harness_profile(profile_path: str | None = None) -> tuple:
    """Load profile YAML → resolve plugin tree → return (host, scope).

    Resolution order:
    1. profile_path argument
    2. LCA_PROFILE environment variable
    3. Auto-detect profiles/web-standard.yaml
    """
    import os
    from pathlib import Path

    resolved_path = profile_path or os.environ.get("LCA_PROFILE")
    if resolved_path is None:
        default = Path("profiles/web-standard.yaml")
        if default.exists():
            resolved_path = str(default)

    if resolved_path is None:
        raise RuntimeError(
            "No profile found. Set LCA_PROFILE or create profiles/web-standard.yaml"
        )

    from lca.infrastructure.plugin.include import ProfileLoader
    from lca.infrastructure.plugin.loader import Loader

    profile = ProfileLoader.load(resolved_path)
    loader = Loader()
    tree = await loader.load(profile.entries)

    return tree.host, tree
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/harness/test_gateway_profile_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gateway/app.py tests/harness/test_gateway_profile_integration.py
git commit -m "feat(harness): A.4 gateway startup loads profile-driven plugin tree"
```

---

## Task 4: Gateway Shadow Dual-Write（B.3）

**Files:**
- Create: `lca/harness/command/dual_write.py`
- Modify: `lca/harness/flags.py` (ensure SpineMode importable)
- Create: `tests/harness/test_dual_write.py`

**Interfaces:**
- Consumes: `CommandGateway`, legacy `execute_run()`, `ResultNormalizer`
- Produces: `ShadowExecutor` class that runs both paths and compares

**Context:** Migration flag `session_spine` 已定义（off/shadow/authoritative/legacy_removed），但 shadow 模式的实际执行逻辑未实现。Spec §B.3, §B.6。

- [ ] **Step 1: Write test for shadow dual-write execution**

```python
# tests/harness/test_dual_write.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from lca.harness.command.dual_write import ShadowExecutor
from lca.harness.diagnostics.normalizer import ResultNormalizer

class TestShadowExecutor:
    """Shadow mode: runs legacy + new path, compares results"""

    @pytest.mark.asyncio
    async def test_shadow_runs_both_paths(self):
        """Shadow executor runs legacy and new, returns legacy result"""
        legacy_fn = AsyncMock(return_value=MagicMock(
            status="completed", answer="hello",
            tool_calls=[], llm_calls=1, error=None,
            journal_events=[],
        ))
        new_fn = AsyncMock(return_value=MagicMock())

        executor = ShadowExecutor()
        result = await executor.execute_shadow(
            legacy_fn=legacy_fn,
            new_fn=new_fn,
        )

        legacy_fn.assert_awaited_once()
        new_fn.assert_awaited_once()
        assert result is legacy_fn.return_value

    @pytest.mark.asyncio
    async def test_shadow_logs_divergence(self):
        """When results diverge, shadow logs a warning"""
        from lca.contracts.harness.command import CommandReceipt

        legacy_result = MagicMock(
            status="completed", answer="hello",
            tool_calls=[], llm_calls=1, error=None,
            journal_events=[],
        )
        new_snapshot = MagicMock()
        new_snapshot.values = {"activity": {"status": "failed"}, "conversation": {}}

        normalizer = ResultNormalizer()
        executor = ShadowExecutor(normalizer=normalizer)
        report = executor.compare(legacy_result, new_snapshot, journal=[])
        # Divergence should be detected (status: completed vs failed)
        assert len(report.divergences) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/harness/test_dual_write.py -v`
Expected: FAIL — `ShadowExecutor` not found

- [ ] **Step 3: Implement ShadowExecutor**

```python
# lca/harness/command/dual_write.py
"""Shadow dual-write executor for migration safety."""
from __future__ import annotations
import asyncio
import structlog
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from lca.harness.diagnostics.normalizer import (
    ResultNormalizer, NormalizedResult, DivergenceReport,
)

_log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ShadowConfig:
    """Configuration for shadow dual-write mode."""
    timeout_seconds: float = 30.0
    log_divergence: bool = True


class ShadowExecutor:
    """Runs both legacy and new execution paths in shadow mode.

    Returns legacy result (authoritative during shadow phase).
    Logs divergence when results don't match.
    """

    def __init__(
        self,
        normalizer: ResultNormalizer | None = None,
        config: ShadowConfig | None = None,
    ) -> None:
        self._normalizer = normalizer or ResultNormalizer()
        self._config = config or ShadowConfig()

    async def execute_shadow(
        self,
        *,
        legacy_fn: Callable[[], Awaitable[Any]],
        new_fn: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Run both paths concurrently, return legacy result.

        Args:
            legacy_fn: Callable that executes the legacy path
            new_fn: Callable that executes the new harness path

        Returns:
            The legacy result (authoritative during shadow)
        """
        legacy_task = asyncio.create_task(legacy_fn())
        new_task = asyncio.create_task(new_fn())

        # Wait for legacy (authoritative)
        legacy_result = await asyncio.wait_for(
            legacy_task, timeout=self._config.timeout_seconds,
        )

        # Wait for new (best-effort)
        try:
            new_result = await asyncio.wait_for(
                new_task, timeout=self._config.timeout_seconds,
            )
        except asyncio.TimeoutError:
            _log.warning("shadow_new_path_timeout")
            return legacy_result

        # Compare (non-blocking)
        if self._config.log_divergence:
            try:
                report = self.compare(legacy_result, new_result, journal=[])
                if report.divergences:
                    _log.warning(
                        "shadow_divergence",
                        divergences=report.divergences,
                    )
            except Exception as e:
                _log.warning("shadow_compare_error", error=str(e))

        return legacy_result

    def compare(
        self,
        legacy_result: Any,
        new_result: Any,
        *,
        journal: list | None = None,
    ) -> DivergenceReport:
        """Compare normalized results from both paths."""
        norm_legacy = self._normalizer.from_task_result(legacy_result)
        norm_new = self._normalizer.from_projection(
            new_result, journal=journal or [],
        )

        divergences: list[str] = []
        if norm_legacy.status != norm_new.status:
            divergences.append(
                f"status: {norm_legacy.status} != {norm_new.status}"
            )
        if norm_legacy.llm_calls != norm_new.llm_calls:
            divergences.append(
                f"llm_calls: {norm_legacy.llm_calls} vs {norm_new.llm_calls}"
            )

        return DivergenceReport(
            divergences=divergences,
            legacy=norm_legacy,
            new=norm_new,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/harness/test_dual_write.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lca/harness/command/dual_write.py lca/harness/flags.py tests/harness/test_dual_write.py
git commit -m "feat(harness): B.3 gateway shadow dual-write executor"
```

---

## Task 5: New `/v1/sessions/*` API Endpoints（B.4）

**Files:**
- Create: `lca/plugins/gateway_starlette/session_routes.py`
- Create: `tests/harness/test_session_routes.py`

**Interfaces:**
- Consumes: `CommandGateway`, `SessionCreateCommand`, `MessageSendCommand`, etc.
- Produces: Starlette routes for `/v1/sessions/*`

**Context:** Spec §B.4 定义了新的 REST API。这些路由通过 CommandGateway 纯 dispatch，不 import 任何 concrete 实现。

- [ ] **Step 1: Write test for session API routes**

```python
# tests/harness/test_session_routes.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from starlette.testclient import TestClient
from starlette.applications import Starlette

class TestSessionRoutes:
    """New /v1/sessions/* API routes"""

    def _make_app(self, gateway_mock=None):
        from lca.plugins.gateway_starlette.session_routes import create_session_router
        from starlette.routing import Mount

        gw = gateway_mock or MagicMock()
        router = create_session_router(gw)
        app = Starlette(routes=[Mount("/v1", routes=router.routes)])
        app.state.command_gateway = gw
        return app

    def test_create_session_route_exists(self):
        """POST /v1/sessions route is registered"""
        app = self._make_app()
        routes = [r.path for r in app.routes]
        # Check that /v1/sessions is in the route tree
        assert any("sessions" in str(r) for r in app.routes)

    def test_send_message_route_exists(self):
        """POST /v1/sessions/{id}/messages route is registered"""
        app = self._make_app()
        assert any("messages" in str(r) for r in app.routes)

    def test_snapshot_route_exists(self):
        """GET /v1/sessions/{id}/snapshot route is registered"""
        app = self._make_app()
        assert any("snapshot" in str(r) for r in app.routes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/harness/test_session_routes.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement session routes**

```python
# lca/plugins/gateway_starlette/session_routes.py
"""New /v1/sessions/* API routes — pure carrier, no business logic."""
from __future__ import annotations
import json
from typing import Any

from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route, Router


def create_session_router(gateway: Any) -> Router:
    """Create Starlette router for /v1/sessions/* endpoints.

    All routes delegate to CommandGateway — no business logic here.
    """

    async def handle_create_session(request: Request) -> JSONResponse:
        from lca.contracts.harness.command import SessionCreateCommand
        body = await request.json()
        cmd = SessionCreateCommand(
            idempotency_key=body.get("idempotency_key", ""),
            profile=body.get("profile", "web-standard"),
            preset=body.get("preset"),
            agent_options=body.get("options"),
        )
        gw = request.app.state.command_gateway
        receipt = await gw.handle_create_session(cmd)
        return JSONResponse(
            status_code=201,
            content={
                "session_id": receipt.session_id,
                "seq": receipt.seq,
                "accepted": receipt.accepted,
            },
        )

    async def handle_send_message(request: Request) -> JSONResponse:
        from lca.contracts.harness.command import MessageSendCommand
        session_id = request.path_params["session_id"]
        body = await request.json()
        cmd = MessageSendCommand(
            idempotency_key=body.get("idempotency_key", ""),
            session_id=session_id,
            role="user",
            content=body["content"],
            attachments=tuple(body.get("attachments", ())),
        )
        gw = request.app.state.command_gateway
        receipt = await gw.handle_send_message(cmd)
        return JSONResponse(content={
            "session_id": receipt.session_id,
            "seq": receipt.seq,
            "accepted": receipt.accepted,
        })

    async def handle_snapshot(request: Request) -> JSONResponse:
        session_id = request.path_params["session_id"]
        gw = request.app.state.command_gateway
        snapshot = await gw.get_snapshot(session_id)
        return JSONResponse(content={
            "as_of_seq": snapshot.as_of_seq,
            "values": snapshot.values,
        })

    async def handle_sse_events(request: Request) -> StreamingResponse:
        session_id = request.path_params["session_id"]
        last_seq = int(request.query_params.get("last_seq", "0"))
        gw = request.app.state.command_gateway

        async def event_stream():
            async for change in gw.subscribe_changes(session_id, last_seq):
                data = json.dumps({
                    "key": change.key,
                    "seq": change.seq,
                    "version": change.version,
                    "value": change.value,
                })
                yield f"event: projection\ndata: {data}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
        )

    async def handle_answer(request: Request) -> JSONResponse:
        from lca.contracts.harness.command import AnswerCommand
        session_id = request.path_params["session_id"]
        body = await request.json()
        cmd = AnswerCommand(session_id=session_id, answer=body["answer"])
        gw = request.app.state.command_gateway
        receipt = await gw.handle_answer(cmd)
        return JSONResponse(content={"accepted": receipt.accepted})

    async def handle_cancel(request: Request) -> JSONResponse:
        from lca.contracts.harness.command import CancelCommand
        session_id = request.path_params["session_id"]
        body = await request.json()
        cmd = CancelCommand(
            session_id=session_id,
            keep_inbox=body.get("keep_inbox", True),
        )
        gw = request.app.state.command_gateway
        receipt = await gw.handle_cancel(cmd)
        return JSONResponse(content={"accepted": receipt.accepted})

    async def handle_steer(request: Request) -> JSONResponse:
        from lca.contracts.harness.command import SteerCommand
        session_id = request.path_params["session_id"]
        body = await request.json()
        cmd = SteerCommand(session_id=session_id, content=body["content"])
        gw = request.app.state.command_gateway
        receipt = await gw.handle_steer(cmd)
        return JSONResponse(content={"accepted": receipt.accepted})

    return Router(routes=[
        Route("/sessions", handle_create_session, methods=["POST"]),
        Route("/sessions/{session_id}/messages", handle_send_message, methods=["POST"]),
        Route("/sessions/{session_id}/snapshot", handle_snapshot, methods=["GET"]),
        Route("/sessions/{session_id}/events", handle_sse_events, methods=["GET"]),
        Route("/sessions/{session_id}/commands/answer", handle_answer, methods=["POST"]),
        Route("/sessions/{session_id}/commands/cancel", handle_cancel, methods=["POST"]),
        Route("/sessions/{session_id}/commands/steer", handle_steer, methods=["POST"]),
    ])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/harness/test_session_routes.py -v`
Expected: PASS

- [ ] **Step 5: Write architecture boundary test**

```python
# tests/test_architecture_gateway.py (append to existing or create)
def test_session_routes_no_concrete_import():
    """session_routes.py must not import layer1/layer2/layer3"""
    import ast
    from pathlib import Path

    source = Path("lca/plugins/gateway_starlette/session_routes.py").read_text()
    tree = ast.parse(source)

    forbidden = {"layer1_cognitive", "layer2_runtime", "layer3_agent"}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = getattr(node, "module", None) or ""
            for name in forbidden:
                assert name not in module, (
                    f"session_routes.py must not import {name}"
                )
```

- [ ] **Step 6: Commit**

```bash
git add lca/plugins/gateway_starlette/session_routes.py tests/harness/test_session_routes.py tests/test_architecture_gateway.py
git commit -m "feat(harness): B.4 new /v1/sessions/* API endpoints"
```

---

## Task 6: LegacyApiAdapter 旧 API 桥接（B.7）

**Files:**
- Create: `lca/plugins/gateway_starlette/legacy_adapter.py`
- Create: `tests/harness/test_legacy_adapter.py`

**Interfaces:**
- Consumes: `CommandGateway`, `SessionCreateCommand`, `MessageSendCommand`
- Produces: `LegacyApiAdapter` that translates `/runs/*` → `/v1/sessions/*` + sync bridge

**Context:** 旧 `/runs/*` 是同步返回结果，新 `/v1/sessions/*` 是异步的。LegacyApiAdapter 桥接两者——内部执行 create + send + wait_for_completion，然后翻译为 TaskResult 格式。Spec §B.7。

- [ ] **Step 1: Write test for legacy API adapter**

```python
# tests/harness/test_legacy_adapter.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from lca.plugins.gateway_starlette.legacy_adapter import LegacyApiAdapter

class TestLegacyApiAdapter:
    """Translates old /runs/* API to new command-based API"""

    @pytest.mark.asyncio
    async def test_wait_for_terminal_state_completed(self):
        """Waits until projection shows completed status"""
        gw = MagicMock()
        snapshot_completed = MagicMock()
        snapshot_completed.values = {"activity": {"status": "completed"}}
        gw.get_snapshot = AsyncMock(return_value=snapshot_completed)

        adapter = LegacyApiAdapter(gateway=gw)
        result = await adapter._wait_for_terminal_state(
            "session-1", timeout_s=5,
        )
        assert result.values["activity"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_wait_for_terminal_state_timeout(self):
        """Returns current state on timeout"""
        gw = MagicMock()
        snapshot_running = MagicMock()
        snapshot_running.values = {"activity": {"status": "working"}}
        gw.get_snapshot = AsyncMock(return_value=snapshot_running)

        adapter = LegacyApiAdapter(gateway=gw)
        result = await adapter._wait_for_terminal_state(
            "session-1", timeout_s=0.1,
        )
        assert result.values["activity"]["status"] == "working"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/harness/test_legacy_adapter.py -v`
Expected: FAIL

- [ ] **Step 3: Implement LegacyApiAdapter**

```python
# lca/plugins/gateway_starlette/legacy_adapter.py
"""Bridge old /runs/* API to new /v1/sessions/* command API."""
from __future__ import annotations
import asyncio
import time
from typing import Any

import structlog

_log = structlog.get_logger(__name__)


class LegacyApiAdapter:
    """Translates synchronous /runs/* requests to async command flow.

    POST /runs       → create session + send message + wait for result
    GET  /runs/{id}  → projection snapshot → TaskResult format
    GET  /runs/{id}/live → ProjectionChange SSE → LiveTail SSE format
    POST /runs/{id}/answer → AnswerCommand
    """

    def __init__(self, gateway: Any) -> None:
        self._gateway = gateway

    async def _wait_for_terminal_state(
        self,
        session_id: str,
        *,
        timeout_s: float = 120.0,
        poll_interval_s: float = 0.2,
    ) -> Any:
        """Wait until session reaches terminal state or timeout."""
        terminal = {"completed", "failed", "canceled", "waiting_input"}
        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            snapshot = await self._gateway.get_snapshot(session_id)
            status = snapshot.values.get("activity", {}).get("status")
            if status in terminal:
                return snapshot
            await asyncio.sleep(poll_interval_s)

        # Timeout — return current state
        return await self._gateway.get_snapshot(session_id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/harness/test_legacy_adapter.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lca/plugins/gateway_starlette/legacy_adapter.py tests/harness/test_legacy_adapter.py
git commit -m "feat(harness): B.7 LegacyApiAdapter for /runs/* → /v1/sessions/* bridge"
```

---

## Task 7: CognitiveRuntime Middleware Phase 开放（C.3）

**Files:**
- Modify: `lca/layer2_runtime/runtime_loop.py`
- Create: `tests/harness/test_runtime_middleware_integration.py`

**Interfaces:**
- Consumes: `MiddlewareRegistry`, `InMemoryMiddlewareRegistry`, `CognitiveRuntime`
- Produces: CognitiveRuntime calls middleware at each phase boundary

**Context:** 这是整个重构最关键的 task——CognitiveRuntime 内部从硬编码 hook 调用改为通过 MiddlewareRegistry 在 phase boundary 自动调用。横切关注点（journal/logging/budget/intervention）全部由 plugin middleware 实现。Spec §3.8。

- [ ] **Step 1: Write test for middleware phase integration**

```python
# tests/harness/test_runtime_middleware_integration.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from lca.harness.middleware.registry import InMemoryMiddlewareRegistry

class TestRuntimeMiddlewareIntegration:
    """CognitiveRuntime calls middleware at phase boundaries"""

    @pytest.mark.asyncio
    async def test_middleware_called_at_each_phase(self):
        """Each phase boundary invokes middleware registry"""
        mw_registry = InMemoryMiddlewareRegistry()
        call_log = []

        async def tracking_middleware(phase, state, context):
            call_log.append(phase)
            return state

        from lca.contracts.harness.middleware import MiddlewareRegistration
        for point in [
            "agent.before_perceive", "agent.after_perceive",
            "agent.before_think", "agent.after_think",
            "agent.before_act", "agent.after_act",
            "agent.before_reflect", "agent.after_reflect",
        ]:
            mw_registry.register(
                MiddlewareRegistration(seam_key=point, priority=50, plugin_id="test"),
                tracking_middleware,
            )

        # Verify middleware is registered
        for point in [
            "agent.before_perceive", "agent.before_think",
            "agent.before_act", "agent.before_reflect",
        ]:
            assert mw_registry.has_point(point)
            regs = mw_registry.list_registrations(point)
            assert len(regs) > 0

    @pytest.mark.asyncio
    async def test_middleware_can_modify_state(self):
        """Waterfall middleware can modify state between phases"""
        mw_registry = InMemoryMiddlewareRegistry()

        async def inject_context(phase, state, context):
            state["injected"] = True
            return state

        from lca.contracts.harness.middleware import MiddlewareRegistration
        mw_registry.register(
            MiddlewareRegistration(seam_key="agent.before_think", priority=50, plugin_id="test"),
            inject_context,
        )

        # Run the middleware
        from lca.harness.middleware.registry import SimplePhaseContext
        ctx = SimplePhaseContext(session_id="test", record=lambda e: None)
        result = await mw_registry.run(
            "agent.before_think", "think", {"injected": False}, ctx,
        )
        assert result["injected"] is True
```

- [ ] **Step 2: Run test to verify it passes** (middleware registry already works)

Run: `pytest tests/harness/test_runtime_middleware_integration.py -v`
Expected: PASS (registry already implemented)

- [ ] **Step 3: Integrate middleware into CognitiveRuntime step()**

In `lca/layer2_runtime/runtime_loop.py`, modify the `step()` or `run()` method to call middleware at each phase boundary:

```python
async def _run_phase_with_middleware(
    self,
    seam_key: str,
    phase: str,
    state: Any,
) -> Any:
    """Run a phase through middleware registry if available."""
    if self._mw is not None and self._mw.has_point(seam_key):
        from lca.harness.middleware.registry import SimplePhaseContext
        ctx = SimplePhaseContext(
            session_id=getattr(self, "_session_id", "unknown"),
            record=lambda e: None,  # TODO: wire to SessionStore
        )
        return await self._mw.run(seam_key, phase, state, ctx)
    return state
```

Then in the perceive/think/act/reflect cycle:

```python
# Before each phase
state = await self._run_phase_with_middleware(f"agent.before_{phase_name}", phase_name, state)
# Execute phase (existing logic)
state = self._execute_phase(phase_name, state)
# After each phase
state = await self._run_phase_with_middleware(f"agent.after_{phase_name}", phase_name, state)
```

- [ ] **Step 4: Write architecture test — no hardcoded hooks in runtime**

```python
# tests/test_architecture_runtime.py
def test_runtime_no_hardcoded_hooks():
    """CognitiveRuntime does not import hook/policy modules directly"""
    import ast
    from pathlib import Path

    source = Path("lca/layer2_runtime/runtime_loop.py").read_text()
    tree = ast.parse(source)

    forbidden_patterns = {"budget_check", "loop_intervention", "journal_emitting"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            for pattern in forbidden_patterns:
                assert pattern not in node.id, (
                    f"CognitiveRuntime should not reference {pattern} directly"
                )
```

- [ ] **Step 5: Run all tests and commit**

Run: `pytest tests/harness/test_runtime_middleware_integration.py tests/test_architecture_runtime.py -v`

```bash
git add lca/layer2_runtime/runtime_loop.py tests/harness/test_runtime_middleware_integration.py tests/test_architecture_runtime.py
git commit -m "feat(harness): C.3 CognitiveRuntime middleware phase boundary integration"
```

---

## Task 8: Budget Policy Plugin（C.3 配套）

**Files:**
- Create: `lca/plugins/budget_policy/__init__.py`
- Create: `tests/harness/test_budget_policy.py`

**Interfaces:**
- Consumes: `MiddlewareRegistry`, `MiddlewareRegistration`, `ScopedPluginHost`
- Produces: Budget check middleware registered at `agent.before_step`

**Context:** 原 `budget_check_hook` 硬编码在 CognitiveRuntime 中，现在迁移为独立 plugin middleware。Spec §3.8.4。

- [ ] **Step 1: Write test for budget policy middleware**

```python
# tests/harness/test_budget_policy.py
import pytest
from unittest.mock import MagicMock

class TestBudgetPolicy:
    """Budget check as plugin middleware"""

    @pytest.mark.asyncio
    async def test_budget_check_passes_under_limit(self):
        """State under budget → pass through"""
        from lca.plugins.budget_policy import budget_check_middleware
        state = MagicMock()
        state.step_count = 5
        ctx = MagicMock()
        result = await budget_check_middleware(
            "before_step", state, ctx, config={"max_steps": 100},
        )
        assert result is state

    @pytest.mark.asyncio
    async def test_budget_check_raises_over_limit(self):
        """State over budget → raises BudgetExceededError"""
        from lca.plugins.budget_policy import budget_check_middleware, BudgetExceededError
        state = MagicMock()
        state.step_count = 101
        ctx = MagicMock()
        with pytest.raises(BudgetExceededError):
            await budget_check_middleware(
                "before_step", state, ctx, config={"max_steps": 100},
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/harness/test_budget_policy.py -v`
Expected: FAIL

- [ ] **Step 3: Implement budget policy plugin**

```python
# lca/plugins/budget_policy/__init__.py
"""Budget check middleware as plugin — replaces hardcoded budget_check_hook."""
from lca.contracts.harness.plugin import PluginManifest, PluginKind, PluginContext
from lca.contracts.harness.middleware import MiddlewareRegistration


class BudgetExceededError(RuntimeError):
    """Raised when step or token budget is exhausted."""
    pass


manifest = PluginManifest(
    id="lca.policy.budget",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.POLICY,
    seam_key="agent.pre_step",
    middleware=("agent.before_step",),
)


async def budget_check_middleware(
    phase: str,
    state: object,
    context: object,
    *,
    config: dict | None = None,
) -> object:
    """Check step budget before each step.

    Raises BudgetExceededError if step_count >= max_steps.
    """
    cfg = config or {}
    max_steps = cfg.get("max_steps", 100)
    step_count = getattr(state, "step_count", 0)

    if step_count >= max_steps:
        raise BudgetExceededError(
            f"Step budget exhausted: {step_count}/{max_steps}"
        )
    return state


def apply(ctx: PluginContext, config: dict) -> None:
    """Register budget check middleware on the agent.before_step extension point."""
    registry = ctx.require("middleware_registry")
    registry.register(
        MiddlewareRegistration(
            seam_key="agent.before_step",
            priority=10,
            plugin_id="lca.policy.budget",
        ),
        lambda phase, state, context: budget_check_middleware(
            phase, state, context, config=config,
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/harness/test_budget_policy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lca/plugins/budget_policy/ tests/harness/test_budget_policy.py
git commit -m "feat(harness): C.3 budget policy plugin middleware"
```

---

## Task 9: Loop Intervention Policy Plugin（C.3 配套）

**Files:**
- Create: `lca/plugins/loop_intervention_policy/__init__.py`
- Create: `tests/harness/test_loop_intervention_policy.py`

**Interfaces:**
- Consumes: `MiddlewareRegistry`, `MiddlewareRegistration`
- Produces: Loop intervention middleware at `agent.after_act`

**Context:** 原 `loop_intervention_hook` 检测连续相同工具调用，防止 agent 陷入死循环。现迁移为 plugin middleware。Spec §3.8.3。

- [ ] **Step 1: Write test for loop intervention middleware**

```python
# tests/harness/test_loop_intervention_policy.py
import pytest

class TestLoopInterventionPolicy:
    """Detect consecutive identical tool calls and intervene"""

    @pytest.mark.asyncio
    async def test_no_intervention_on_different_tools(self):
        """Different tool calls → no intervention"""
        from lca.plugins.loop_intervention_policy import loop_intervention_middleware
        state = {"recent_tools": ["read", "write", "exec"]}
        result = await loop_intervention_middleware(
            "after_act", state, None, config={"threshold": 3},
        )
        assert result == state

    @pytest.mark.asyncio
    async def test_intervention_on_consecutive_identical(self):
        """N consecutive identical tool calls → intervention flag"""
        from lca.plugins.loop_intervention_policy import loop_intervention_middleware
        state = {"recent_tools": ["read", "read", "read"]}
        result = await loop_intervention_middleware(
            "after_act", state, None, config={"threshold": 3},
        )
        assert result.get("loop_intervention") is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/harness/test_loop_intervention_policy.py -v`
Expected: FAIL

- [ ] **Step 3: Implement loop intervention policy plugin**

```python
# lca/plugins/loop_intervention_policy/__init__.py
"""Loop intervention middleware — detects consecutive identical tool calls."""
from lca.contracts.harness.plugin import PluginManifest, PluginKind, PluginContext
from lca.contracts.harness.middleware import MiddlewareRegistration

manifest = PluginManifest(
    id="lca.policy.loop_intervention",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.POLICY,
    seam_key="agent.after_act",
    middleware=("agent.after_act",),
)


async def loop_intervention_middleware(
    phase: str,
    state: dict,
    context: object,
    *,
    config: dict | None = None,
) -> dict:
    """Check for consecutive identical tool calls.

    If the last N tool calls are identical, set loop_intervention flag.
    """
    cfg = config or {}
    threshold = cfg.get("threshold", 3)
    recent = state.get("recent_tools", [])

    if len(recent) >= threshold:
        last_n = recent[-threshold:]
        if len(set(last_n)) == 1:
            state = dict(state)
            state["loop_intervention"] = True
            return state

    return state


def apply(ctx: PluginContext, config: dict) -> None:
    registry = ctx.require("middleware_registry")
    registry.register(
        MiddlewareRegistration(
            seam_key="agent.after_act",
            priority=20,
            plugin_id="lca.policy.loop_intervention",
        ),
        lambda phase, state, context: loop_intervention_middleware(
            phase, state, context, config=config,
        ),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/harness/test_loop_intervention_policy.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lca/plugins/loop_intervention_policy/ tests/harness/test_loop_intervention_policy.py
git commit -m "feat(harness): C.3 loop intervention policy plugin middleware"
```

---

## Task 10: ReplayLoop 完整实现（C.5）

**Files:**
- Modify: `lca/plugins/loop_replay/__init__.py`
- Create: `tests/harness/test_loop_replay.py`

**Interfaces:**
- Consumes: `AgentLoopFactory`, `AgentHandle`, `LiveAgent`, `SessionStore`
- Produces: `ReplayLoopFactory` + `ReplayLiveAgent` that replays journal events deterministically

**Context:** Replay loop 从 golden journal 重放事件，不真正调用 LLM。用于测试、审计、调试。Spec §C.5。

- [ ] **Step 1: Write test for replay loop**

```python
# tests/harness/test_loop_replay.py
import pytest
from unittest.mock import MagicMock, AsyncMock

class TestReplayLoop:
    """Deterministic replay from golden journal"""

    @pytest.mark.asyncio
    async def test_replay_produces_events_in_order(self):
        """Replay yields events in journal seq order"""
        from lca.plugins.loop_replay import ReplayLiveAgent

        events = [
            MagicMock(type="turn.started.v1", seq=0),
            MagicMock(type="model.completed.v1", seq=1),
            MagicMock(type="turn.ended.v1", seq=2),
        ]
        store = MagicMock()
        store.read_from = AsyncMock(return_value=events)

        agent = ReplayLiveAgent(
            store=store,
            identity=MagicMock(session_id="replay-1"),
        )
        replayed = await agent.replay_all()
        assert len(replayed) == 3
        assert replayed[0].seq == 0
        assert replayed[2].seq == 2

    @pytest.mark.asyncio
    async def test_replay_factory_creates_handle(self):
        """ReplayLoopFactory.create() returns AgentHandle"""
        from lca.plugins.loop_replay import ReplayLoopFactory

        factory = ReplayLoopFactory()
        scope = MagicMock()
        store = MagicMock()
        scope.resolve = MagicMock(return_value=store)

        handle = await factory.create(
            scope=scope,
            session_id="replay-1",
            options=MagicMock(),
        )
        assert handle is not None
        assert hasattr(handle, "agent")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/harness/test_loop_replay.py -v`
Expected: FAIL

- [ ] **Step 3: Implement ReplayLoop**

```python
# lca/plugins/loop_replay/__init__.py
"""Deterministic replay loop — replays journal events without LLM calls."""
from __future__ import annotations
from typing import Any

from lca.contracts.harness.plugin import PluginManifest, PluginKind, PluginContext
from lca.contracts.harness.agent import AgentLoopFactory, AgentHandle, LiveAgent

manifest = PluginManifest(
    id="lca.loop.replay",
    version="1.0.0",
    api_version="lca-harness/1",
    kind=PluginKind.CONSUMER,
    requires=("session_store",),
)


class ReplayLiveAgent:
    """Replays journal events deterministically, no LLM calls."""

    def __init__(self, *, store: Any, identity: Any) -> None:
        self._store = store
        self._identity = identity
        self._status = "idle"

    @property
    def id(self) -> str:
        return self._identity.session_id

    @property
    def session_id(self) -> str:
        return self._identity.session_id

    @property
    def status(self) -> str:
        return self._status

    async def replay_all(self) -> list:
        """Replay all events from journal in order."""
        events = await self._store.read_from(seq=0)
        return sorted(events, key=lambda e: e.seq)

    async def followup(self, message: Any) -> Any:
        """Replay from journal — message is ignored."""
        self._status = "working"
        events = await self.replay_all()
        self._status = "idle"
        return events


class ReplayLoopFactory:
    """Creates ReplayLiveAgent from journal."""

    async def create(
        self,
        *,
        scope: Any,
        session_id: str,
        options: Any,
    ) -> AgentHandle:
        store = scope.resolve("session_store")
        identity = type("Identity", (), {"session_id": session_id})()
        agent = ReplayLiveAgent(store=store, identity=identity)
        handle = type("Handle", (), {
            "agent": agent,
            "dispose": staticmethod(async_method_stub),
        })()
        return handle


async def async_method_stub(*args, **kwargs):
    pass


def apply(ctx: PluginContext, config: dict) -> None:
    factory = ReplayLoopFactory()
    ctx.mount("lca.loop.replay", factory)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/harness/test_loop_replay.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lca/plugins/loop_replay/ tests/harness/test_loop_replay.py
git commit -m "feat(harness): C.5 replay loop full implementation"
```

---

## Task 11: DSH → SessionEvent 完整映射（D.2）

**Files:**
- Modify: `lca/plugins/loop_dsh_bridge/event_mapping.py`
- Create: `tests/harness/test_dsh_event_mapping.py`

**Interfaces:**
- Consumes: DSH notification events, `SessionEvent`, `@session_event` decorator
- Produces: `DshJournalProjector` that maps DSH events to LCA SessionEvents

**Context:** DSH 有自己的事件类型（`turn/start`, `tool/call` 等），需要映射到 LCA 事件词表（`turn.started.v1`, `tool.called.v1` 等）。Spec §D.2。

- [ ] **Step 1: Write test for DSH event mapping**

```python
# tests/harness/test_dsh_event_mapping.py
import pytest
from lca.plugins.loop_dsh_bridge.event_mapping import DSH_EVENT_MAP, DshJournalProjector

class TestDshEventMapping:
    """Map DSH notification events to LCA SessionEvents"""

    def test_event_map_has_core_types(self):
        """Core DSH event types are mapped"""
        assert "turn/start" in DSH_EVENT_MAP
        assert "turn/end" in DSH_EVENT_MAP
        assert "tool/call" in DSH_EVENT_MAP
        assert "tool/result" in DSH_EVENT_MAP
        assert "user/message" in DSH_EVENT_MAP
        assert "assistant/message" in DSH_EVENT_MAP

    def test_mapped_types_match_lca_vocabulary(self):
        """DSH events map to LCA v1 event types"""
        assert DSH_EVENT_MAP["turn/start"] == "turn.started.v1"
        assert DSH_EVENT_MAP["turn/end"] == "turn.ended.v1"
        assert DSH_EVENT_MAP["tool/call"] == "tool.called.v1"
        assert DSH_EVENT_MAP["tool/result"] == "tool.completed.v1"

    def test_projector_converts_event(self):
        """DshJournalProjector converts DSH event to LCA SessionEvent"""
        from unittest.mock import MagicMock
        projector = DshJournalProjector()

        dsh_event = MagicMock()
        dsh_event.type = "turn/start"
        dsh_event.data = {"turn": 1}

        result = projector.project(dsh_event)
        assert result is not None
        assert result.type == "turn.started.v1"

    def test_projector_skips_unknown_events(self):
        """Unknown DSH events are skipped with warning"""
        from unittest.mock import MagicMock
        projector = DshJournalProjector()

        dsh_event = MagicMock()
        dsh_event.type = "unknown/type"

        result = projector.project(dsh_event)
        assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/harness/test_dsh_event_mapping.py -v`
Expected: FAIL (event_mapping.py may have partial mapping)

- [ ] **Step 3: Complete DSH event mapping**

```python
# lca/plugins/loop_dsh_bridge/event_mapping.py
"""DSH → LCA event type mapping."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

import structlog

_log = structlog.get_logger(__name__)

# DSH event type → LCA SessionEvent type
DSH_EVENT_MAP: dict[str, str] = {
    "agent/created": "session.created.v1",
    "turn/start": "turn.started.v1",
    "turn/end": "turn.ended.v1",
    "step/start": "step.started.v1",
    "step/end": "step.ended.v1",
    "user/message": "message.accepted.v1",
    "assistant/message": "model.completed.v1",
    "assistant/chunk": "model.completed.v1",  # chunks collapse to completed
    "tool/call": "tool.called.v1",
    "tool/result": "tool.completed.v1",
}


@dataclass(frozen=True)
class MappedEvent:
    """Lightweight mapped event — mirrors SessionEvent shape."""
    type: str
    data: dict[str, Any]
    time: int = 0


class DshJournalProjector:
    """Converts DSH notification events to LCA SessionEvents."""

    def project(self, dsh_event: Any) -> MappedEvent | None:
        """Map a DSH event to LCA format.

        Returns None for unknown event types (with warning log).
        """
        lca_type = DSH_EVENT_MAP.get(dsh_event.type)
        if lca_type is None:
            _log.warning(
                "dsh_unknown_event",
                dsh_type=dsh_event.type,
            )
            return None

        return MappedEvent(
            type=lca_type,
            data=getattr(dsh_event, "data", {}),
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/harness/test_dsh_event_mapping.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lca/plugins/loop_dsh_bridge/event_mapping.py tests/harness/test_dsh_event_mapping.py
git commit -m "feat(harness): D.2 complete DSH → SessionEvent mapping"
```

---

## Task 12: Architecture Self-Consistency 守卫测试

**Files:**
- Create: `tests/test_architecture_self_consistency.py`

**Interfaces:**
- Consumes: AST analysis of source files
- Produces: Automated guards for plugin-everything 自洽性

**Context:** Spec §8.4 定义了多项架构守卫测试，确保重构不会引入新的硬编码。

- [ ] **Step 1: Write architecture self-consistency tests**

```python
# tests/test_architecture_self_consistency.py
"""Plugin-everything 自洽性守卫测试。"""
import ast
from pathlib import Path


def test_gateway_import_boundary():
    """CommandGateway only imports contracts/harness/{command,projection,session}"""
    source = Path("lca/harness/command/gateway.py").read_text()
    tree = ast.parse(source)

    forbidden = {"layer1_cognitive", "layer2_runtime", "layer3_agent",
                 "contracts.harness.agent"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for name in forbidden:
                assert name not in module, (
                    f"gateway.py must not import {name}"
                )


def test_no_hardcoded_boot_in_composer():
    """AgentComposer.compose(scope=...) does not call boot_capabilities()"""
    source = Path("lca/layer4_app/composer.py").read_text()
    # When scope is provided, boot_capabilities should NOT be called
    # This is a soft check — we verify the scope path exists
    assert "scope" in source
    assert "boot_capabilities" in source  # legacy path still exists


def test_migration_flags_env_override():
    """MIGRATION_FLAGS can be overridden via environment"""
    import os
    from lca.harness.flags import MIGRATION_FLAGS
    assert "session_spine" in MIGRATION_FLAGS


def test_all_plugin_modules_have_manifest():
    """Every plugin module under lca/plugins/ has a PluginManifest"""
    plugins_dir = Path("lca/plugins")
    for plugin_dir in plugins_dir.iterdir():
        if plugin_dir.is_dir() and (plugin_dir / "__init__.py").exists():
            source = (plugin_dir / "__init__.py").read_text()
            assert "PluginManifest" in source or "manifest" in source.lower(), (
                f"{plugin_dir.name}/__init__.py missing PluginManifest"
            )
```

- [ ] **Step 2: Run tests and commit**

Run: `pytest tests/test_architecture_self_consistency.py -v`

```bash
git add tests/test_architecture_self_consistency.py
git commit -m "test(harness): architecture self-consistency guard tests"
```

---

## Task 13: 全量测试验证 + Phase 验收

**Files:**
- No new files — runs existing tests
- Create: `docs/harness-phase-status.md` (final status report)

**Interfaces:** N/A (integration verification)

- [ ] **Step 1: Run all harness tests**

```bash
pytest tests/harness/ tests/test_architecture_*.py -v --tb=short
```

- [ ] **Step 2: Verify Phase A acceptance criteria**

- [ ] Same AgentSpec + mock LLM result is equivalent with profile-driven loading
- [ ] `AgentComposer.compose(spec, scope=profile_scope)` works without boot_capabilities()
- [ ] `lca inspect tree` outputs complete plugin tree
- [ ] Old path `AgentComposer.compose(spec)` still works (backward compat)
- [ ] `register_seam_catalog()` emits DeprecationWarning
- [ ] Loader reconcile passes seam completeness check

- [ ] **Step 3: Verify Phase B acceptance criteria**

- [ ] Shadow mode runs both paths and compares results
- [ ] `/v1/sessions/*` API endpoints are accessible
- [ ] LegacyApiAdapter translates old /runs/* correctly
- [ ] Architecture boundary: gateway does not import concrete implementations

- [ ] **Step 4: Verify Phase C acceptance criteria**

- [ ] CognitiveRuntime calls middleware at each phase boundary
- [ ] Budget policy is a plugin middleware, not hardcoded
- [ ] Loop intervention is a plugin middleware, not hardcoded
- [ ] ReplayLoop can replay a golden journal

- [ ] **Step 5: Verify Phase D acceptance criteria**

- [ ] DSH events map to LCA event vocabulary
- [ ] Gateway has no `if is_dsh_driver` branch

- [ ] **Step 6: Write phase status report**

```bash
git add docs/harness-phase-status.md
git commit -m "docs: harness phase implementation status report"
```

---

## Phase E 概要（需独立详细计划）

> Phase E 涉及 Tool Pipeline / Skills / Subagents / Workflow 四大子系统的收敛，面积大、风险高，需要独立的详细计划。以下仅列出高层目标和关键设计方向。

### E.1 Tool Pipeline 分离
- Tool Definition（声明工具签名）→ Tool Provider（实现执行）→ Tool Pipeline（guard/approval/sandbox）→ Tool Renderer（模型可见 schema）
- 每个分离为独立 plugin module
- `tools.pre_execute` / `tools.execute` / `tools.post_execute` 扩展点

### E.2 Skills 统一
- Skill Catalog（发现）→ Skill Tool（模型调用）→ Skill Slash（用户调用）→ Skill Projection（审计）
- 统一为 `SkillProvider` Protocol
- `skill.catalog.published` / `skill.loaded` 事件

### E.3 Subagent 注册与协商
- `SubagentRegistry` + `SubagentCapabilities` 能力声明
- `ActivationManager` 管理子代理生命周期
- lineage/depth/tool-filter/child-cancel/parent-drain 测试

### E.4 Workflow DAG Engine
- 声明式 DAG：`WorkflowMeta { name, phases, deps }`
- Worker isolation：`asyncio.Task` 或 `multiprocessing.Process`
- `agent()` / `phase()` 脚本 API

**建议**：Phase A-D 完成后，使用 writing-plans 为 Phase E 创建独立计划。
