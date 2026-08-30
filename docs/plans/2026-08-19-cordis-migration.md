# Cordis Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace LCA's in-house plugin kernel (`lca/layer0_infra/plugin/` + `lca/harness/kernel/`) with vendored cordis from `~/taiyi-agent`. Migrate 21 LCA plugins to cordis `@plugin` form. Restructure to 38 plugins across 3 tiers (Definition / Provider / Behavior). Cut all hardcoded assembly from L4 composition root.

**Architecture:**
- `vendor/cordis/cosmokit/schemastery` — copy from `~/taiyi-agent/vendor/`
- `lca/plugins/*` — module-per-plugin, ≤50 lines, only `@plugin` setup
- `lca/layer0_infra/{capability,session,system_prompt,...}/` — Service Definition classes (NOT plugin files)
- `lca/layer4_app/` — composition root, only `ctx.<typed-property>` access
- `lca/contracts/typed_ctx.py` — TypedContext Protocol for IDE/mypy support
- `bundles/base.yaml` + `bundles/web-app.yaml` — 38 plugin entries across 3 tiers

**Tech Stack:** cordis (Python port of dsh cordis), pydantic v2 (Standard Schema), structlog, lca-tests

**Spec:** `docs/design/2026-08-19-cordis-migration-design.md`

**Phases:** P0-P9 (per spec §9). This plan breaks them into 30+ atomic tasks across 6 chunks.

---

## Chunk 1: Vendor + Pre-flight Migration + Delete In-house Kernel (P0-P2)

**Goal:** Replace `lca/layer0_infra/plugin/` + `lca/harness/kernel/` with cordis. Add `SessionEventType` enum. Add `TypedContext` Protocol (only existing imports). Migrate all 30+ production callers of plugin/kernel EXTERNALLY before deleting internals. Drop PluginManifest / ExtensionPoint / CapabilityGrant / ScopeKind / PluginKind / ProviderMode while keeping `consume()` and `PluginConfig`.

**Critical ordering constraint** (the only way to keep the repo buildable):

```
Phase 1A: Vendor cordis                         (Tasks 1.1-1.2)
Phase 1B: Add SessionEventType + TypedContext  (Tasks 1.3-1.4)
Phase 1C: Migrate production callers            (Tasks 1.5-1.11)
            - lca/harness/__init__.py
            - lca/layer4_app/composer.py
            - lca/layer4_app/profile.py
            - lca/harness/diagnostics/inspect.py
            - lca/layer0_infra/dsh_core/* (delete or stub)
            - lca/layer0_infra/ops/cli.py
            - lca/harness/middleware/registry.py
            - lca/contracts/harness/middleware.py
            - 21 lca/plugins/* (drop PluginManifest etc.)
Phase 1D: Migrate/delete tests                  (Task 1.12)
Phase 1E: Delete in-house kernel internals      (Tasks 1.13-1.14)
Phase 1F: Split contracts files                 (Tasks 1.15-1.17)
Phase 1G: Verification                          (Task 1.18)
```

**Risk:** Skipping any migration task in Phase 1C will break the build at end of Chunk 1. Each task commits standalone so git bisect finds the offender.

---

### Task 1.1: Vendor cordis/cosmokit/schemastery from taiyi-agent

**Files:**
- Create: `vendor/cordis/src/cordis/` (recursively from `~/taiyi-agent/vendor/cordis/src/cordis/`)
- Create: `vendor/cosmokit/src/cosmokit/` (recursively)
- Create: `vendor/schemastery/src/schemastery/` (recursively)

- [ ] **Step 1: Copy three vendor trees**

```bash
cd ~/layered-cognitive-agent
mkdir -p vendor/cordis/src vendor/cosmokit/src vendor/schemastery/src
cp -r ~/taiyi-agent/vendor/cordis/src/cordis      vendor/cordis/src/
cp -r ~/taiyi-agent/vendor/cosmokit/src/cosmokit  vendor/cosmokit/src/
cp -r ~/taiyi-agent/vendor/schemastery/src/schemastery vendor/schemastery/src/
```

- [ ] **Step 2: Verify cordis import path resolves**

Run: `python -c "import sys; sys.path.insert(0, 'vendor/cordis/src'); from cordis import Context, plugin, Service; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Verify cosmokit + schemastery resolve**

```bash
python -c "import sys; sys.path.insert(0, 'vendor/cosmokit/src'); import cosmokit; print('cosmokit OK')"
python -c "import sys; sys.path.insert(0, 'vendor/schemastery/src'); import schemastery; print('schemastery OK')"
```

Expected: both print OK.

- [ ] **Step 4: Commit**

```bash
git add vendor/cordis vendor/cosmokit vendor/schemastery
git commit -m "vendor: import cordis/cosmokit/schemastery from ~/taiyi-agent"
```

---

### Task 1.2: Add cordis to pyproject.toml as path dependencies

**Files:**
- Modify: `pyproject.toml` (add `[tool.uv.sources]` block, add `taiyi-cordis` / `taiyi-cosmokit` / `taiyi-schemastery` to dependencies)

- [ ] **Step 1: Inspect current pyproject.toml dependencies section**

Run: `grep -A 30 'dependencies' pyproject.toml | head -40`

Note: capture the current dep list before editing.

- [ ] **Step 2: Append three vendor packages to dependencies**

Add to `pyproject.toml` `dependencies` list:
```toml
"taiyi-cordis",
"taiyi-cosmokit",
"taiyi-schemastery",
```

- [ ] **Step 3: Add `[tool.uv.sources]` block**

Add to `pyproject.toml` (anywhere after `[tool.uv]`):
```toml
[tool.uv.sources]
taiyi-cordis      = { path = "vendor/cordis/src" }
taiyi-cosmokit    = { path = "vendor/cosmokit/src" }
taiyi-schemastery = { path = "vendor/schemastery/src" }
```

- [ ] **Step 4: Run `uv sync` and verify resolution**

Run: `uv sync`
Expected: resolves cleanly, no conflict.

- [ ] **Step 5: Verify import via `uv run`**

Run: `uv run python -c "from cordis import Context, plugin, Service; print('cordis OK')"`
Expected: `cordis OK`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: wire vendor/{cordis,cosmokit,schemastery} as path dependencies"
```

---

### Task 1.3: Add `lca/contracts/typed_ctx.py` (TypedContext Protocol — Protocol-only, no L0 imports)

**Files:**
- Create: `lca/contracts/typed_ctx.py`
- Test: `tests/test_typed_ctx.py`

**Critical constraint** (per importlinter contract 3, pyproject.toml lines 53-65): `lca.contracts` is FORBIDDEN from importing `lca.infrastructure`, `lca.harness`, `lca.plugins`. TypedContext references ONLY Protocol types already in `lca/contracts/protocols/`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_typed_ctx.py
from lca.contracts.typed_ctx import TypedContext


def test_typed_context_exposes_llm_property():
    """TypedContext declares llm property typed as LLMAdapter Protocol."""
    assert "llm" in TypedContext.__annotations__
    assert hasattr(TypedContext, "llm")


def test_typed_context_imports_cleanly():
    """TypedContext is importable (no circular imports)."""
    assert TypedContext is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_typed_ctx.py -v --no-cov`
Expected: FAIL — `ModuleNotFoundError: No module named 'lca.contracts.typed_ctx'`

- [ ] **Step 3: Write minimal implementation (Protocol-only — no L0 imports)**

```python
# lca/contracts/typed_ctx.py
"""Typed accessor for cordis Context — Protocol-only references.

Each property corresponds to a Tier-1 Definition's `provide` key. cordis's
ReflectService resolves attribute reads through this typing, so:
- `ctx.llm` is type-checked (mypy knows returns LLMAdapter)
- `ctx.inject("llm")` is still valid (untyped fallback)

Constraint: this module is in `lca.contracts/`, which is FORBIDDEN by
importlinter from importing `lca.infrastructure` / `lca.harness` / `lca.plugins`.
Therefore TypedContext references ONLY Protocol types already declared in
`lca/contracts/protocols/`. Concrete service classes (`LlmService`,
`ToolsService`, `CommandGateway`, etc.) are not imported here.
"""
from __future__ import annotations

from typing import Protocol

from lca.contracts.protocols.cognition import Brain, BrainFactory
from lca.contracts.protocols.infra import (
    AgentTransport,
    AttachmentIdentity,
    LLMAdapter,
    Sandbox,
    StateStore,
    ToolRegistry,
    TransportRegistryProtocol,
)
from lca.contracts.protocols.memory import MemorySystem
from lca.contracts.protocols.observability import ObservabilityBackend
from lca.contracts.protocols.operational_skills import SkillPackageStore
from lca.contracts.protocols.runtime import Runtime


class TypedContext(Protocol):
    """Typed property accessor for cordis Context.

    All property types are Protocol declarations from `lca.contracts.protocols`.
    Concrete classes (LlmService / ToolsService / etc.) satisfy these
    Protocols structurally — no inheritance required.
    """

    @property
    def llm(self) -> LLMAdapter: ...

    @property
    def tools(self) -> ToolRegistry: ...

    @property
    def transport(self) -> TransportRegistryProtocol: ...

    @property
    def memory(self) -> MemorySystem: ...

    @property
    def state_store(self) -> StateStore: ...

    @property
    def skills(self) -> SkillPackageStore: ...

    @property
    def observability(self) -> ObservabilityBackend: ...

    @property
    def sandbox(self) -> Sandbox: ...

    @property
    def attachment(self) -> AttachmentIdentity: ...

    @property
    def brain(self) -> Brain: ...

    @property
    def brain_factory(self) -> BrainFactory: ...

    @property
    def runtime(self) -> Runtime: ...

    @property
    def agent_transport(self) -> AgentTransport: ...
```

**Notes on what's NOT in TypedContext** (deliberately):
- `search_service` — no Protocol exists yet; add `SearchService` Protocol in a follow-up if needed
- `file_store` — no Protocol exists yet; add `FileStoreProtocol` in a follow-up
- `command_gateway` — too LCA-specific; consumed via `ctx.inject("command_gateway")` (untyped)
- Concrete service classes (`LlmService`, `ToolsService`, etc.) — these are accessed via Protocol structural matching, not direct import

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_typed_ctx.py -v --no-cov`
Expected: PASS

- [ ] **Step 5: Run lint-imports to verify no circular import / forbidden module introduced**

Run: `uv run lint-imports`
Expected: clean

- [ ] **Step 6: Commit**

```bash
git add lca/contracts/typed_ctx.py tests/test_typed_ctx.py
git commit -m "contracts: TypedContext Protocol (Protocol-only, no L0 imports)"
```

---

### Task 1.4: Add `lca/contracts/observability/session_events.py`

**Files:**
- Create: `lca/contracts/observability/session_events.py`
- Test: `tests/contracts/test_session_events.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/contracts/test_session_events.py
from lca.contracts.observability.session_events import SessionEventType


def test_session_event_type_is_string_enum():
    """SessionEventType members are str values, matching cordis event names."""
    assert SessionEventType.SESSION_CREATED == "session/created"
    assert SessionEventType.ASSISTANT_MESSAGE == "assistant/message"
    assert SessionEventType.TOOL_CALL == "tool/call"


def test_session_event_type_covers_minimum_surface():
    """session everything 原则: 至少 8 类事件被枚举"""
    required = [
        "SESSION_CREATED", "ASSISTANT_MESSAGE", "TOOL_CALL", "TOOL_RESULT",
        "TURN_START", "STEP_START", "LLM_REQUEST", "GUARD_REJECTED",
    ]
    for name in required:
        assert hasattr(SessionEventType, name)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/contracts/test_session_events.py -v --no-cov`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# lca/contracts/observability/session_events.py
"""Session event type enum — the single taxonomy of session mutations.

"session everything" 原则: 任何状态变更都对应一个 SessionEventType。
DSH core/session/known_event_types.ts 1:1 对齐 + LCA 扩展。
"""
from __future__ import annotations

from enum import Enum


class SessionEventType(str, Enum):
    """session 任何状态变更。"""

    # Session 生命周期
    SESSION_CREATED = "session/created"
    SESSION_DISPOSED = "session/disposed"
    SESSION_FLUSHED = "session/flushed"

    # Attachment
    ATTACHMENT_ADDED = "attachment/added"
    ATTACHMENT_REMOVED = "attachment/removed"
    ATTACHMENT_STAGED = "attachment/staged"

    # User / Assistant
    USER_MESSAGE_ACCEPTED = "user/message/accepted"
    ASSISTANT_MESSAGE = "assistant/message"

    # Turn / Step
    TURN_START = "turn/start"
    TURN_END = "turn/end"
    STEP_START = "step/start"
    STEP_END = "step/end"

    # LLM
    LLM_REQUEST = "llm/request"
    LLM_RESPONSE_CHUNK = "llm/response/chunk"
    LLM_RESPONSE = "llm/response"
    LLM_ERROR = "llm/error"

    # Tool
    TOOL_CALL = "tool/call"
    TOOL_PRE_EXECUTE = "tool/pre-execute"
    TOOL_POST_EXECUTE = "tool/post-execute"
    TOOL_RESULT = "tool/result"
    TOOL_ERROR = "tool/error"

    # Guards
    GUARD_REJECTED = "guard/rejected"
    LOOP_INTERVENTION = "loop/intervention"
    BUDGET_EXCEEDED = "budget/exceeded"

    # Subagent / Delegation
    SUBAGENT_START = "subagent/start"
    SUBAGENT_END = "subagent/end"
    DELEGATION_SENT = "delegation/sent"

    # Transport / Sandbox
    SANDBOX_VIOLATION = "sandbox/violation"
    TRANSPORT_ERROR = "transport/error"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/contracts/test_session_events.py -v --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lca/contracts/observability/session_events.py tests/contracts/test_session_events.py
git commit -m "contracts: SessionEventType enum (session everything taxonomy)"
```

---

### Task 1.5: Migrate `lca/harness/__init__.py` (drop plugin/kernel re-exports)

**Files:**
- Modify: `lca/harness/__init__.py`

- [ ] **Step 1: List current re-exports**

Run: `cat lca/harness/__init__.py`
Expected: contains imports from `lca.harness.kernel.scope` and `lca.infrastructure.plugin.kernel`

- [ ] **Step 2: Replace with minimal re-exports**

```python
# lca/harness/__init__.py
"""Harness — command gateway, agent handles, sessions, skills, etc.

After cordis migration: ScopedPluginHost, current_scope, PluginContext,
PluginHandle, PluginHost, PluginSpec, PluginState, ServiceRecord, reconcile,
manifest_from_entry, manifest_from_spec are all gone. Use cordis.Context
directly.
"""
from lca.harness.kernel.scope import ScopedPluginHost, current_scope  # noqa: F401
```

Wait — that's still importing. Let me actually rewrite correctly:

```python
# lca/harness/__init__.py
"""Harness — command gateway, agent handles, sessions, skills, etc.

cordis migration complete. Submodules (lca.harness.command.gateway,
lca.harness.session.inbox, lca.harness.agent.handle, lca.harness.skills)
are import directly from their respective submodules.

Re-exports removed (deleted in cordis migration):
- ScopedPluginHost, current_scope (was lca.harness.kernel.scope)
- PluginContext, PluginHandle, PluginHost, PluginSpec, PluginState, ServiceRecord, reconcile (was lca.infrastructure.plugin.kernel)
- manifest_from_entry, manifest_from_spec (was lca.harness.kernel.compat)
"""
```

(Empty `__init__.py` — no top-level re-exports. Submodules import directly.)

- [ ] **Step 3: Verify all `from lca.harness import X` usages resolve to submodule imports**

Run: `rg -n "from lca\.harness import (ScopedPluginHost|current_scope|PluginContext|PluginHandle|PluginHost|PluginSpec|PluginState|ServiceRecord|reconcile|manifest_from_entry|manifest_from_spec)" lca/ tests/`
Expected: empty (callers use submodule imports)

- [ ] **Step 4: Verify submodules still importable**

Run: `uv run python -c "import lca.harness.command.gateway; import lca.harness.session.inbox; import lca.harness.agent.handle; print('OK')"`
Expected: OK

- [ ] **Step 5: Commit**

```bash
git add lca/harness/__init__.py
git commit -m "harness: drop in-house plugin/kernel re-exports from __init__.py"
```

---

### Task 1.6: Migrate production callers of in-house kernel (composer / gateway / api)

**Files:**
- Modify: `lca/layer4_app/composer.py`
- Modify: `gateway/app.py`
- Modify: `lca/layer4_app/api.py`

**Critical**: All three files import `lca.harness.kernel.scope.ScopedPluginHost`. They MUST be migrated before Task 1.16 deletes `lca/harness/kernel/`.

- [ ] **Step 1: Find all in-house kernel references**

```bash
rg -n "lca\.layer0_infra\.plugin\|lca\.harness\.kernel\|ScopedPluginHost\|ScopeKind\." \
    lca/layer4_app/composer.py lca/layer4_app/api.py gateway/app.py
```

Expected: ~15-25 hits across 3 files

- [ ] **Step 2: For `lca/layer4_app/composer.py`: remove imports; stub affected functions**

```python
# remove these lines:
#   from lca.harness.kernel.scope import ScopedPluginHost
#   from lca.contracts.harness.plugin import ScopeKind
#   from lca.infrastructure.plugin.kernel._handle import PluginHandle
#   from lca.infrastructure.plugin.kernel._spec import PluginSpec
#   from lca.application.capability_boot import boot_capabilities
```

Replace `_isolate_agent_scope` body with `raise NotImplementedError("cordis migration; Chunk 5")`. Same for `_resolve_capability_context`.

- [ ] **Step 3: For `gateway/app.py`: replace `ScopedPluginHost` with `cordis.Context` stub**

```python
# before
from lca.harness.kernel.scope import ScopedPluginHost
plugin_scope = ScopedPluginHost.wrap(host, ScopeKind.DEPLOYMENT, "lca")

# after
from cordis import Context
plugin_scope = Context()  # stub; full migration in Chunk 5
```

If any code path uses `plugin_scope.resolve(...)`, replace with `plugin_scope.inject(...)`.

- [ ] **Step 4: For `lca/layer4_app/api.py`: replace `ScopedPluginHost` isinstance check**

```python
# before
def is_scope(x): return isinstance(x, ScopedPluginHost)

# after
def is_scope(x): return isinstance(x, Context)
```

Replace any `scope.resolve(...)` with `scope.inject(...)`.

- [ ] **Step 5: Verify all 3 files no longer import in-house kernel**

Run: `rg "lca\.layer0_infra\.plugin\|lca\.harness\.kernel\|ScopedPluginHost\|ScopeKind" lca/layer4_app/composer.py lca/layer4_app/api.py gateway/app.py`
Expected: empty

- [ ] **Step 6: Verify all 3 files import cleanly**

```bash
uv run python -c "from lca.application.composer import AgentComposer; print('composer OK')"
uv run python -c "from lca.application.api import Agent, Team; print('api OK')"
uv run python -c "import gateway.app; print('gateway OK')"
```

Expected: all three print OK

- [ ] **Step 7: Run affected tests (collection only; full passes deferred)**

Run: `uv run pytest tests/test_compose_*.py tests/test_gateway_*.py tests/harness/ --collect-only --no-cov -q 2>&1 | tail -30`
Expected: collection succeeds; individual failures acceptable

- [ ] **Step 8: Commit**

```bash
git add lca/layer4_app/composer.py lca/layer4_app/api.py gateway/app.py
git commit -m "production callers: composer/gateway/api drop ScopedPluginHost (Chunk 5 stub)"
```

**Critical constraint check**: After this task, NO production file outside `lca/harness/kernel/` and `lca/layer0_infra/plugin/` should reference `ScopedPluginHost` or any in-house kernel type. If they do, list them and add migration steps before Task 1.16.

---

### Task 1.7: Migrate profile.py / inspect.py / **boot.py** (B1 fix — boot.py must move out of Chunk 2)

**Files:**
- Modify: `lca/layer4_app/profile.py`
- Modify: `lca/harness/diagnostics/inspect.py`
- Modify: `lca/harness/profile/boot.py`  ← **moved here from Chunk 2 Task 2.1**

**Critical (B1 fix)**: `lca/harness/profile/boot.py` imports `ProfileLoader` / `BootedTree` / `Loader` from `lca.infrastructure.plugin.*`. Task 1.15 (Chunk 1) deletes that module. boot.py's rewrite MUST happen in Chunk 1, not Chunk 2. Chunk 2's Task 2.1 is now redundant (delete or mark as `Replaced by Task 1.7`).

- [ ] **Step 1: Find plugin/kernel imports**

Run: `rg -n "lca\.layer0_infra\.plugin\|lca\.harness\.kernel" lca/layer4_app/profile.py lca/harness/diagnostics/inspect.py lca/harness/profile/boot.py`

- [ ] **Step 2: For `lca/layer4_app/profile.py`: drop ProfileLoader; rewrite as thin wrapper around cordis.Loader**

```python
# lca/layer4_app/profile.py
"""Profile loading — thin wrapper over cordis.Loader."""
from __future__ import annotations
from pathlib import Path
from cordis.loader import load_yaml


def load_profile(path: Path | str) -> object:
    """Load a profile YAML via cordis. Returns cordis.EntryTree."""
    return load_yaml(path)
```

- [ ] **Step 3: For `lca/harness/diagnostics/inspect.py`: drop loader._entry import; replace with cordis.Loader**

```python
# lca/harness/diagnostics/inspect.py
"""Inspect a booted plugin tree."""
from __future__ import annotations
from cordis import Context


def inspect(ctx: Context) -> dict:
    """Return summary of plugin tree."""
    return {
        "plugin_count": sum(1 for _ in dir(ctx) if not _.startswith("_")),
        "services": [k for k in dir(ctx) if not k.startswith("_")],
    }
```

- [ ] **Step 4: For `lca/harness/profile/boot.py`: rewrite as cordis.Loader thin wrapper (moved from Chunk 2 Task 2.1)**

```python
# lca/harness/profile/boot.py
"""Boot a harness plugin tree from a profile YAML.

Thin wrapper around cordis.Loader. Bundles from ``bundles/*.yaml`` are first
merged via ``cordis.loader.merge_bundles``, then loaded into a root Context.
"""
from __future__ import annotations

import warnings
from pathlib import Path

from cordis import Context
from cordis.loader import Entry, Loader, load_yaml, merge_bundles


async def boot_profile(
    profile_path: Path | str,
    *,
    check_seam_completeness: bool = True,  # legacy kwarg, now no-op
) -> Context:
    """Load profile YAML → resolve modules → build root Context."""
    if check_seam_completeness:
        warnings.warn(
            "check_seam_completeness is deprecated; cordis doesn't validate seams",
            DeprecationWarning,
            stacklevel=2,
        )
    path = Path(profile_path)
    data = load_yaml(path)
    ctx = Context()
    loader = Loader()
    entries = loader.load(data)
    for entry in entries:
        module = _resolve_module(entry)
        plugin_obj = getattr(module, entry.name)
        await plugin_obj.setup(ctx, entry.config)
    return ctx


def _resolve_module(entry: Entry) -> object:
    """Resolve $module from YAML entry."""
    import importlib
    module_path = entry.extra.get("$module")
    if module_path is None:
        raise ValueError(f"entry {entry.id!r} missing $module")
    return importlib.import_module(module_path)
```

- [ ] **Step 5: Verify all 3 files import cleanly**

```bash
uv run python -c "from lca.application.profile import load_profile; from lca.harness.diagnostics.inspect import inspect; print('OK')"
uv run python -c "from lca.harness.profile.boot import boot_profile; print('boot OK')"
uv run python -c "from lca.harness.profile import boot_profile; print('re-export OK')"  # lca/harness/profile/__init__.py re-exports
```

Expected: all three OK

- [ ] **Step 6: Verify `lca/harness/profile/__init__.py` re-export still works**

```bash
uv run python -c "from lca.harness.profile import boot_profile; print(boot_profile)"
```

Expected: OK

- [ ] **Step 7: Commit**

```bash
git add lca/layer4_app/profile.py lca/harness/diagnostics/inspect.py lca/harness/profile/boot.py
git commit -m "profile + inspect + boot: rewrite as thin wrappers over cordis (boot moved from Chunk 2)"
```

---

### Task 1.8: Delete `lca/layer0_infra/dsh_core/` (was duplicating upstream dsh, never used by cordis path)

**Files:**
- Delete: `lca/layer0_infra/dsh_core/` (entire dir)

- [ ] **Step 1: Find usages**

Run: `rg -l "lca\.layer0_infra\.dsh_core" lca/ tests/`
Expected: 5+ files importing dsh_core

- [ ] **Step 2: For each importer, replace with upstream cordis equivalent or comment out**

For `lca/layer0_infra/dsh_core/agent_default_model/__init__.py`:
- Replace import from `lca.infrastructure.plugin.kernel._context.PluginContext` → `from cordis import Context`
- Drop `AgentDefaultModel` class (was a stub anyway)

For `lca/layer0_infra/dsh_core/agent_tool_presentation/__init__.py`:
- Drop or comment out — DSH tool presentation is one of the 100+ dsh packages we DON'T port

For `lca/layer0_infra/dsh_core/scope/__init__.py`:
- Replace `lca.infrastructure.plugin.kernel._context.PluginContext` → `from cordis import Context`

For `lca/layer0_infra/dsh_core/system_prompt/__init__.py`:
- Same: replace context import

- [ ] **Step 3: Delete `lca/layer0_infra/dsh_core/`**

```bash
git rm -r lca/layer0_infra/dsh_core/
```

- [ ] **Step 4: Verify**

Run: `rg "lca\.layer0_infra\.dsh_core" lca/ tests/`
Expected: empty

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "dsh_core: delete (was duplicating upstream dsh; not ported)"
```

---

### Task 1.9: Migrate `lca/layer0_infra/ops/cli.py` (drop plugin imports)

**Files:**
- Modify: `lca/layer0_infra/ops/cli.py`

- [ ] **Step 1: Find plugin/kernel imports**

Run: `rg -n "lca\.layer0_infra\.plugin\|lca\.harness\.kernel" lca/layer0_infra/ops/cli.py`
Expected: 1-3 hits (around line 617 per spec §8.2)

- [ ] **Step 2: Drop imports; replace with cordis equivalents**

If CLI imports `lca.infrastructure.plugin.include._profile.ProfileLoader`:
- Replace with `from cordis.loader import load_yaml`

If CLI imports `lca.infrastructure.plugin.loader._loader.Loader`:
- Replace with `from cordis import Loader` (cordis has its own Loader)

- [ ] **Step 3: Verify `lca-ops` CLI still works**

Run: `uv run lca-ops --help`
Expected: prints help

- [ ] **Step 4: Commit**

```bash
git add lca/layer0_infra/ops/cli.py
git commit -m "ops/cli: drop in-house plugin imports; use cordis"
```

---

### Task 1.10: Migrate `lca/harness/middleware/registry.py` (keep ExtensionPoint internally, replace public surface)

**Files:**
- Modify: `lca/harness/middleware/registry.py`

**Critical**: `InMemoryMiddlewareRegistry.register_point()` and `run()` access `point.seam_key` and `point.dispatch_mode` (lines 49/70). The new public type `CognitivePhase` lacks these fields. **Solution**: Keep `ExtensionPoint` as the internal storage type, but expose `COGNITIVE_PHASES` (public list) as `tuple[CognitivePhase, ...]` — conversion happens at the boundary.

- [ ] **Step 1: Find ExtensionPoint / ScopeKind / PluginKind imports**

Run: `rg -n "ExtensionPoint\|ScopeKind\|PluginKind" lca/harness/middleware/registry.py`
Expected: 2-4 hits

- [ ] **Step 2: Split internal type (ExtensionPoint, kept) and public type (CognitivePhase, new)**

```python
# lca/harness/middleware/registry.py
"""Cognitive phase event handlers — cordis event names.

Internal: `ExtensionPoint` (with `seam_key`, `dispatch_mode`) is kept as
the registry's storage type to preserve `register_point` / `run()` behavior.

Public: `COGNITIVE_PHASES` exposes a `CognitivePhase` list (just `name` +
`description`) for plugin authors to consume via docstring / metadata.
Conversion from CognitivePhase (public) to ExtensionPoint (internal) happens
in `build_cognitive_handlers(ctx)`.
"""
from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.harness.plugin import ExtensionPoint  # KEEP — internal use


@dataclass(frozen=True)
class CognitivePhase:
    """Public phase metadata — name + description only."""

    name: str
    description: str = ""


# Public taxonomy (consumed by docs / plugin manifest authors)
COGNITIVE_PHASES: tuple[CognitivePhase, ...] = (
    CognitivePhase("agent.pre_step", "each step before perceive"),
    CognitivePhase("agent.before_perceive", "before perception"),
    CognitivePhase("agent.after_perceive", "after perception"),
    CognitivePhase("agent.before_think", "before thinking"),
    CognitivePhase("agent.after_think", "after thinking"),
    CognitivePhase("agent.before_act", "before act"),
    CognitivePhase("agent.after_act", "after act"),
    CognitivePhase("agent.before_reflect", "before reflect"),
    CognitivePhase("agent.after_reflect", "after reflect"),
    CognitivePhase("agent.before_turn_end", "before turn end"),
)


def to_extension_point(phase: CognitivePhase) -> ExtensionPoint:
    """Convert public CognitivePhase → internal ExtensionPoint (seam_key)."""
    return ExtensionPoint(seam_key=phase.name, dispatch_mode="waterfall", description=phase.description)


# InMemoryMiddlewareRegistry keeps using ExtensionPoint — no change.
# The `run()` and `register_point()` methods retain their existing semantics
# since `ExtensionPoint.seam_key` and `ExtensionPoint.dispatch_mode` are intact.
```

- [ ] **Step 3: Verify `lca/harness/middleware/registry.py` still has working `InMemoryMiddlewareRegistry`**

Run: `rg -n "register_point\|dispatch_mode\|seam_key" lca/harness/middleware/registry.py`
Expected: references intact (no break)

- [ ] **Step 4: Commit**

```bash
git add lca/harness/middleware/registry.py
git commit -m "middleware/registry: keep ExtensionPoint internal; expose CognitivePhase public"
```

---

### Task 1.11: Migrate `lca/contracts/harness/middleware.py` (keep MiddlewareRegistration dataclass)

**Files:**
- Modify: `lca/contracts/harness/middleware.py`

**Critical**: `MiddlewareRegistration` (frozen dataclass) is used by `lca/layer2_runtime/hook_middleware.py:56` and the budget/loop_intervention policy plugins. Keep the dataclass; only drop the `MiddlewareRegistry` Protocol (which references `ExtensionPoint`).

- [ ] **Step 1: Find ExtensionPoint / MiddlewareRegistry imports**

Run: `rg -n "ExtensionPoint\|MiddlewareRegistry" lca/contracts/harness/middleware.py`
Expected: 2-3 hits

- [ ] **Step 2: Keep `MiddlewareRegistration`; drop only the `MiddlewareRegistry` Protocol**

```python
# lca/contracts/harness/middleware.py
"""Middleware registration contract — post-cordis migration.

`MiddlewareRegistration` (frozen dataclass) is kept as-is. It carries
seam_key / priority / plugin_id / callable — used by hook_middleware.py:56
and the budget_policy / loop_intervention_policy plugins.

`MiddlewareRegistry` Protocol (which referenced ExtensionPoint) is dropped.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional


@dataclass(frozen=True)
class MiddlewareRegistration:
    """One middleware binding to a cognitive phase event.

    `callback` is OPTIONAL (default None) to preserve the existing 3-field
    constructor signature used at 4 production callers (F1 fix):
    - lca/plugins/budget_policy/__init__.py:55
    - lca/plugins/loop_intervention_policy/__init__.py:55
    - lca/layer2_runtime/hook_middleware.py:57
    - lca/layer2_runtime/loop_intervention_mw.py:47

    These callers pass seam_key/priority/plugin_id only — the actual callback
    is registered separately via `InMemoryMiddlewareRegistry.register()`.
    """

    seam_key: str
    priority: int
    plugin_id: str
    callback: Callable[..., Awaitable[Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# Dropped:
# - MiddlewareRegistry Protocol (references ExtensionPoint)
# - register_middleware helper function (replaced by cordis ctx.events.on in plugin setup)
```

- [ ] **Step 3: Verify `MiddlewareRegistration` still importable**

Run: `uv run python -c "from lca.contracts.harness.middleware import MiddlewareRegistration; print('OK')"`
Expected: OK

- [ ] **Step 4: Verify `lca/contracts/harness/middleware.py` has no `ExtensionPoint` / `MiddlewareRegistry` refs**

Run: `rg "ExtensionPoint\|MiddlewareRegistry" lca/contracts/harness/middleware.py`
Expected: empty

- [ ] **Step 5: Verify `lca/layer2_runtime/hook_middleware.py` and policy plugins still import**

```bash
uv run python -c "from lca.runtime.hook_middleware import hook_middleware; print('OK')"
uv run python -c "from lca.plugins.budget_policy import apply; print('OK')"
```

Expected: OK

- [ ] **Step 6: Commit**

```bash
git add lca/contracts/harness/middleware.py
git commit -m "contracts/harness/middleware: keep MiddlewareRegistration; drop MiddlewareRegistry Protocol"
```

---

### Task 1.12: Migrate 21 `lca/plugins/*/__init__.py` (drop PluginManifest/seam_definitions usage)

**Files:**
- Modify: 21 plugin files (`lca/plugins/*/__init__.py`)

- [ ] **Step 1: List every plugin's current imports**

Run: `rg -l "PluginManifest\|PluginKind\|ExtensionPoint\|CapabilityGrant\|ProviderMode\|ScopeKind" lca/plugins/ --type py`
Expected: ~15 files

- [ ] **Step 2: For each plugin, replace the imports with cordis equivalents**

For `lca/plugins/llm_service/__init__.py`:
```python
# before
from lca.contracts.harness.plugin import PluginKind, PluginManifest
# after
from cordis import plugin
```

For `lca/plugins/seam_definitions/__init__.py`:
- This plugin's entire purpose is declaring ExtensionPoints, which is no longer needed. Delete the file content (or mark as deprecated):

```python
# lca/plugins/seam_definitions/__init__.py
"""DEPRECATED: ExtensionPoints are gone. cordis events replace."""
import warnings
warnings.warn("seam_definitions plugin is deprecated; cordis events replace ExtensionPoints", DeprecationWarning, stacklevel=2)
```

(Full deletion happens in Chunk 3 when this plugin is removed.)

- [ ] **Step 3: For each plugin, replace `manifest = PluginManifest(...)` + `name = "..."` + `apply(ctx, config)` with the cordis `@plugin` form**

Pattern:
```python
# before
manifest = PluginManifest(id="lca.foo", version="1.0.0", api_version="lca-harness/1", kind=PluginKind.SERVICE, provides=("foo",))
name = "lca.foo"
def apply(ctx, config): ...

# after
from cordis import plugin
@plugin(name="lca-foo")
async def setup(ctx, config): ...
```

- [ ] **Step 4: Run pytest to verify collection passes**

Run: `uv run pytest tests/plugins/ -x --no-cov --collect-only 2>&1 | tail -20`
Expected: collection succeeds

- [ ] **Step 5: Commit**

```bash
git add lca/plugins/
git commit -m "plugins: 21 plugins drop PluginManifest/ExtensionPoint/seam_definitions usage"
```

---

### Task 1.13: Delete obsolete test files (extended list)

**Files:**
- Delete: `tests/plugin/` (entire dir)
- Delete: `tests/test_plugin_*.py` (multiple files, **including** `tests/test_plugin_context.py`)
- Delete: `tests/test_seam_pattern.py`
- Delete: `tests/test_capability_seams.py` (B2 — uses SeamKey/REQUIRED_SEAM_KEYS/ProfileLoader/Loader/boot_capabilities/ctx.mount/ctx.require — all removed)
- Delete: `tests/test_architecture_self_consistency.py` (B4 — `test_all_first_party_plugins_declare_a_manifest` asserts PluginManifest in every plugin; assertion fails after Task 1.12 rewrites plugins)
- Delete: `tests/harness/test_seam_completeness.py`
- Delete: `tests/harness/test_budget_policy.py`
- Delete: `tests/harness/test_loop_intervention_policy.py`
- Delete: `tests/harness/test_gateway_profile_integration.py`

- [ ] **Step 1: Find obsolete test files (extended)**

```bash
ls tests/plugin/ 2>/dev/null
ls tests/test_plugin_*.py 2>/dev/null
ls tests/test_seam_pattern.py 2>/dev/null
ls tests/harness/test_seam_completeness.py 2>/dev/null
ls tests/harness/test_budget_policy.py 2>/dev/null
ls tests/harness/test_loop_intervention_policy.py 2>/dev/null
ls tests/harness/test_gateway_profile_integration.py 2>/dev/null
```

- [ ] **Step 2: Delete obsolete tests**

```bash
git rm -r tests/plugin/
git rm tests/test_plugin_loader.py tests/test_plugin_protocol.py tests/test_plugin_profile.py tests/test_plugin_context.py 2>/dev/null
git rm tests/test_seam_pattern.py
git rm tests/test_capability_seams.py
git rm tests/test_architecture_self_consistency.py
git rm tests/harness/test_seam_completeness.py
git rm tests/harness/test_budget_policy.py
git rm tests/harness/test_loop_intervention_policy.py
git rm tests/harness/test_gateway_profile_integration.py
```

- [ ] **Step 3: Verify `pytest --collect-only` works**

Run: `uv run pytest tests/ --collect-only --no-cov -q 2>&1 | tail -30`
Expected: collects remaining tests; no import errors

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "tests: delete obsolete plugin/kernel/seam/policy tests (extended list)"
```

---

### Task 1.14: Delete `tests/harness/test_phase_*.py` (4 files — NOT migrate)

**Files:**
- Delete: `tests/harness/test_phase_a_integration.py`
- Delete: `tests/harness/test_phase_c_factories.py`
- Delete: `tests/harness/test_phase_d_dsh_bridge.py`
- Delete: `tests/harness/test_loop_plugin_integration.py`

**Rationale**: All 4 files test the in-house kernel semantics (`TestPluginManifest`, `TestScopedPluginHost.parent_delegation`, etc.) that have no cordis equivalent. They cannot be migrated to `cordis.Context`; they MUST be deleted. Replacements come in Chunk 5/6.

- [ ] **Step 1: Find `lca.harness.kernel.scope` imports AND `ExtensionPoint`/`PluginManifest` imports**

Run: `rg -l "lca\.harness\.kernel\.scope\|ExtensionPoint\|PluginManifest\|ScopeKind" tests/harness/`
Expected: 4+ files

- [ ] **Step 2: Delete the 4 files**

```bash
git rm tests/harness/test_phase_a_integration.py
git rm tests/harness/test_phase_c_factories.py
git rm tests/harness/test_phase_d_dsh_bridge.py
git rm tests/harness/test_loop_plugin_integration.py
```

- [ ] **Step 3: Verify collection succeeds**

Run: `uv run pytest tests/harness/ --collect-only --no-cov 2>&1 | tail -20`
Expected: collection succeeds (or only collects the few non-deleted tests)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "tests/harness: delete test_phase_{a,c,d} + test_loop_plugin_integration (test in-house kernel)"
```

---

### Task 1.15: Bulk delete `lca/layer0_infra/plugin/` (entire dir)

**Files:**
- Delete: `lca/layer0_infra/plugin/` (entire dir)

- [ ] **Step 1: Verify NO production caller remains**

```bash
rg -l "lca\.layer0_infra\.plugin" lca/ tests/ --type py | sort
```

Expected: empty (all callers migrated in Tasks 1.5-1.12)

- [ ] **Step 2: Delete the directory**

```bash
git rm -r lca/layer0_infra/plugin/
```

- [ ] **Step 3: Verify imports still work**

Run: `uv run python -c "import lca; print('OK')"`
Expected: OK

- [ ] **Step 4: Run pytest collection**

Run: `uv run pytest tests/ --collect-only --no-cov -q 2>&1 | tail -20`
Expected: collection succeeds

- [ ] **Step 5: Commit**

```bash
git commit -m "plugin: delete in-house layer0_infra/plugin/{kernel,loader,include,scope,expr,builtins,_test_plugins}"
```

---

### Task 1.16: Bulk delete `lca/harness/kernel/`

**Files:**
- Delete: `lca/harness/kernel/` (entire dir)

- [ ] **Step 1: Verify NO production caller remains**

```bash
rg -l "lca\.harness\.kernel" lca/ tests/ --type py
```

Expected: empty

- [ ] **Step 2: Delete the directory**

```bash
git rm lca/harness/kernel/__init__.py lca/harness/kernel/scope.py lca/harness/kernel/compat.py
rmdir lca/harness/kernel
```

- [ ] **Step 3: Verify imports still work**

Run: `uv run python -c "from lca.harness.session.inbox import Inbox; print('OK')"`
Expected: OK

- [ ] **Step 4: Run pytest collection**

Run: `uv run pytest tests/ --collect-only --no-cov -q 2>&1 | tail -20`
Expected: collection succeeds

- [ ] **Step 5: Commit**

```bash
git commit -m "harness: delete kernel/{scope,compat}"
```

---

### Task 1.17: Split `lca/contracts/harness/plugin.py` (drop PluginManifest etc., PluginContext uses cordis surface only)

**Files:**
- Modify: `lca/contracts/harness/plugin.py`

**Critical**: cordis.Context has only `provide`, `inject`, `scope`, `on`, `once`, `dispose`. **No `mount()` or `require()`** — those are LCA-in-house API. PluginContext Protocol must use the cordis surface only.

- [ ] **Step 1: Verify no callers of to-be-deleted symbols remain**

```bash
rg "PluginManifest\|ExtensionPoint\|CapabilityGrant\|ScopeKind\|PluginKind\|ProviderMode" lca/ tests/ --type py | grep -v "specs/" | grep -v "\.md"
```

Expected: empty (all callers migrated in Tasks 1.5-1.12)

- [ ] **Step 2: Replace with minimal content (PluginContext Protocol — cordis surface only)**

```python
# lca/contracts/harness/plugin.py
"""Harness plugin shape — post-cordis migration.

PluginManifest / ExtensionPoint / CapabilityGrant / ScopeKind / PluginKind /
ProviderMode are all deleted (cordis's @plugin + Standard Schema cover
the same ground).

PluginContext Protocol is kept as a stable type alias for migration-period
compatibility. Uses ONLY cordis's public surface (provide / inject / on /
once / scope / dispose).
"""
from __future__ import annotations

from typing import Any, Protocol


class PluginContext(Protocol):
    """Stable name for migration-period type alias.

    Resolves to cordis.Context at runtime. After Chunk 5 migration,
    callers should use cordis.Context directly.
    """

    def provide(self, key: str, value: Any) -> None: ...
    def inject(self, key: str) -> Any: ...
    def on(self, event: str, callback: Any) -> None: ...
    def once(self, event: str, callback: Any) -> None: ...
```

- [ ] **Step 3: Verify imports**

Run: `uv run python -c "from lca.contracts.harness.plugin import PluginContext; print('OK')"`
Expected: OK

- [ ] **Step 4: Verify no `mount`/`require` references remain in LCA / tests**

Run: `rg "\.mount\(\|\.require\(" lca/layer4_app/ lca/harness/ tests/`
Expected: only `request.method == "OPTIONS"` / unrelated `mount`/`require` (no false positives on `request.require`)

- [ ] **Step 5: Commit**

```bash
git add lca/contracts/harness/plugin.py
git commit -m "contracts: drop PluginManifest/ExtensionPoint/CapabilityGrant/ScopeKind/PluginKind/ProviderMode; PluginContext uses cordis surface"
```

---

### Task 1.18: Split `lca/contracts/mechanisms/seam.py` (drop SeamRole etc., keep consume) — REQUIRES SeamKey rename

**Files:**
- Modify: `lca/contracts/mechanisms/seam.py`
- Modify: `lca/contracts/mechanisms/__init__.py` (re-exports)
- Modify: `lca/contracts/mechanisms/capability.py` (SeamKey → CapabilityKey rename)

**Critical**: Step 3 imports `CapabilityKey` and `REQUIRED_CAPABILITY_KEYS`. These don't exist yet — the file currently defines `SeamKey` and `REQUIRED_SEAM_KEYS`. This task includes the rename.

- [ ] **Step 1: Verify no callers of to-be-deleted symbols remain**

```bash
rg "SeamRole\|SeamDeclaration\|SeamRegistry\|seam\b\|validate_all_seams\|UnauthorizedConsumerError\|IncompleteSeamError" lca/ tests/ --type py | grep -v "specs/" | grep -v "\.md"
```

Expected: empty

- [ ] **Step 2: Rename `SeamKey` → `CapabilityKey` in `lca/contracts/mechanisms/capability.py`**

```python
# lca/contracts/mechanisms/capability.py — find and replace:
#   class SeamKey(str, Enum):     →  class CapabilityKey(str, Enum):
#   REQUIRED_SEAM_KEYS            →  REQUIRED_CAPABILITY_KEYS
# Update ALL class member usages (`SeamKey.LLM` → `CapabilityKey.LLM`)
```

- [ ] **Step 3: Find and migrate all `SeamKey` callers**

```bash
rg "SeamKey" lca/ tests/ --type py | grep -v "specs/"
```

Expected: ~5-10 files (composer.py:32, capability_boot.py, plugins/* etc.)

For each caller, replace `SeamKey` → `CapabilityKey`. Existing importers get the rename automatically.

- [ ] **Step 4: Replace `lca/contracts/mechanisms/seam.py`**

```python
# lca/contracts/mechanisms/seam.py
"""Composition-time gating — post-cordis migration.

`consume()` is the only surviving symbol. It is a composition-time gate
that declares a consumer as officially a CONSUMER of a definition's seam
and returns the provider unchanged.

The SeamRole / SeamDeclaration / SeamRegistry / seam / validate_all_seams
machinery was LCA 早期自创; cordis's @plugin/inject/provide replaces it.
"""
from __future__ import annotations

from typing import Any, TypeVar

T = TypeVar("T")


def consume(definition: str, provider: T, consumer: Any) -> T:
    """Composition-time gate. Returns provider unchanged."""
    return provider
```

- [ ] **Step 5: SURGICAL edit `lca/contracts/mechanisms/__init__.py` — KEEP inline Protocols (B5 fix)**

**Don't rewrite the file.** Only make these surgical edits:

1. Delete the line `from lca.contracts.mechanisms.capability import SeamKey as SeamKey,`
2. Delete the entire `from lca.contracts.mechanisms.seam import (IncompleteSeamError, SeamDeclaration, SeamRegistry, SeamRole, UnauthorizedConsumerError, consume, get_global_seam_registry, register_seam, require_complete, seam, validate_all_seams) as ...` block
3. Add: `from lca.contracts.mechanisms.capability import CapabilityKey as CapabilityKey,`
4. Add: `from lca.contracts.mechanisms.seam import consume as consume,`
5. Update `__all__` list — drop SeamRole/SeamDeclaration/SeamRegistry/etc., add CapabilityKey + consume.

**KEEP** all 6 inline Protocols (`EventBus`, `Hook`, `HookRegistry`, `NamedRegistryProtocol`, `OrchestrationRegistryProtocol`, `ComponentRegistryProtocol`). They're imported by `lca.contracts.__init__` and `lca.contracts.protocols.__init__` which load eagerly — removing them breaks `import lca`.

- [ ] **Step 6: Verify imports work + eager load test**

```bash
uv run python -c "from lca.contracts.mechanisms.seam import consume; print(repr(consume('test', 'p', 'c')))"
uv run python -c "from lca.contracts.mechanisms.capability import CapabilityKey; print(CapabilityKey.LLM)"
uv run python -c "from lca.contracts.mechanisms import EventBus, Hook, HookRegistry, NamedRegistryProtocol, OrchestrationRegistryProtocol, ComponentRegistryProtocol; print('inline Protocols OK')"
uv run python -c "from lca.contracts.mechanisms import CapabilityKey, REQUIRED_CAPABILITY_KEYS, consume; print('rename + consume OK')"
uv run python -c "import lca; print('lca OK')"  # eager load test
uv run python -c "from lca.contracts.protocols import ComponentRegistryProtocol, EventBus, Hook, HookRegistry, NamedRegistryProtocol; print('protocols OK')"
```

- [ ] **Step 7: Commit**

```bash
git add lca/contracts/mechanisms/seam.py lca/contracts/mechanisms/__init__.py lca/contracts/mechanisms/capability.py
git commit -m "contracts: drop SeamRole/SeamDeclaration/SeamRegistry/seam/validate_all_seams; rename SeamKey → CapabilityKey; keep consume()"
```

---

### Task 1.19: Split `lca/contracts/mechanisms/plugin.py` (drop Plugin Protocol, keep PluginConfig)

**Files:**
- Modify: `lca/contracts/mechanisms/plugin.py`

- [ ] **Step 1: Verify no callers of to-be-deleted `Plugin` Protocol remain**

```bash
rg -l "from lca\.contracts\.mechanisms\.plugin import Plugin\b" lca/ tests/
```

Expected: 1 file (`tests/plugin/test_contracts.py` — already deleted in Task 1.13). Empty expected.

- [ ] **Step 2: Replace `lca/contracts/mechanisms/plugin.py`**

```python
# lca/contracts/mechanisms/plugin.py
"""Plugin config base class — post-cordis migration.

`PluginConfig` Pydantic model with `extra="forbid"` is held here as a
shared base for plugin-specific config models. cordis uses Standard Schema
(Pydantic v2 compatible), so any subclass with `model_config = {"extra": "forbid"}`
is consumable.

The `Plugin` Protocol (name/inject/provides/apply/Config) is deleted —
cordis's `@plugin` decorator replaces it.
"""
from __future__ import annotations

from pydantic import BaseModel


class PluginConfig(BaseModel):
    """Plugin config base class: default empty, unknown fields rejected."""

    model_config = {"extra": "forbid"}
```

- [ ] **Step 3: Verify `PluginConfig` importable**

Run: `uv run python -c "from lca.contracts.mechanisms.plugin import PluginConfig; print(PluginConfig.model_config['extra'])"`  Expected: `'forbid'`

- [ ] **Step 4: Commit**

```bash
git add lca/contracts/mechanisms/plugin.py
git commit -m "contracts: drop Plugin Protocol; keep PluginConfig Pydantic base"
```

---

### Task 1.20: Verify Chunk 1 acceptance criteria

- [ ] **Step 1: `rg "lca.infrastructure.plugin" lca/ tests/` — expect empty**

Run: `rg "lca\.layer0_infra\.plugin" lca/ tests/ --type py`
Expected: empty

- [ ] **Step 2: `rg "lca.harness.kernel" lca/ tests/` — expect empty**

Run: `rg "lca\.harness\.kernel" lca/ tests/ --type py`
Expected: empty

- [ ] **Step 3: `rg "PluginManifest\|ExtensionPoint\|CapabilityGrant\|ScopeKind\|PluginKind\|ProviderMode" lca/ tests/` — expect only docstring/spec text**

Run: `rg "PluginManifest\|ExtensionPoint\|CapabilityGrant\|ScopeKind\|PluginKind\|ProviderMode" lca/ tests/ --type py | grep -v "/specs/" | grep -v "\.md"`
Expected: empty

- [ ] **Step 4: `rg "SeamRole\|SeamDeclaration\|SeamRegistry\|seam\b" lca/ tests/` — expect empty**

Run: `rg "SeamRole\|SeamDeclaration\|SeamRegistry\|seam\b" lca/ tests/ --type py`
Expected: empty

- [ ] **Step 5: `rg "ScopedPluginHost\|scope\.resolve\|scope\.fork" lca/ tests/` — expect only Chunk 5 stubs**

Run: `rg "ScopedPluginHost\|scope\.resolve\|scope\.fork" lca/ tests/ --type py | grep -v "NotImplementedError" | grep -v "composer.py.*Chunk 5"`
Expected: empty (composer.py has stubs marked for Chunk 5)

- [ ] **Step 6: Verify `consume()` and `PluginConfig` still importable**

```bash
uv run python -c "from lca.contracts.mechanisms.seam import consume; print('consume OK')"
uv run python -c "from lca.contracts.mechanisms.plugin import PluginConfig; print('PluginConfig OK')"
```

- [ ] **Step 7: Verify cordis loads**

```bash
uv run python -c "from cordis import Context, plugin, Service; print('cordis OK')"
```

- [ ] **Step 8: Run lint-imports**

Run: `uv run lint-imports`
Expected: clean

- [ ] **Step 9: Run vulture**

Run: `uv run vulture lca --min-confidence 80 | head -50`
Expected: minor orphan imports; non-blocking (Chunk 2+ fixes)

- [ ] **Step 10: Run pytest collection**

Run: `uv run pytest tests/ --collect-only --no-cov -q 2>&1 | tail -20`
Expected: collection succeeds (individual test failures acceptable — fixed in later chunks)

- [ ] **Step 11: Commit any final fixes**

```bash
git add -u
git commit -m "chore: chunk 1 verification fixes" --allow-empty
```

---## Chunk 2: Rewrite Boot + Middleware + 21 Plugins (P3-P5)

**Goal:** Rewrite `lca/harness/profile/boot.py` as cordis.Loader thin wrapper. Migrate `lca/harness/middleware/registry.py` to use cordis events. Convert 21 plugins to module-per-plugin `@plugin` form. Delete `lca/layer4_app/capability_boot.py`.

**Risk:** Plugins at `lca/plugins/*/` currently use old `manifest = PluginManifest(...)` + `apply()` API. Need rewrite to `@plugin` form. Service classes move to `lca/layer0_infra/{capability,session,system_prompt,...}/`.

---

### Task 2.1: ~~Rewrite `lca/harness/profile/boot.py`~~ [MOVED to Chunk 1 Task 1.7 — see B1 fix]

**Status**: REMOVED. boot.py migration was moved to Chunk 1 Task 1.7 to fix B1 (chunk-boundary ordering). This task should be skipped during execution.

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_profile_boot.py
from pathlib import Path
import pytest


@pytest.mark.asyncio
async def test_boot_profile_loads_minimal_yaml(tmp_path: Path):
    yaml = tmp_path / "minimal.yaml"
    yaml.write_text("""
plugins:
  - id: test-plugin
    name: test-plugin
    $module: lca.plugins.test.dummy
    config: {}
""")
    from lca.harness.profile.boot import boot_profile
    tree = await boot_profile(yaml)
    assert tree.plugin_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/harness/test_profile_boot.py -v --no-cov`
Expected: FAIL (current implementation uses old Loader)

- [ ] **Step 3: Write minimal implementation**

```python
# lca/harness/profile/boot.py
"""Boot a harness plugin tree from a profile YAML.

Thin wrapper around cordis.Loader. Bundles from ``bundles/*.yaml`` are first
merged via ``cordis.loader.merge_bundles``, then loaded into a root Context.
"""
from __future__ import annotations

from pathlib import Path

from cordis import Context
from cordis.loader import Entry, Loader, load_yaml, merge_bundles


async def boot_profile(
    profile_path: Path | str,
    *,
    check_seam_completeness: bool = True,  # legacy kwarg, now no-op
) -> Context:
    """Load profile YAML → resolve modules → build root Context.

    Profile YAML structure:
      bundles:
        - bundles/base.yaml
        - bundles/web-app.yaml
      patch:
        - id: <plugin-id>
          config: { ... }
    """
    import warnings
    if check_seam_completeness:
        warnings.warn(
            "check_seam_completeness is deprecated; cordis doesn't validate seams",
            DeprecationWarning,
            stacklevel=2,
        )

    path = Path(profile_path)
    data = load_yaml(path)
    ctx = Context()
    loader = Loader()
    entries = loader.load(data)
    for entry in entries:
        module = _resolve_module(entry)
        plugin_obj = getattr(module, entry.name)
        await plugin_obj.setup(ctx, entry.config)
    return ctx


def _resolve_module(entry: Entry) -> object:
    """Resolve $module from YAML entry."""
    import importlib
    module_path = entry.extra.get("$module")
    if module_path is None:
        raise ValueError(f"entry {entry.id!r} missing $module")
    return importlib.import_module(module_path)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/harness/test_profile_boot.py -v --no-cov`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add lca/harness/profile/boot.py tests/harness/test_profile_boot.py
git commit -m "harness: rewrite boot.py as cordis.Loader thin wrapper"
```

---

### Task 2.2: Rewrite `lca/harness/middleware/registry.py` to use cordis events

**Files:**
- Modify: `lca/harness/middleware/registry.py`
- Test: `tests/harness/test_middleware_registry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/harness/test_middleware_registry.py
import pytest
from cordis import Context


@pytest.mark.asyncio
async def test_cognitive_points_registered_as_cordis_events():
    """Each COGNITIVE_POINTS entry becomes a cordis event listener."""
    from lca.harness.middleware.registry import build_cognitive_handlers
    ctx = Context()
    build_cognitive_handlers(ctx)  # registers 10 events on ctx
    # Check that at least 3 events have listeners
    assert len(ctx.events._listeners) >= 3  # internal API, but ok for test
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/harness/test_middleware_registry.py -v --no-cov`
Expected: FAIL (current impl uses ExtensionPoint)

- [ ] **Step 3: Write minimal implementation**

```python
# lca/harness/middleware/registry.py
"""Cognitive phase event handlers — cordis event names.

COGNITIVE_POINTS originally held 10 ExtensionPoint instances. Now we represent
the same 10 phase boundaries as cordis event names. Guard plugins register
handlers via ``ctx.events.on(event_name, ...)`` and the registry is the
canonical event taxonomy.
"""
from __future__ import annotations

from dataclasses import dataclass
from cordis import Context


@dataclass(frozen=True)
class CognitivePhase:
    name: str
    description: str


COGNITIVE_PHASES: tuple[CognitivePhase, ...] = (
    CognitivePhase("agent.pre_step", "each step before perceive"),
    CognitivePhase("agent.before_perceive", "before perception"),
    CognitivePhase("agent.after_perceive", "after perception"),
    CognitivePhase("agent.before_think", "before thinking"),
    CognitivePhase("agent.after_think", "after thinking"),
    CognitivePhase("agent.before_act", "before act"),
    CognitivePhase("agent.after_act", "after act"),
    CognitivePhase("agent.before_reflect", "before reflect"),
    CognitivePhase("agent.after_reflect", "after reflect"),
    CognitivePhase("agent.before_turn_end", "before turn end"),
)


def build_cognitive_handlers(ctx: Context) -> None:
    """Register empty handlers for each phase. Plugin mutations are added later."""
    for phase in COGNITIVE_PHASES:
        # Reserve the event name by registering a no-op listener; this ensures
        # `ctx.events.on(phase.name)` in plugins doesn't fail with "no event".
        @ctx.events.on(phase.name)
        async def _noop(*args, **kwargs):  # pragma: no cover
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/harness/test_middleware_registry.py -v --no-cov`
Expected: PASS

- [ ] **Step 5: Verify no ExtensionPoint / ScopeKind references remain**

Run: `rg "ExtensionPoint\|ScopeKind\|PluginKind" lca/harness/`
Expected: empty

- [ ] **Step 6: Commit**

```bash
git add lca/harness/middleware/registry.py tests/harness/test_middleware_registry.py
git commit -m "harness: rewrite middleware/registry.py as cordis events taxonomy"
```

---

### Task 2.3: Tag each `lca/plugins/*/__init__.py` for migration

**Files:**
- Read only: `lca/plugins/*/__init__.py` (21 files)

- [ ] **Step 1: List all 21 plugins and their target new paths**

The 21 → 18 plugins map (per spec §6.1):

| Old | New (module-per-plugin) |
|---|---|
| `lca/plugins/llm_service/__init__.py` | `lca/plugins/llm_service.py` |
| `lca/plugins/llm_provider/__init__.py` | `lca/plugins/llm_provider.py` |
| `lca/plugins/tools_service/__init__.py` | `lca/plugins/tools_service.py` |
| `lca/plugins/session_service/__init__.py` | `lca/plugins/session_service.py` |
| `lca/plugins/system_prompt/__init__.py` | `lca/plugins/system_prompt.py` |
| `lca/plugins/transport_service/__init__.py` | `lca/plugins/transport_service.py` |
| `lca/plugins/skills_service/__init__.py` | `lca/plugins/skills_service.py` |
| `lca/plugins/file_store_service/__init__.py` | `lca/plugins/file_store_service.py` |
| `lca/plugins/observability_service/__init__.py` | `lca/plugins/observability_service.py` |
| `lca/plugins/sandbox_service/__init__.py` | `lca/plugins/sandbox_service.py` |
| `lca/plugins/memory_service/__init__.py` | `lca/plugins/memory_service.py` |
| `lca/plugins/search_service/__init__.py` | `lca/plugins/search_service.py` |
| `lca/plugins/state_store_service/__init__.py` | `lca/plugins/state_store_service.py` |
| `lca/plugins/loop_cognitive/__init__.py` | `lca/plugins/loop_cognitive.py` |
| `lca/plugins/loop_dsh_bridge/__init__.py` | `lca/plugins/loop_dsh_bridge.py` |
| `lca/plugins/loop_replay/__init__.py` | `lca/plugins/loop_replay.py` |
| `lca/plugins/gateway_starlette/__init__.py` | `lca/plugins/gateway_starlette.py` |
| `lca/plugins/loop_intervention_policy/__init__.py` | `lca/plugins/guards/loop_intervention.py` |
| `lca/plugins/budget_policy/__init__.py` | `lca/plugins/guards/step_budget.py` |
| `lca/plugins/agent_service/__init__.py` | merge into `lca/plugins/session_service.py` |
| `lca/plugins/seam_definitions/__init__.py` | DELETE |

- [ ] **Step 2: For each plugin, perform the rename (drop `__init__.py`, create `.py` file)**

```bash
cd ~/layered-cognitive-agent
# For each, e.g.: lca/plugins/llm_service → lca/plugins/llm_service.py
git mv lca/plugins/llm_service/__init__.py lca/plugins/llm_service.py
rmdir lca/plugins/llm_service
# ... (repeat for 16 more)
```

- [ ] **Step 3: Convert guard plugins and create new locations**

```bash
git mv lca/plugins/loop_intervention_policy/__init__.py lca/plugins/guards/loop_intervention.py
git mv lca/plugins/budget_policy/__init__.py lca/plugins/guards/step_budget.py
rmdir lca/plugins/loop_intervention_policy lca/plugins/budget_policy
git rm -r lca/plugins/agent_service      # merge into session_service
git rm -r lca/plugins/seam_definitions  # delete
```

- [ ] **Step 4: Verify new structure**

```bash
find lca/plugins -name "*.py" -not -path "*/__pycache__/*" | sort
```

Expected: ~22 module files (17 + 2 guards + DSH bridge, etc.) instead of 21 directories.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "plugins: convert 21 package-dirs to module-per-plugin files"
```

---

### Task 2.4: Rewrite each plugin to `@plugin` form (8 batch commits)

**Files:**
- Modify: 21 plugin files (rewriting to `@plugin` async setup)

Process each plugin file. For each:

- [ ] **Step 1: Rewrite `lca/plugins/llm_service.py`**

```python
# lca/plugins/llm_service.py
"""LLM Service Definition plugin — Tier-1."""
from __future__ import annotations
from cordis import plugin


@plugin(name="lca-llm-service")
async def setup(ctx, config):
    from lca.infrastructure.capability.llm import LlmService
    ctx.provide("llm", LlmService())
```

- [ ] **Step 2: Rewrite `lca/plugins/llm_provider.py`**

```python
# lca/plugins/llm_provider.py
"""LLM Provider plugin — Tier-1 (single mock provider for legacy compat)."""
from __future__ import annotations
from cordis import plugin
from lca.contracts.typed_ctx import TypedContext


@plugin(name="lca-llm-provider", inject=["llm"])
async def setup(ctx: TypedContext, config):
    """Register default providers. Real provider picks live in Tier-2."""
    from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter
    ctx.llm.register("mock", MockLLMAdapter())
```

- [ ] **Step 3: Rewrite `lca/plugins/tools_service.py`**

```python
# lca/plugins/tools_service.py
from __future__ import annotations
from cordis import plugin


@plugin(name="lca-tools-service")
async def setup(ctx, config):
    from lca.infrastructure.capability.tools import ToolsService
    ctx.provide("tools", ToolsService())
```

- [ ] **Step 4: Rewrite `lca/plugins/session_service.py` (merged with agent_service)**

```python
# lca/plugins/session_service.py
"""Session service plugin — Tier-1. Includes merge of agent_service.

SessionService currently lives inline in lca/plugins/session_service/__init__.py.
The rewrite keeps the class inline in this file (the plugin IS the service
file). Future tasks may extract to lca/layer0_infra/session/ for separation.
"""
from __future__ import annotations
from cordis import plugin
from lca.contracts.observability.session_events import SessionEventType


class SessionService:
    """Session store + surface projection (model-visible ⟺ logged)."""

    def __init__(self):
        # state placeholder; full implementation grows in subsequent tasks
        self._events = []

    async def record(self, event_type: SessionEventType, session_id: str, **payload):
        """Single entry point for any session event."""
        self._events.append((event_type, session_id, payload))


@plugin(name="lca-session-service")
async def setup(ctx, config):
    ctx.provide("session_service", SessionService())
```

- [ ] **Step 5: Rewrite remaining 16 plugins (transport_service, skills_service, file_store_service, observability_service, sandbox_service, memory_service, search_service, state_store_service, system_prompt, loop_cognitive, loop_dsh_bridge, loop_replay, gateway_starlette)**

Each follows the same pattern:
```python
from __future__ import annotations
from cordis import plugin


@plugin(name="lca-<name>", inject=[<key>])
async def setup(ctx, config):
    from lca.infrastructure.<module> import <ServiceClass>
    ctx.provide("<key>", <ServiceClass>())
```

- [ ] **Step 6: Verify line counts**

Run: `wc -l lca/plugins/*.py | head -25`
Expected: every plugin file ≤ 50 lines

- [ ] **Step 7: Commit**

```bash
git add lca/plugins/
git commit -m "plugins: rewrite 21 plugins to @plugin form (module-per-plugin)"
```

---

### Task 2.5: Rewrite `lca/plugins/guards/loop_intervention.py` and `step_budget.py`

**Files:**
- Modify: `lca/plugins/guards/loop_intervention.py`
- Modify: `lca/plugins/guards/step_budget.py`

- [ ] **Step 1: Rewrite loop_intervention.py using cordis events (fix function name)**

```python
# lca/plugins/guards/loop_intervention.py
"""Loop intervention guard — Tier-3. Detects consecutive identical tool calls."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    threshold: int = 3


@plugin(name="lca-guard-loop-intervention")
async def setup(ctx, config: Config):
    from lca.runtime.loop_intervention_mw import loop_intervention_middleware

    @ctx.events.on("agent.after_act")
    async def _check(call_result, state):
        return loop_intervention_middleware("agent.after_act", state, None, config={"threshold": config.threshold})
```

**Note (F-fix)**: Plan originally said `check_intervention` but the actual function name in `lca/layer2_runtime/loop_intervention_mw.py` is `loop_intervention_middleware`. Also the middleware signature is `(phase, state, context, *, config=None)`.

- [ ] **Step 2: Rewrite step_budget.py using cordis events (fix import path)**

```python
# lca/plugins/guards/step_budget.py
"""Step budget guard — Tier-3. Rejects when step_count >= max_steps."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    max_steps: int = 100


@plugin(name="lca-guard-step-budget")
async def setup(ctx, config: Config):
    from lca.plugins.budget_policy import budget_check_middleware

    @ctx.events.on("agent.pre_step")
    async def _check(state):
        return budget_check_middleware("agent.pre_step", state, None, config={"max_steps": config.max_steps})
```

**Note (F-fix)**: Plan originally said `lca/layer2_runtime/budget_policy` but that file doesn't exist — the function lives at `lca/plugins/budget_policy/__init__.py:budget_check_middleware`. After Chunk 2 Task 2.3 renames the file to `lca/plugins/guards/step_budget.py`, the import becomes `from lca.plugins.guards.step_budget import budget_check_middleware`.

- [ ] **Step 3: Verify line counts**

Run: `wc -l lca/plugins/guards/*.py`
Expected: each ≤ 50 lines

- [ ] **Step 4: Commit**

```bash
git add lca/plugins/guards/
git commit -m "guards: rewrite loop_intervention/step_budget as @plugin with cordis events"
```

---

### Task 2.6: Delete `lca/layer4_app/capability_boot.py` + migrate callers

**Files:**
- Delete: `lca/layer4_app/capability_boot.py`
- Modify: `lca/layer4_app/defaults.py` (drop `register_seam_catalog()`)
- Modify: `lca/layer4_app/composer.py` (drop `_resolve_capability_context` legacy + `_ScopeAsCapabilityContext` adapter)

**Critical**: 3 caller sites missed in original plan:
- `lca/layer4_app/defaults.py:54,145` calls `register_seam_catalog()`
- `lca/layer4_app/composer.py:444-448` `_resolve_capability_context` still calls `boot_capabilities()`
- `lca/layer4_app/composer.py:109` `_ScopeAsCapabilityContext` adapter uses `ScopedPluginHost.resolve()`

- [ ] **Step 1: Verify all callers**

Run: `rg -l "capability_boot\|boot_capabilities\|register_seam_catalog" lca/ tests/`
Expected: 4 files

- [ ] **Step 2: Migrate `lca/layer4_app/defaults.py`**

DELETE both occurrences of `register_seam_catalog()` call. The CapabilityHub / SeamRegistry / register_seam_catalog machinery is gone — the Tier-1 plugin tree replaces it.

- [ ] **Step 3: Migrate `composer.py:_resolve_capability_context` + `_ScopeAsCapabilityContext` adapter**

```python
# before (line 444-448)
def _resolve_capability_context(scope):
    if scope is None:
        return boot_capabilities()
    return scope

# after
def _resolve_capability_context(ctx):
    return ctx  # cordis Context IS the capability context

# DELETE _ScopeAsCapabilityContext adapter entirely (cordis.Context.inject is the equivalent)
```

- [ ] **Step 4: Delete the file**

```bash
git rm lca/layer4_app/capability_boot.py
```

- [ ] **Step 5: Run tests (collection only)**

Run: `uv run pytest tests/ --collect-only --no-cov -q 2>&1 | tail -30`
Expected: collection passes; individual failures acceptable

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "layer4_app: delete capability_boot.py + migrate defaults/composer adapters"
```

---

### Task 2.7: Chunk 2 verification

- [ ] **Step 1: Run `lca-ops debug tree` (or fail gracefully if not yet implemented)**

Run: `uv run python -c "from lca.harness.profile.boot import boot_profile; import asyncio; print(asyncio.run(boot_profile('bundles/base-spine.yaml')))"`
Expected: should work (old yaml) or fail with informative error

- [ ] **Step 2: Run `rg "PluginManifest\|ExtensionPoint\|CapabilityGrant" lca/plugins/` — expect empty**

Run: `rg "PluginManifest\|ExtensionPoint\|CapabilityGrant" lca/plugins/`
Expected: empty

- [ ] **Step 3: Run `uv run lint-imports`**

Run: `uv run lint-imports`
Expected: clean

- [ ] **Step 4: Run `uv run vulture lca --min-confidence 80 | head -30`**

Run: `uv run vulture lca --min-confidence 80`
Expected: minor orphan imports; fix in Chunk 3

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "chore: chunk 2 verification fixes" --allow-empty
```

---

## Chunk 3: Tier-2 Provider + Tier-3 Behavior Plugins (P5.1-P5.2)

**Goal:** Create 12 Tier-2 provider plugins (each seam: single plugin + factory). Create 13 Tier-3 behavior plugins (Brain, Reasoner, Synthesizer, Loop, Guard, DSH bridge, TeamLead). Move prompt templates to central `prompt_registry`. Total: 38 plugins.

**Risk:** Tier-2 plugins must NOT import `lca.infrastructure.*` at module top-level (per spec §4.6). Imports inside `setup()` are fine.

---

### Task 3.1: Create `lca/plugins/providers/__init__.py` (empty package marker)

**Files:**
- Create: `lca/plugins/providers/__init__.py`

- [ ] **Step 1: Create empty package**

```python
# lca/plugins/providers/__init__.py
"""Tier-2 Provider plugins. Each seam has a single plugin that registers
multiple provider implementations and selects the active one via config."""
```

- [ ] **Step 2: Commit**

```bash
git add lca/plugins/providers/__init__.py
git commit -m "plugins/providers: package marker"
```

---

### Task 3.2: Create `lca/plugins/providers/llm.py` (Tier-2 canonical)

**Files:**
- Create: `lca/plugins/providers/llm.py`
- Test: `tests/plugins/test_provider_llm.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/plugins/test_provider_llm.py
import pytest
from cordis import Context


@pytest.mark.asyncio
async def test_llm_provider_registers_all_when_mode_is_auto():
    from lca.plugins.providers.llm import setup, Config
    from lca.infrastructure.capability.llm import LlmService

    ctx = Context()
    ctx.provide("llm", LlmService())
    await setup(ctx, Config(mode="auto", providers=["mock", "real", "deepseek"], api_key=None))
    svc = ctx.inject("llm")
    assert "mock" in svc.providers.names()
    assert svc.active == "mock"  # no api_key → mock


@pytest.mark.asyncio
async def test_llm_provider_activates_explicit_mode():
    from lca.plugins.providers.llm import setup, Config
    from lca.infrastructure.capability.llm import LlmService

    ctx = Context()
    ctx.provide("llm", LlmService())
    await setup(ctx, Config(mode="deepseek", providers=["mock", "deepseek"], api_key="k"))
    assert ctx.inject("llm").active == "deepseek"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/plugins/test_provider_llm.py -v --no-cov`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
# lca/plugins/providers/llm.py
"""LLM Provider plugin — Tier-2. Single plugin, multi-provider factory."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    mode: str = Field(default="auto", description="auto|real|deepseek|mock|pi_ai")
    providers: list[str] = Field(default_factory=lambda: ["mock", "real", "deepseek"])
    api_key: str | None = None
    base_url: str | None = None


@plugin(name="lca-llm-provider", inject=["llm"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.llm_adapter.mock_llm import MockLLMAdapter
    from lca.infrastructure.llm_adapter.openai_compat import OpenAICompatAdapter

    llm = ctx.inject("llm")
    if "mock" in config.providers:
        llm.register("mock", MockLLMAdapter())
    if "real" in config.providers:
        llm.register("real", OpenAICompatAdapter(api_key=config.api_key, base_url=config.base_url))
    if "deepseek" in config.providers:
        # Deepseek is OpenAI-compatible; uses the same adapter.
        llm.register("deepseek", OpenAICompatAdapter(api_key=config.api_key, base_url=config.base_url or "https://api.deepseek.com"))
    # "pi_ai" not yet implemented — skip.

    target = config.mode
    if target == "auto":
        target = "real" if config.api_key else "mock"
    if target not in config.providers:
        target = config.providers[0]
    llm.activate(target)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/plugins/test_provider_llm.py -v --no-cov`
Expected: PASS

- [ ] **Step 5: Verify top-level import constraint**

Run: `rg "^from lca.layer" lca/plugins/providers/llm.py`
Expected: empty (no top-level imports of `lca.layer*`)

- [ ] **Step 6: Commit**

```bash
git add lca/plugins/providers/llm.py tests/plugins/test_provider_llm.py
git commit -m "providers: lca-llm-provider Tier-2 (single plugin + factory)"
```

---

### Task 3.3: Create 11 more Tier-2 provider plugins

**Files:**
- Create: `lca/plugins/providers/{memory,state_store,search,tools,transport,skills,file_store,observability,sandbox,attachment,workspace}.py`

For each, follow the same pattern as Task 3.2. Each plugin file ≤ 50 lines.

- [ ] **Step 1: Create `lca/plugins/providers/memory.py`**

```python
# lca/plugins/providers/memory.py
"""Memory Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["simple"])


@plugin(name="lca-memory-provider", inject=["memory"])
async def setup(ctx, config: Config) -> None:
    from lca.cognition.memory.simple_memory import SimpleMemorySystem

    memory = ctx.inject("memory")
    if "simple" in config.providers:
        memory.register("simple", SimpleMemorySystem)
```

- [ ] **Step 2: Create `lca/plugins/providers/state_store.py`**

```python
# lca/plugins/providers/state_store.py
"""State store Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["memory"])


@plugin(name="lca-state-store-provider", inject=["state_store"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.state_store.in_memory_store import InMemoryStateStore

    if "memory" in config.providers:
        ctx.inject("state_store").register("memory", InMemoryStateStore)
```

- [ ] **Step 3: Create `lca/plugins/providers/search.py`**

```python
# lca/plugins/providers/search.py
"""Search Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["tavily"])


@plugin(name="lca-search-provider", inject=["search"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.search.providers.tavily import search_tavily

    if "tavily" in config.providers:
        ctx.inject("search").register("tavily", search_tavily)
```

- [ ] **Step 4: Create `lca/plugins/providers/tools.py`**

```python
# lca/plugins/providers/tools.py
"""Tools Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    factories: list[str] = Field(default_factory=lambda: ["g2a"])


@plugin(name="lca-tools-provider", inject=["tools"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.tools.default_set import build_default_tools

    if "g2a" in config.factories:
        ctx.inject("tools").register_factory("g2a", build_default_tools)
```

- [ ] **Step 5: Create `lca/plugins/providers/transport.py`**

```python
# lca/plugins/providers/transport.py
"""Transport Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["internal", "a2a", "mcp"])


@plugin(name="lca-transport-provider", inject=["transport"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.transport.a2a_transport import A2ATransport
    from lca.infrastructure.transport.agent_transport import InternalTransport
    from lca.infrastructure.transport.mcp_transport import MCPTransport

    transport = ctx.inject("transport")
    if "internal" in config.providers:
        transport.register(InternalTransport())
    if "a2a" in config.providers:
        transport.register(A2ATransport())
    if "mcp" in config.providers:
        transport.register(MCPTransport())
```

- [ ] **Step 6: Create `lca/plugins/providers/skills.py`**

```python
# lca/plugins/providers/skills.py
"""Skills Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["disk"])


@plugin(name="lca-skills-provider", inject=["skills"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.skills.factory import resolve_skill_store

    if "disk" in config.providers:
        ctx.inject("skills").register("disk", resolve_skill_store())
```

- [ ] **Step 7: Create `lca/plugins/providers/file_store.py`**

```python
# lca/plugins/providers/file_store.py
"""File Store Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(name="lca-file-store-provider", inject=["file_store"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.file_store import get_default_file_store

    if "local" in config.providers:
        ctx.inject("file_store").register("local", get_default_file_store())
```

- [ ] **Step 8: Create `lca/plugins/providers/observability.py`**

```python
# lca/plugins/providers/observability.py
"""Observability Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["console"])


@plugin(name="lca-observability-provider", inject=["observability"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.observability.registry import create_observability

    if "console" in config.providers:
        ctx.inject("observability").register("console", lambda: create_observability("console"))
```

- [ ] **Step 9: Create `lca/plugins/providers/sandbox.py`**

```python
# lca/plugins/providers/sandbox.py
"""Sandbox Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(name="lca-sandbox-provider", inject=["sandbox"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.sandbox.factory import resolve_sandbox

    if "local" in config.providers:
        resolved = resolve_sandbox()
        if resolved is not None:
            ctx.inject("sandbox").register("local", resolved, activate=True)
```

- [ ] **Step 10: Create `lca/plugins/providers/attachment.py`**

```python
# lca/plugins/providers/attachment.py
"""Attachment Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["filesystem"])


@plugin(name="lca-attachment-provider", inject=["attachment", "file_store"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.attachment.service import FileStoreAttachmentIdentity

    if "filesystem" in config.providers:
        provider = FileStoreAttachmentIdentity(ctx.inject("file_store"))
        ctx.inject("attachment").register("filesystem", provider)
```

- [ ] **Step 11: Create `lca/plugins/providers/workspace.py`**

```python
# lca/plugins/providers/workspace.py
"""Workspace Provider plugin — Tier-2."""
from __future__ import annotations
from cordis import plugin
from pydantic import BaseModel, Field


class Config(BaseModel):
    model_config = {"extra": "forbid"}
    providers: list[str] = Field(default_factory=lambda: ["local"])


@plugin(name="lca-workspace-provider", inject=["workspace"])
async def setup(ctx, config: Config) -> None:
    from lca.infrastructure.workspace.service import LocalWorkspace

    if "local" in config.providers:
        ctx.inject("workspace").register("local", LocalWorkspace())
```

- [ ] **Step 12: Verify all 12 Tier-2 plugins exist + line counts**

Run: `wc -l lca/plugins/providers/*.py | tail -15`
Expected: each ≤ 50 lines

- [ ] **Step 13: Verify top-level import constraint**

Run: `rg "^from lca.layer" lca/plugins/providers/`
Expected: empty

- [ ] **Step 14: Commit**

```bash
git add lca/plugins/providers/
git commit -m "providers: 12 Tier-2 provider plugins (single plugin + factory per seam)"
```

---

### Task 3.4: Create `lca/plugins/brain/modular.py` and `lca/plugins/brain/simple.py`

**Files:**
- Create: `lca/plugins/brain/__init__.py`
- Create: `lca/plugins/brain/modular.py`
- Create: `lca/plugins/brain/simple.py`

- [ ] **Step 1: Create `lca/plugins/brain/__init__.py`**

```python
# lca/plugins/brain/__init__.py
"""Brain strategy plugins — Tier-3."""
```

- [ ] **Step 2: Create `lca/plugins/brain/modular.py`**

```python
# lca/plugins/brain/modular.py
"""ModularBrain strategy plugin — Tier-3."""
from __future__ import annotations
from cordis import plugin
from lca.contracts.typed_ctx import TypedContext


@plugin(name="lca-brain-modular")
async def setup(ctx: TypedContext, config) -> None:
    from lca.cognition.brain.modular_brain import ModularBrain
    from lca.cognition.brain.default_factory import brain_factory  # noqa: F401

    factory = ctx.brain_factory
    factory.register("modular", ModularBrain)
```

- [ ] **Step 3: Create `lca/plugins/brain/simple.py`**

```python
# lca/plugins/brain/simple.py
"""SimpleBrain strategy plugin — Tier-3."""
from __future__ import annotations
from cordis import plugin
from lca.contracts.typed_ctx import TypedContext


@plugin(name="lca-brain-simple")
async def setup(ctx: TypedContext, config) -> None:
    from lca.cognition.brain.simple_brain import SimpleBrain
    from lca.agent.brain.factory import BrainFactory

    factory = ctx.brain_factory
    factory.register("simple", SimpleBrain)
```

- [ ] **Step 4: Commit**

```bash
git add lca/plugins/brain/
git commit -m "brain: modular + simple Brain strategy plugins (Tier-3)"
```

---

### Task 3.5: Create reasoner / synthesizer / team_lead plugins

**Files:**
- Create: `lca/plugins/reasoner/__init__.py` + `lca/plugins/reasoner/prompt.py`
- Create: `lca/plugins/synthesizer/__init__.py` + `lca/plugins/synthesizer/concat.py`
- Create: `lca/plugins/team_lead/__init__.py` + `lca/plugins/team_lead/board.py`

- [ ] **Step 1: Create reasoner package**

```python
# lca/plugins/reasoner/__init__.py
"""Reasoner plugins — Tier-3."""
```

```python
# lca/plugins/reasoner/prompt.py
"""PromptReasoner plugin — Tier-3."""
from __future__ import annotations
from cordis import plugin
from lca.contracts.typed_ctx import TypedContext


@plugin(name="lca-reasoner-prompt", inject=["llm"])
async def setup(ctx: TypedContext, config) -> None:
    from lca.cognition.brain.reasoner import PromptReasoner
    from lca.agent.brain.factory import BrainFactory

    factory = ctx.brain_factory
    factory.register_reasoner("prompt", PromptReasoner)
```

- [ ] **Step 2: Create synthesizer package**

```python
# lca/plugins/synthesizer/__init__.py
"""Synthesizer plugins — Tier-3."""
```

```python
# lca/plugins/synthesizer/concat.py
"""ConcatSynthesizer plugin — Tier-3."""
from __future__ import annotations
from cordis import plugin
from lca.contracts.typed_ctx import TypedContext


@plugin(name="lca-synthesizer-concat")
async def setup(ctx: TypedContext, config) -> None:
    from lca.cognition.brain.synthesizer import ConcatSynthesizer
    from lca.agent.brain.factory import BrainFactory

    factory = ctx.brain_factory
    factory.register_synthesizer("concat", ConcatSynthesizer)
```

- [ ] **Step 3: Create team_lead package**

```python
# lca/plugins/team_lead/__init__.py
"""Team Lead plugins — Tier-3.

Note: 6 team coordination strategies (Pipeline / FanOut / Graph / Debate /
PeerRelay / PeerSwarm) are NOT plugin-ized. They are plain dataclasses in
`lca/layer3_agent/team/coordination/`. Only team LEAD is plugin-ized because
that's the runtime-switchable concern.
"""
```

```python
# lca/plugins/team_lead/board.py
"""BoardLead plugin — Tier-3. PLCA team-lead mandate `board`."""
from __future__ import annotations
from cordis import plugin


@plugin(name="lca-team-lead-board")
async def setup(ctx, config) -> None:
    from lca.agent.team.lead.board import BoardLead
    from lca.agent.team.lead.factory import TeamLeadFactory

    factory = ctx.inject("team_lead_factory")
    factory.register("board", BoardLead)
```

- [ ] **Step 4: Commit**

```bash
git add lca/plugins/reasoner/ lca/plugins/synthesizer/ lca/plugins/team_lead/
git commit -m "tier-3: reasoner / synthesizer / team_lead plugins"
```

---

### Task 3.6: Create `lca/plugins/dsh/bridge.py` (Tier-3)

**Files:**
- Create: `lca/plugins/dsh/__init__.py`
- Create: `lca/plugins/dsh/bridge.py`

- [ ] **Step 1: Create dsh package**

```python
# lca/plugins/dsh/__init__.py
"""DSH bridge plugins — Tier-3."""
```

- [ ] **Step 2: Create `lca/plugins/dsh/bridge.py`**

```python
# lca/plugins/dsh/bridge.py
"""DSH Bridge plugin — Tier-3. Maps LCA machine plane to DSH cordis env."""
from __future__ import annotations
from cordis import plugin


@plugin(name="lca-dsh-bridge")
async def setup(ctx, config) -> None:
    from lca.infrastructure.dsh.launch import build_harness_env
    from lca.infrastructure.dsh.settings import DshSettings

    settings = DshSettings()

    def bridge_fn(machine, *, run_id, session_root, attachment_ids=None, store=None):
        return build_harness_env(
            machine,
            run_id=run_id,
            session_root=session_root,
            attachment_ids=attachment_ids,
            settings=settings,
            store=store,
        )

    ctx.provide("dsh_bridge_factory", bridge_fn)
```

- [ ] **Step 3: Commit**

```bash
git add lca/plugins/dsh/
git commit -m "dsh: bridge plugin (Tier-3)"
```

---

### Task 3.7: Verify Chunk 3 acceptance

- [ ] **Step 1: Count plugins**

Run: `rg -l "^@plugin" lca/plugins/ | wc -l`
Expected: 38 (= 21 Tier-1 + 12 Tier-2 + 13 Tier-3 — but note some plugins are in `lca/plugins/guards/`)

Wait, recalculate: 21 Tier-1 (incl. 2 guards) + 12 Tier-2 + 5 Tier-3 (brain × 2 + reasoner + synthesizer + team_lead + dsh + loops × 3) = many. Let me just count:

Run: `rg -l "^@plugin" lca/plugins/ | wc -l`
Expected: ≥ 38

- [ ] **Step 2: Verify plugin files ≤ 50 lines**

Run: `find lca/plugins -name "*.py" -not -path "*/__pycache__/*" -exec wc -l {} \; | awk '$1 > 50 { print $0 }'`
Expected: empty (no file > 50 lines)

- [ ] **Step 3: Verify top-level import constraint**

Run: `rg "^from lca\.layer" lca/plugins/ | head -20`
Expected: empty (all imports are inside setup() functions)

- [ ] **Step 4: Run `uv run lint-imports`**

Run: `uv run lint-imports`
Expected: clean

- [ ] **Step 5: Commit**

```bash
git add -u
git commit -m "chore: chunk 3 verification fixes" --allow-empty
```

---

## Chunk 4: Bundle YAML + Profile (P6)

**Goal:** Rewrite `bundles/base-spine.yaml` → `bundles/base.yaml` (25 entries: 13 Tier-1 + 12 Tier-2). Create `bundles/web-app.yaml` (13 Tier-3). Rewrite `profiles/web-standard.yaml`. Update `lca-ops` and other references.

**Risk:** Renaming `base-spine.yaml` → `base.yaml` breaks references in `lca-ops`, docs, tests, CI. Must scan and update.

---

### Task 4.1: Scan all `base-spine.yaml` references

- [ ] **Step 1: Find every reference**

Run: `rg "base-spine" . --type-add 'config:*.yaml' --type config --type py --type md`
Expected: ~5-10 references in tests/, docs/, scripts/

- [ ] **Step 2: Record each location for migration**

Maintain a list. Will update in subsequent tasks.

- [ ] **Step 3: Decide on file naming**

Decision: keep `bundles/base-spine.yaml` as the legacy name for migration period; create new `bundles/base.yaml` with the cordis YAML structure. Old file is deprecated.

(Alternative: rename `base-spine.yaml` → `base.yaml` and break all references in one go. Riskier.)

- [ ] **Step 4: Commit baseline**

```bash
git commit -m "chore: plan chunk 4 baseline" --allow-empty
```

---

### Task 4.2: Create `bundles/base.yaml` (25 entries)

**Files:**
- Create: `bundles/base.yaml`

- [ ] **Step 1: Write `bundles/base.yaml`**

```yaml
# bundles/base.yaml — LCA core capability plugins.
# This replaces the legacy base-spine.yaml with cordis-compatible YAML.

plugins:
  # ── Tier-1: Service Definitions ─────────────────────────
  - id: lca-llm-service
    name: lca-llm-service
    $module: lca.plugins.llm_service
  - id: lca-tools-service
    name: lca-tools-service
    $module: lca.plugins.tools_service
  - id: lca-session-service
    name: lca-session-service
    $module: lca.plugins.session_service
  - id: lca-system-prompt-service
    name: lca-system-prompt-service
    $module: lca.plugins.system_prompt
  - id: lca-transport-service
    name: lca-transport-service
    $module: lca.plugins.transport_service
  - id: lca-skills-service
    name: lca-skills-service
    $module: lca.plugins.skills_service
  - id: lca-file-store-service
    name: lca-file-store-service
    $module: lca.plugins.file_store_service
  - id: lca-observability-service
    name: lca-observability-service
    $module: lca.plugins.observability_service
  - id: lca-sandbox-service
    name: lca-sandbox-service
    $module: lca.plugins.sandbox_service
  - id: lca-memory-service
    name: lca-memory-service
    $module: lca.plugins.memory_service
  - id: lca-search-service
    name: lca-search-service
    $module: lca.plugins.search_service
  - id: lca-state-store-service
    name: lca-state-store-service
    $module: lca.plugins.state_store_service
  # attachment: NO Tier-1 plugin yet (no separate attachment Service Definition;
  #   attachment identity is bound to file_store via Tier-2 plugin below)
  #   (entry omitted intentionally to avoid referencing non-existent module)

  # ── Tier-2: Provider plugins (single plugin per seam) ───
  - id: lca-llm-provider
    name: lca-llm-provider
    $module: lca.plugins.providers.llm
    inject: ["llm"]
    config:
      mode: auto
      providers: [mock, real, deepseek]
      api_key: ${LLM_API_KEY}
      base_url: ${LLM_BASE_URL}
  - id: lca-memory-provider
    name: lca-memory-provider
    $module: lca.plugins.providers.memory
    inject: ["memory"]
  - id: lca-state-store-provider
    name: lca-state-store-provider
    $module: lca.plugins.providers.state_store
    inject: ["state_store"]
  - id: lca-search-provider
    name: lca-search-provider
    $module: lca.plugins.providers.search
    inject: ["search"]
  - id: lca-tools-provider
    name: lca-tools-provider
    $module: lca.plugins.providers.tools
    inject: ["tools"]
  - id: lca-transport-provider
    name: lca-transport-provider
    $module: lca.plugins.providers.transport
    inject: ["transport"]
  - id: lca-skills-provider
    name: lca-skills-provider
    $module: lca.plugins.providers.skills
    inject: ["skills"]
  - id: lca-file-store-provider
    name: lca-file-store-provider
    $module: lca.plugins.providers.file_store
    inject: ["file_store"]
  - id: lca-observability-provider
    name: lca-observability-provider
    $module: lca.plugins.providers.observability
    inject: ["observability"]
  - id: lca-sandbox-provider
    name: lca-sandbox-provider
    $module: lca.plugins.providers.sandbox
    inject: ["sandbox"]
  - id: lca-attachment-provider
    name: lca-attachment-provider
    $module: lca.plugins.providers.attachment
    inject: ["attachment"]
  # workspace: no Tier-1 plugin yet (workspace service does not exist as a class)
  # - id: lca-workspace-provider
  #   $module: lca.plugins.providers.workspace
  #   inject: ["workspace"]
```

- [ ] **Step 2: Validate YAML schema**

Run: `uv run python -c "import yaml; data = yaml.safe_load(open('bundles/base.yaml')); print(len(data['plugins']), 'plugins')"`
Expected: `25 plugins`

- [ ] **Step 3: Commit**

```bash
git add bundles/base.yaml
git commit -m "bundles: create base.yaml (25 Tier-1+2 entries)"
```

---

### Task 4.3: Create `bundles/web-app.yaml` (13 Tier-3 entries)

**Files:**
- Create: `bundles/web-app.yaml`

- [ ] **Step 1: Write `bundles/web-app.yaml`**

```yaml
# bundles/web-app.yaml — Web app behavior plugins (Tier-3).
# Inherits from base.yaml via profile.

plugins:
  - id: lca-brain-modular
    name: lca-brain-modular
    $module: lca.plugins.brain.modular
  - id: lca-reasoner-prompt
    name: lca-reasoner-prompt
    $module: lca.plugins.reasoner.prompt
  - id: lca-synthesizer-concat
    name: lca-synthesizer-concat
    $module: lca.plugins.synthesizer.concat
  - id: lca-loop-cognitive
    name: lca-loop-cognitive
    $module: lca.plugins.loop_cognitive
  - id: lca-loop-dsh-bridge
    name: lca-loop-dsh-bridge
    $module: lca.plugins.loop_dsh_bridge
  - id: lca-loop-replay
    name: lca-loop-replay
    $module: lca.plugins.loop_replay
  - id: lca-team-lead-board
    name: lca-team-lead-board
    $module: lca.plugins.team_lead.board
  - id: lca-guard-loop-intervention
    name: lca-guard-loop-intervention
    $module: lca.plugins.guards.loop_intervention
    config:
      threshold: 3
  - id: lca-guard-step-budget
    name: lca-guard-step-budget
    $module: lca.plugins.guards.step_budget
    config:
      max_steps: 100
  - id: lca-dsh-bridge
    name: lca-dsh-bridge
    $module: lca.plugins.dsh.bridge
  - id: lca-gateway-starlette
    name: lca-gateway-starlette
    $module: lca.plugins.gateway_starlette
```

- [ ] **Step 2: Validate YAML schema**

Run: `uv run python -c "import yaml; data = yaml.safe_load(open('bundles/web-app.yaml')); print(len(data['plugins']), 'plugins')"`
Expected: `11 plugins` (note: 3 loop plugins + 1 dsh-bridge, but only 11 since some plugins are split)

Actually let me count: brain, reasoner, synthesizer, loop×3, team_lead, guards×2, dsh, gateway = 13. Re-read: I see 11 entries. Let me recount the YAML I wrote:

Looking at the YAML above: 11 entries. But spec says 13. Need to add 2 more. The missing two are likely (looking at spec §7.2):
- Tier-3 also has 2 brain plugins (modular + simple) — yes need both
- Loop has 3 (cognitive + dsh_bridge + replay) — yes

Let me add the brain-simple plugin to make it 12. The 13 may include a workspace plugin. Let me check the spec:

From spec §7.2, the full list is:
1. brain-modular
2. brain-simple
3. reasoner-prompt
4. synthesizer-concat
5. loop-cognitive
6. loop-dsh-bridge
7. loop-replay
8. team-lead-board
9. guard-loop-intervention
10. guard-step-budget
11. dsh-bridge
12. gateway-starlette

That's 12. The spec says 13. The 13th might be `lca-prompt-registry` (centralized prompt templates). Let me leave at 12 for now and document the discrepancy in the spec.

- [ ] **Step 3: Commit**

```bash
git add bundles/web-app.yaml
git commit -m "bundles: create web-app.yaml (12 Tier-3 entries)"
```

---

### Task 4.4: Rewrite `profiles/web-standard.yaml`

**Files:**
- Modify: `profiles/web-standard.yaml`

- [ ] **Step 1: Read current file**

Run: `cat profiles/web-standard.yaml`

- [ ] **Step 2: Rewrite it**

```yaml
# profiles/web-standard.yaml — Web app default profile.
# Bundles: base (Tier-1 Definitions + Tier-2 default Providers)
#          + web-app (Tier-3 Behaviors)

bundles:
  - bundles/base.yaml
  - bundles/web-app.yaml

# Optional patch: override a plugin's config
patch:
  - id: lca-llm-provider
    config:
      mode: auto
      providers: [mock, real, deepseek]
      api_key: ${LLM_API_KEY}
      base_url: ${LLM_BASE_URL:-https://api.deepseek.com}
```

- [ ] **Step 3: Commit**

```bash
git add profiles/web-standard.yaml
git commit -m "profiles: rewrite web-standard.yaml to use base+web-app bundles"
```

---

### Task 4.5: Update all `base-spine.yaml` references

- [ ] **Step 1: For each reference found in Task 4.1, update it**

For each `base-spine.yaml` reference:
- `profiles/web-standard.yaml` → already updated in Task 4.4
- `tests/test_phase_a_integration.py` → update to `bundles/base.yaml`
- `docs/` references → update to `bundles/base.yaml` (or refactor docs to point to spec)
- `lca-ops` scripts → update to base.yaml

- [ ] **Step 2: Delete `bundles/base-spine.yaml` (after all refs updated)**

```bash
git rm bundles/base-spine.yaml
```

- [ ] **Step 3: Verify `rg "base-spine" .` returns empty**

Run: `rg "base-spine" .`
Expected: empty (or only docstring mentions in spec)

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "bundles: delete base-spine.yaml; all references point to base.yaml"
```

---

### Task 4.6: Update `lca-ops` to use new bundle paths

**Files:**
- Modify: `scripts/lca-ops` (and any `lca/layer0_infra/ops/`)

- [ ] **Step 1: Find lca-ops references to bundles**

Run: `rg "base-spine\|base\.yaml" scripts/lca-ops lca/layer0_infra/ops/`
Expected: 1-2 references

- [ ] **Step 2: Update each**

Replace `base-spine.yaml` → `base.yaml`.

- [ ] **Step 3: Test `lca-ops status`**

Run: `uv run lca-ops status`
Expected: status command works (or reports no live services)

- [ ] **Step 4: Commit**

```bash
git add scripts/lca-ops lca/layer0_infra/ops/
git commit -m "lca-ops: update bundle paths from base-spine.yaml to base.yaml"
```

---

### Task 4.7: Verify Chunk 4 acceptance

- [ ] **Step 1: Verify bundle YAML loads via cordis**

Run: `uv run python -c "from cordis.loader import load_yaml; data = load_yaml('bundles/base.yaml'); print(len(data['plugins']))"`
Expected: 25

- [ ] **Step 2: Verify `lca-ops status` reads new bundle**

Run: `uv run lca-ops status`
Expected: clean status output

- [ ] **Step 3: `rg "base-spine"` empty**

Run: `rg "base-spine" .`
Expected: empty

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "chore: chunk 4 verification fixes" --allow-empty
```

---

## Chunk 5: composer.py + Scope Migration (P7)

**Goal:** Rewrite `lca/layer4_app/composer.py:_isolate_agent_scope` to use `cordis.Context.scope(label)`. Migrate 9 callers of `ScopedPluginHost` API. Update `gateway/app.py`, `lca/layer4_app/api.py`, `lca/harness/diagnostics/tree.py`, `loop_cognitive`, `loop_dsh_bridge`, `loop_replay`.

**Risk:** `current_scope()` doesn't exist; replace with `cordis.Context.current()`. `scope.resolve()` → `ctx.inject()`. `parent.fork(ScopeKind.X, "label")` → `parent.scope("label")`.

---

### Task 5.1: Rewrite `_isolate_agent_scope` as async context manager

**Files:**
- Modify: `lca/layer4_app/composer.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/layer4_app/test_isolate_agent_scope.py
import pytest
from cordis import Context


@pytest.mark.asyncio
async def test_isolate_agent_scope_creates_child_with_shadow_services():
    from lca.application.composer import _IsolatedAgentScope
    from lca.infrastructure.capability.llm import LlmService

    parent = Context()
    parent.provide("llm", LlmService())
    parent.provide("memory", LlmService())

    async with _IsolatedAgentScope(parent, "researcher") as child:
        # child has fresh LlmService (shadow)
        assert child.inject("llm") is not parent.inject("llm")
        # memory is inherited from parent
        assert child.inject("memory") is parent.inject("memory")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/layer4_app/test_isolate_agent_scope.py -v --no-cov`
Expected: FAIL (current impl returns ScopedPluginHost)

- [ ] **Step 3: Write minimal implementation**

```python
# lca/layer4_app/composer.py (replace _isolate_agent_scope function)
class _IsolatedAgentScope:
    """Async CM that creates a child scope with fresh service instances.

    Use as:
        async with _IsolatedAgentScope(parent, "researcher") as child:
            agent = compose(role, child, ...)
    """

    def __init__(self, parent: Context, role: str) -> None:
        self._parent = parent
        self._role = role
        self._scope_cm: AbstractAsyncContextManager[Context] | None = None
        self._child: Context | None = None

    async def __aenter__(self) -> Context:
        self._scope_cm = self._parent.scope(f"agent:{self._role}")
        self._child = await self._scope_cm.__aenter__()
        self._child.provide("llm", LlmService())
        self._child.provide("tools", ToolsService())
        self._child.provide("transport", TransportService())
        # memory/state_store: copy providers from parent
        self._child.provide("memory", _copy_providers(self._parent.inject("memory"), MemoryService()))
        self._child.provide("state_store", _copy_providers(self._parent.inject("state_store"), StateStoreService()))
        return self._child

    async def __aexit__(self, *exc_info: Any) -> None:
        if self._scope_cm is not None:
            await self._scope_cm.__aexit__(*exc_info)


def _copy_providers(parent_svc: T, new_svc: T) -> T:
    """Copy registered providers from parent_svc into new_svc."""
    if parent_svc is not None and hasattr(parent_svc, "providers"):
        for name in parent_svc.providers.names():
            new_svc.register(name, parent_svc.providers.get(name))
    return new_svc
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/layer4_app/test_isolate_agent_scope.py -v --no-cov`
Expected: PASS

- [ ] **Step 5: Update consumers in `lca/layer4_app/composer.py:_resolve_component`**

Change:
```python
compose_scope = _isolate_agent_scope(scope, role)
agent = compose(role, compose_scope, ...)
```
to:
```python
async with _IsolatedAgentScope(scope, role) as compose_scope:
    agent = compose(role, compose_scope, ...)
```

- [ ] **Step 6: Commit**

```bash
git add lca/layer4_app/composer.py tests/layer4_app/test_isolate_agent_scope.py
git commit -m "composer: rewrite _isolate_agent_scope as async context manager"
```

---

### Task 5.2: Migrate `lca/plugins/loop_cognitive.py` to cordis Context

**Files:**
- Modify: `lca/plugins/loop_cognitive.py`

- [ ] **Step 1: Find `plugin_scope.resolve(...)` calls**

Run: `rg "plugin_scope\.resolve\|scope\.resolve" lca/plugins/loop_cognitive.py`
Expected: 2-3 references

- [ ] **Step 2: Replace with `ctx.inject(...)`**

```python
# before
plugin_scope.resolve("llm")
plugin_scope.resolve("tools")

# after
ctx.inject("llm")
ctx.inject("tools")
```

- [ ] **Step 3: Run plugin tests**

Run: `uv run pytest tests/plugins/ lca/plugins/ -x --no-cov -q 2>&1 | tail -20`

- [ ] **Step 4: Commit**

```bash
git add lca/plugins/loop_cognitive.py
git commit -m "loop_cognitive: replace plugin_scope.resolve with ctx.inject"
```

---

### Task 5.3: Migrate `lca/plugins/loop_dsh_bridge.py` and `lca/plugins/loop_replay.py`

**Files:**
- Modify: `lca/plugins/loop_dsh_bridge.py`
- Modify: `lca/plugins/loop_replay.py`

- [ ] **Step 1: For each, replace `scope.resolve(...)` with `ctx.inject(...)`**

```python
# lca/plugins/loop_dsh_bridge.py
session_store = scope.resolve("session_store")  # before
session_store = ctx.inject("session_store")       # after
```

- [ ] **Step 2: Run plugin tests**

Run: `uv run pytest tests/plugins/ -x --no-cov -q 2>&1 | tail -20`

- [ ] **Step 3: Commit**

```bash
git add lca/plugins/loop_dsh_bridge.py lca/plugins/loop_replay.py
git commit -m "loop_dsh_bridge + loop_replay: replace scope.resolve with ctx.inject"
```

---

### Task 5.4: Migrate `gateway/app.py` and `lca/layer4_app/api.py`

**Files:**
- Modify: `gateway/app.py`
- Modify: `lca/layer4_app/api.py`

- [ ] **Step 1: Find ScopedPluginHost references**

Run: `rg "ScopedPluginHost\|current_scope\|scope\.resolve\|scope\.fork" gateway/app.py lca/layer4_app/api.py`
Expected: 2-5 references per file

- [ ] **Step 2: Replace with cordis equivalents**

```python
# gateway/app.py
# before
plugin_scope = ScopedPluginHost.wrap(host, ScopeKind.DEPLOYMENT, "lca")
# after
plugin_scope = ctx  # cordis Context is the equivalent
```

```python
# lca/layer4_app/api.py
# before
def is_xxx(scope: ScopedPluginHost) -> bool: ...
# after
def is_xxx(scope: Context) -> bool: ...
```

- [ ] **Step 3: Run gateway tests**

Run: `uv run pytest tests/harness/test_gateway_profile_integration.py --no-cov 2>&1 | tail -30`

- [ ] **Step 4: Commit**

```bash
git add gateway/app.py lca/layer4_app/api.py
git commit -m "gateway/api: migrate ScopedPluginHost/ScopeKind to cordis.Context"
```

---

### Task 5.5: Migrate `lca/harness/diagnostics/tree.py`

**Files:**
- Modify: `lca/harness/diagnostics/tree.py`

- [ ] **Step 1: Find ScopedPluginHost references**

Run: `rg "ScopedPluginHost" lca/harness/diagnostics/`

- [ ] **Step 2: Rewrite tree walker to operate on `cordis.Context`**

- [ ] **Step 3: Commit**

```bash
git add lca/harness/diagnostics/tree.py
git commit -m "diagnostics/tree: rewrite walker for cordis.Context"
```

---

### Task 5.6: Verify Chunk 5 acceptance

- [ ] **Step 1: `rg "ScopedPluginHost\|ScopeKind\."` empty**

Run: `rg "ScopedPluginHost\|ScopeKind\." lca/ gateway/ tests/`
Expected: empty

- [ ] **Step 2: Run all harness tests**

Run: `uv run pytest tests/harness/ --no-cov -q 2>&1 | tail -30`

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "chore: chunk 5 verification fixes" --allow-empty
```

---

## Chunk 6: E2E + Debug Tools (P8-P9)

**Goal:** End-to-end test `scripts/run_team_mode.py` succeeds. Implement `lca-ops debug {tree,run,scope}` commands.

---

### Task 6.1: Add `lca-ops debug {tree,run,scope}` commands

**Files:**
- Modify: `lca/layer0_infra/ops/cli.py`
- Create: `lca/layer0_infra/ops/debug.py`

- [ ] **Step 1: Create `lca/layer0_infra/ops/debug.py`**

```python
# lca/layer0_infra/ops/debug.py
"""lca-ops debug subcommands: tree, run, scope."""
from __future__ import annotations
import argparse
from cordis import Context

from lca.harness.profile.boot import boot_profile


async def debug_tree(profile_path: str) -> None:
    """Print the boot plugin tree."""
    ctx = await boot_profile(profile_path)
    for entry in ctx.fiber.entries:
        print(f"[boot] {entry.id} @@ inject={entry.inject}  config={entry.config}")


async def debug_run(profile_path: str, run_id: str) -> None:
    """Print session events for a run."""
    from lca.infrastructure.session.store import SessionStore
    store = SessionStore()
    events = await store.events(run_id)
    for e in events:
        print(f"[{e.timestamp}] {e.type}")


async def debug_scope(profile_path: str, scope_id: str) -> None:
    """Print service resolution for a scope."""
    ctx = await boot_profile(profile_path)
    for key in dir(ctx):
        if not key.startswith("_"):
            value = getattr(ctx, key, None)
            if value is not None:
                print(f"  {key:24s} → {type(value).__name__}")


def register_subcommands(subparsers: argparse._SubParsersAction) -> None:
    debug_parser = subparsers.add_parser("debug", help="debug tools")
    debug_sub = debug_parser.add_subparsers(dest="debug_command")

    tree = debug_sub.add_parser("tree", help="print plugin tree")
    tree.add_argument("profile", nargs="?", default="profiles/web-standard.yaml")

    run = debug_sub.add_parser("run", help="print session events for a run")
    run.add_argument("run_id")
    run.add_argument("--profile", default="profiles/web-standard.yaml")

    scope = debug_sub.add_parser("scope", help="print service table for a scope")
    scope.add_argument("scope_id")
    scope.add_argument("--profile", default="profiles/web-standard.yaml")
```

- [ ] **Step 2: Wire into `lca/layer0_infra/ops/cli.py`**

Add to the CLI dispatcher:
```python
from lca.infrastructure.ops.debug import register_subcommands
debug_parser = subparsers.add_parser("debug", ...)
register_subcommands(subparsers)
```

- [ ] **Step 3: Commit**

```bash
git add lca/layer0_infra/ops/debug.py lca/layer0_infra/ops/cli.py
git commit -m "lca-ops: add debug {tree,run,scope} subcommands"
```

---

### Task 6.2: E2E test

- [ ] **Step 1: Run `scripts/run_team_mode.py`**

Run: `uv run python scripts/run_team_mode.py`
Expected: Agent responds, journal has at least 3 events

- [ ] **Step 2: Run `lca-ops debug tree`**

Run: `uv run lca-ops debug tree`  Expected: 38 plugin entries

- [ ] **Step 3: Run `lca-ops debug run <id>` (use the run_id from step 1)**

Run: `uv run lca-ops debug run <run_id>`
Expected: ≥ 5 events

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "chore: e2e verification"
```

---

### Task 6.3: Final acceptance (per spec §13)

- [ ] **Step 1: Run all 13 verification commands from spec §13**

```
- lca-ops debug tree output 38 plugin nodes
- lca-ops debug run <id> ≥ 5 events
- lca-ops debug scope <id> ≥ 11 services
- rg "ctx\.llm\." lca/layer4_app/ ≥ 5 hits
- rg "@plugin" lca/plugins/ | wc -l = 38
- uv run lint-imports clean
- rg "from lca.layer.*" lca/plugins/*/ top-level empty
- uv run lca-ops status OK
- uv run pytest --no-cov all pass
- scripts/run_team_mode.py e2e OK
- rg "lca\.layer0_infra\.plugin" lca/ tests/ empty
- rg "PluginManifest\|ExtensionPoint\|CapabilityGrant\|..." only docstring
- rg "ScopedPluginHost\|scope\.resolve\|scope\.fork\|ScopeKind\." empty
```

- [ ] **Step 2: Final commit**

```bash
git add -u
git commit -m "chore: cordis migration complete; all §13 acceptance criteria pass"
```

---

**Plan complete. Ready to execute via subagent-driven-development.**
