# ADR-0256: 工具命名空间划分规范实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 终结单工具命名空间退化，将 namespace 作为工具 Factory 的显式声明元数据，按 8 域（core/file/shell/memory/skill/web/agent/ext）统一模型决策粒度、defer 加载粒度与安全审批边界。

**Architecture:** 基于 LCA 单向分层（contracts → infrastructure → cognition → runtime），将 namespace 作为 Tool Protocol 固有元数据，彻底剥离 ToolsService 中央映射表；在 ToolDeferSession 实施零回退 fail-fast；Cognition Wire Gate 按 namespace 判定可见性；审批引擎接入 shell 域审批策略；同 PR 彻底下线驼峰命名兼容。

**Tech Stack:** Python 3.12+, Pydantic v2, Pytest, UV, LCA Framework Contracts & Seams.

---

### Task 1: Contracts 层强化与 DeferPolicy 8 域闭环

**Files:**
- Modify: `lca/contracts/protocols/runtime/infra/infra.py:43-60`
- Modify: `lca/contracts/models/core/execution/tool.py:41-65`
- Modify: `lca/infrastructure/tool_defer/policy.py:10-39`
- Create: `tests/contracts/test_tool_namespace_contracts.py`
- Does NOT own: `lca/cognition/`, `lca/runtime/`, `lca/session/`, `lca/plugins/transport/` (AP-01)
- Invariants to test: `Tool.namespace` 契约存在且必填，`DeferPolicy.namespace_descriptions` 覆盖 8 大领域无遗漏，`eager_namespaces` 默认仅含 `core` (AP-02)

**Step 1: Write the failing test**
Create `tests/contracts/test_tool_namespace_contracts.py`:
```python
from lca.contracts.models.core.execution.tool import ToolApi
from lca.contracts.protocols import Tool
from lca.infrastructure.tool_defer.policy import DeferPolicy, STANDARD_NAMESPACES


def test_tool_protocol_requires_namespace() -> None:
    class IncompleteTool:
        name = "test"
        description = "test"
        parameters = {}
        is_idempotent = True
        effect_kind = "ephemeral"
        default_timeout_s = 10
        async def execute(self, args): return None
        def validate(self, args): return None

    # Lacks namespace -> not an instance of Tool protocol
    assert not isinstance(IncompleteTool(), Tool)


def test_tool_api_has_namespace_field() -> None:
    api = ToolApi(name="foo", description="bar", parameters={}, namespace="file")
    assert api.namespace == "file"


def test_defer_policy_standard_eight_namespaces() -> None:
    policy = DeferPolicy.default()
    assert policy.eager_namespaces == frozenset({"core"})
    assert set(policy.namespace_descriptions.keys()) == {
        "core", "file", "shell", "memory", "skill", "web", "agent", "ext"
    }
    assert "shell" in policy.namespace_approval
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/contracts/test_tool_namespace_contracts.py -v`
Expected: FAIL (missing `namespace` attribute and `STANDARD_NAMESPACES`).

**Step 3: Write minimal implementation**
1. In `lca/contracts/protocols/runtime/infra/infra.py`, add `namespace: ClassVar[str]` to `Tool(Protocol)`.
2. In `lca/contracts/models/core/execution/tool.py`, add `namespace: str = ""` to `ToolApi`.
3. In `lca/infrastructure/tool_defer/policy.py`, define `STANDARD_NAMESPACES`, set `eager_namespaces = frozenset({"core"})`, define default `namespace_descriptions` (8 句精准中文描述), and `namespace_approval: Mapping[str, str] = field(default_factory=lambda: {"shell": "require_approval"})`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/contracts/test_tool_namespace_contracts.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/contracts/ lca/infrastructure/tool_defer/policy.py tests/contracts/test_tool_namespace_contracts.py
git commit -m "feat(contracts): add namespace to Tool and ToolApi, enforce 8 domains in DeferPolicy"
```

---

### Task 2: 工具 Factory 与 Manifest 显式声明 Namespace 并下沉 SSOT

**Files:**
- Modify: `lca/infrastructure/tools/builder/builder.py:95-110`
- Modify: `lca/infrastructure/tools/lca_computer/manifest.py:48-96`
- Modify: `lca/infrastructure/tools/web_search/__init__.py:23-57`
- Modify: `lca/infrastructure/tools/ask_user/__init__.py:17-57`
- Modify: `lca/infrastructure/tools/skills/tool/set.py` & skill tool classes
- Modify: `lca/infrastructure/tools/assistant/memory_tools.py:47-60`
- Modify: `lca/infrastructure/tools/box/` tool classes
- Modify: `lca/infrastructure/vocal/tool_adapter.py`
- Modify: `lca/infrastructure/tool_defer/tool_search.py:26-60`
- Modify: `lca/plugins/tools/composio_tools.py:60-69`
- Modify: `lca/infrastructure/capability/tools/tools.py:46-125`
- Create: `tests/infrastructure/tools/test_tools_namespace_declaration.py`
- Does NOT own: `lca/cognition/`, `lca/session/`, prompt templates (AP-01)
- Invariants to test: 所有已注册工具的 `tool.namespace` 属性非空且属于 8 大合法域之一；`ToolsService._tool_namespaces` 彻底删除 (AP-02)

**Step 1: Write the failing test**
Create `tests/infrastructure/tools/test_tools_namespace_declaration.py`:
```python
from lca.infrastructure.capability.tools.tools import ToolsService
from lca.infrastructure.tools.builder.builder import build_tools_from_manifest
from lca.contracts.models.core.execution.tool import ToolApi, ToolManifest, ToolMeta
from lca.infrastructure.tool_defer.policy import STANDARD_NAMESPACES


def test_builder_propagates_namespace() -> None:
    manifest = ToolManifest(
        identifier="test",
        type="builtin",
        api=(ToolApi(name="foo", description="d", parameters={}, namespace="file"),),
        meta=ToolMeta(avatar="x", title="t", description="d"),
    )
    tools = build_tools_from_manifest(manifest, object())
    assert len(tools) == 1
    assert tools[0].namespace == "file"


def test_tools_service_has_no_central_tool_namespaces_dict() -> None:
    service = ToolsService()
    assert not hasattr(service, "_tool_namespaces")
    assert not hasattr(service, "tool_namespaces")
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/infrastructure/tools/test_tools_namespace_declaration.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
1. In `lca/infrastructure/tools/builder/builder.py`, inject `"namespace": api.namespace` into the dynamic `tool_cls` attributes in `_build_single_tool`.
2. In `lca/infrastructure/tools/lca_computer/manifest.py`, update `_ALL_API_SPECS` to include namespace (`file` for file ops, `shell` for runCommand/execScript/executeCode/killCommand/getCommandOutput).
3. In `web_search/__init__.py`, set `namespace="web"`.
4. In `ask_user/__init__.py`, set `namespace="agent"`.
5. In `memory_tools.py`, set `namespace: ClassVar[str] = "memory"` on `_BaseMemoryTool`.
6. In `skills/`, set `namespace: ClassVar[str] = "skill"` on skill tools.
7. In `tool_search.py`, set `namespace: ClassVar[str] = "core"`.
8. In `tools/box/` and `vocal/tool_adapter.py`, declare `file` / `shell` / `agent`.
9. In `lca/infrastructure/capability/tools/tools.py`, remove `_tool_namespaces` and `tool_namespaces()`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/infrastructure/tools/test_tools_namespace_declaration.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/infrastructure/tools/ lca/infrastructure/capability/tools/ lca/plugins/ tests/infrastructure/tools/test_tools_namespace_declaration.py
git commit -m "feat(tools): declare explicit namespace on all tool classes and remove ToolsService central mapping"
```

---

### Task 3: ToolDeferSession 协议升级与 ToolSearch 批量加载

**Files:**
- Modify: `lca/infrastructure/tool_defer/session.py:64-150`
- Modify: `lca/infrastructure/tool_defer/tool_search.py:26-85`
- Modify: `lca/nodes/concept/tool_fork/dispatch.py:314-324`
- Modify: `tests/infrastructure/tool_defer/test_session.py`
- Create: `tests/infrastructure/tool_defer/test_tool_search_batch.py`
- Does NOT own: `lca/cognition/brain/` (AP-01)
- Invariants to test: `update_turn` 遇到缺少 namespace 的工具必抛 `ValueError`；删除 `"N tools:"` 降级文本；`tool_search` 支持 `namespaces: list[str]` 批量加载 (AP-02)

**Step 1: Write the failing test**
In `tests/infrastructure/tool_defer/test_tool_search_batch.py`:
```python
import pytest
from lca.infrastructure.tool_defer.session import ToolDeferSession, set_current_defer_session
from lca.infrastructure.tool_defer.policy import DeferPolicy
from lca.infrastructure.tool_defer.tool_search import ToolSearchTool


class FakeTool:
    def __init__(self, name: str, namespace: str) -> None:
        self.name = name
        self.namespace = namespace
        self.description = f"fake {name}"
        self.parameters = {"type": "object", "properties": {}}

    async def execute(self, args): return {}


@pytest.mark.asyncio
async def test_tool_search_batch_loading() -> None:
    policy = DeferPolicy.default()
    session = ToolDeferSession(policy)
    tools = (
        FakeTool("tool_search", "core"),
        FakeTool("readFile", "file"),
        FakeTool("memory_search", "memory"),
    )
    session.update_turn(tools)
    token = set_current_defer_session(session)
    try:
        searcher = ToolSearchTool()
        obs = await searcher.execute({"namespaces": ["file", "memory"]})
        assert obs.success is True
        assert "file" in session.loaded_namespaces
        assert "memory" in session.loaded_namespaces
        assert len(obs.payload["tools"]) == 2
    finally:
        session._loaded.clear()
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/infrastructure/tool_defer/test_tool_search_batch.py -v`
Expected: FAIL (argument validation error / missing update_turn signature).

**Step 3: Write minimal implementation**
1. In `lca/infrastructure/tool_defer/session.py`:
   - Change `update_turn(self, tools: Sequence[Tool]) -> None` (remove `namespaces` dict mapping argument).
   - Check `tool.namespace`: if empty or not in `self._policy.namespace_descriptions`, raise `ValueError(f"tool {tool.name!r} declares invalid namespace {getattr(tool, 'namespace', None)!r}")`.
   - Remove `"N tools:"` fallback in `_describe`.
   - In `load_namespace`, keep existing idempotent behavior; add `load_namespaces(self, namespaces: Sequence[str]) -> dict[str, Any]` to load multiple at once.
2. In `lca/infrastructure/tool_defer/tool_search.py`:
   - Accept either `namespace: str` or `namespaces: list[str]`.
   - Execute batch load across requested namespaces.
3. In `lca/nodes/concept/tool_fork/dispatch.py`:
   - Update call `_defer_session.update_turn(items)` without passing `forked.tool_namespaces()`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/infrastructure/tool_defer/test_session.py tests/infrastructure/tool_defer/test_tool_search_batch.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/infrastructure/tool_defer/ lca/nodes/concept/tool_fork/dispatch.py tests/infrastructure/tool_defer/
git commit -m "feat(defer): fail-fast on missing namespace and enable batch loading in tool_search"
```

---

### Task 4: Cognition Wire Gate 升级为 Namespace 可见性判定与驼峰双拼清理

**Files:**
- Modify: `lca/cognition/body/tools/tool_wire_gate.py:72-125`
- Modify: `tests/cognition/body/test_tool_arguments_wire_gate.py`
- Does NOT own: `lca/runtime/` (AP-01)
- Invariants to test: 调用未加载 namespace 的工具必须被 Wire Gate 拦截返回 guidance；`_name_forms` 彻底删除；驼峰工具名全面规范为 snake_case (AP-02)

**Step 1: Write the failing test**
Update `tests/cognition/body/test_tool_arguments_wire_gate.py` to verify namespace-level blocking and absence of `_name_forms`.

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/cognition/body/test_tool_arguments_wire_gate.py -v`
Expected: FAIL.

**Step 3: Write minimal implementation**
1. In `tool_wire_gate.py`:
   - Delete `_name_forms`.
   - In `unexposed_tool_block_observation`: look up `tool` from active registry or defer session; inspect `tool.namespace`.
   - If `tool.namespace not in session.loaded_namespaces and tool.namespace not in session.policy.eager_namespaces`:
     return Observation with error message:
     `f"tool {tc.tool_name} belongs to deferred namespace '{tool.namespace}' which is not loaded this turn. Call tool_search for its namespace before using it."`
2. Remove any remaining camelCase alias registration from `skills` or tool manifestations.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/cognition/body/test_tool_arguments_wire_gate.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/cognition/body/tools/tool_wire_gate.py tests/cognition/body/test_tool_arguments_wire_gate.py
git commit -m "feat(wire-gate): upgrade unexposed tool check to namespace granularity and drop camelCase shims"
```

---

### Task 5: 接入安全控制面：Shell 域审批策略挂载

**Files:**
- Modify: `lca/infrastructure/runtime_plane/access/approval_engine.py`
- Create: `tests/infrastructure/runtime_plane/test_namespace_approval_strategy.py`
- Does NOT own: `lca/contracts/` (AP-01)
- Invariants to test: 当 tool_calls 包含 `shell` 域工具时，审批策略必然生成 `ApprovalRequirement(required=True, reason_kind=ELEVATED_COMMAND)` (AP-02)

**Step 1: Write the failing test**
Create `tests/infrastructure/runtime_plane/test_namespace_approval_strategy.py`:
```python
from lca.contracts.models.core.execution.decision import ToolCall
from lca.contracts.models.core.execution.approval import ApprovalReasonKind
from lca.infrastructure.runtime_plane.access.approval_engine import NamespaceApprovalStrategy


def test_shell_namespace_triggers_approval() -> None:
    strategy = NamespaceApprovalStrategy()
    tool_calls = [ToolCall(tool_name="runCommand", tool_call_id="call_1", call_id="c1", arguments={"command": "ls"})]
    requirement = strategy.evaluate(tool_calls)
    assert requirement is not None
    assert requirement.required is True
    assert requirement.reason_kind == ApprovalReasonKind.ELEVATED_COMMAND


def test_file_namespace_auto_pass() -> None:
    strategy = NamespaceApprovalStrategy()
    tool_calls = [ToolCall(tool_name="readFile", tool_call_id="call_2", call_id="c2", arguments={"path": "/tmp/a"})]
    requirement = strategy.evaluate(tool_calls)
    assert requirement is None
```

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/infrastructure/runtime_plane/test_namespace_approval_strategy.py -v`
Expected: FAIL (`NamespaceApprovalStrategy` not defined).

**Step 3: Write minimal implementation**
1. Implement `NamespaceApprovalStrategy` in `lca/infrastructure/runtime_plane/access/approval_engine.py`.
2. Inspect tool's namespace mapping / registry; for any tool call in `"shell"` (or registered in `policy.namespace_approval`), emit `ApprovalRequirement(required=True, reason_kind=ApprovalReasonKind.ELEVATED_COMMAND, ...)`.
3. Register `NamespaceApprovalStrategy` in the default `ApprovalEngine`.

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/infrastructure/runtime_plane/test_namespace_approval_strategy.py -v`
Expected: PASS.

**Step 5: Commit**
```bash
git add lca/infrastructure/runtime_plane/access/approval_engine.py tests/infrastructure/runtime_plane/test_namespace_approval_strategy.py
git commit -m "feat(security): mount NamespaceApprovalStrategy to enforce REQUIRE_APPROVAL on shell domain"
```

---

### Task 6: ADR-0256 全量符合性集成验收与 Pre-push 门禁体检

**Files:**
- Create: `tests/scenario/test_tool_namespace_adr0256_conformance.py`
- Modify: `docs/plans/task.md`
- Does NOT own: out-of-scope non-LCA assets (AP-01)
- Invariants to test: 满足 ADR-0256 §10 全部 8 项验收标准 (AP-02)

**Step 1: Write the comprehensive conformance test**
Create `tests/scenario/test_tool_namespace_adr0256_conformance.py` covering:
1. 目录行严格 8 行且描述纯净；
2. 单域加载返回全部 9 个 file 工具；
3. 批量加载支持多域合并；
4. 漏配 namespace 启动抛错；
5. 未加载域被 Wire Gate 拦截重试；
6. `shell` 域触发审批；
7. 全局无 `_name_forms` 驼峰泄漏。

**Step 2: Run full regression and linter**
1. Run: `uv run pytest tests/scenario/test_tool_namespace_adr0256_conformance.py -v`
2. Run: `uv run pytest tests/infrastructure/tool_defer/ tests/cognition/body/test_tool_arguments_wire_gate.py tests/contracts/test_tool_namespace_contracts.py`
3. Run: `ruff check lca/ tests/`
4. Run: `git diff --check`

**Step 3: Update tracking table**
Update `docs/plans/task.md` to reflect all completed tasks with exact commit hashes and evidence.

**Step 4: Final commit**
```bash
git add tests/scenario/test_tool_namespace_adr0256_conformance.py docs/plans/task.md
git commit -m "test(conformance): add ADR-0256 8-domain tool namespace conformance suite"
```
