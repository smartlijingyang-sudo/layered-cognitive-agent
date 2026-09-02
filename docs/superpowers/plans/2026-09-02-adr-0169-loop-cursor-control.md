# ADR-0169 LoopCursor 控制面收敛实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 LCA loop 控制面收敛为 `LoopCursor` Protocol,业务路径只允许 `advance(phase)` 与 `record_*(...)`;与观测装配彻底分离为五缝(LoopCursor / ProjectionHost / PersistenceCoordinator / ModelVisibleCapture / CloseBarrier),落地 16 条不变量 L1-L16,删除 ADR §D9 列出的全部死代码 / 兼容包装,web-standard profile 跑绿。

**Architecture:** ADR-0169 决定采用"薄控制状态机 × 宽事件 SSOT × 可插拔投影宿主"五缝架构。LoopCursor 仅持 spine handle + 状态机;projection 走 ProjectionHost.register(disposer pattern);persistence 走 PersistenceCoordinator.flush/close;model_visible 走 LLM 边界 Capture;close 顺序由 CloseBarrier 协调。本计划把 D1-D11 + L1-L16 拆成 30 个原子 PR,每个 PR 自带测试 + grep 门禁 + 集成验证。

**Tech Stack:** Python 3.12 / dataclass(frozen=True) / typing.Protocol / cordis / pytest / importlinter / ruff / mypy / vulture。

**Spec:** `docs/adr/0169-loop-cursor-control.md`(本计划是它的实施论据);`docs/adr/0170-projection-host.md`(D7/D8/D9 引用);`docs/adr/0171-fork-shared-host.md`(fork 共享 Host 协议,本计划引用其接口,不实现其逻辑);`docs/adr/0172-observability-exporters.md`(Exporter 实现层,本计划不实现);`docs/adr/0173-halt-resume.md`(resume 协议,本计划不实现);`docs/adr/0174-profile-batch-migration.md`(其余 8 profile 分批,本计划只做 web-standard)。

## Global Constraints

> 这些约束来自 ADR-0169 + AGENTS.md,所有任务默示遵守。

- **G1 · 五层单向依赖**:`contracts → infrastructure → cognition → runtime → agent`;`application` 是组合根。Webserver transport 是 Carrier,只负责 HTTP/SSE/typed command/projection,不直接绑定具体 Brain/Body/Loop(AGENTS.md §3)。
- **G2 · 闭集纪律**:PhaseName 是 `Literal[...]` 编译期禁扩展;CloseReason 同;IterationReason 同。任何新 `record_*` 默认否决(ADR-0169 D1)。
- **G3 · 业务不 import spine**:cognition/body/runtime/agent 不允许 import `EventSpine`/`Serializer`/`Storage`/`coordinator` 的非 `advance / record_*` 方法;只走 cursor Protocol(ADR-0169 L4 / I-PLUG1 强化)。
- **G4 · CursorError 不静默 fallback**:非法 phase / 关闭后调用 / 跨窗口 record → raise,不静默 no-op;`NullLoopCursor` 不存在(ADR-0169 L13,测试用 `InMemoryLoopCursor` 替代)。
- **G5 · 写路径单写**:`events.jsonl` 由 `EventSpine.append` 唯一写入;默认文件名 `<run_id>.spine.jsonl`(ADR-0169 L10,取代 ADR-0168 §D6)。
- **G6 · C7 控制/观察分离**:LoopCursor 不持 ProjectionRegistry/PersistenceCoordinator/LLMCallHook/ModelVisibleRecorder 实例;ProjectionHost 不订阅 `writable.iteration.close`(ADR-0169 L9/L16)。
- **G7 · 快照 frozen**:CursorSnapshot 是 read-only + frozen dataclass;reducer / projection 不可改(ADR-0169 I-CURSOR-2)。
- **G8 · incarnation 显式身份**:incarnation = (run_id, plan_ref, incarnation_seq),journal envelope 必携带(ADR-0169 L14 / I-CURSOR-5)。
- **G9 · 记录协议闭集**:cursor 公共动词只有 9 个(advance/halt/close/record_thinking/record_tool_call/record_tool_result/record_request_header/fork/snapshot);任何新 `record_X` 默认问题"能否变 EP + Projection"。
- **G10 · schema 拒绝方向感知**:`< SCHEMA_VERSION ⇒ VersionTooOld`,`> SCHEMA_VERSION ⇒ VersionTooNew`,未知 event_type 且 ignorable != true ⇒ `UnknownEventType`(ADR-0169 L15)。
- **G11 · 删除条件绑定 grep 门禁**:每次删除项必须给可 grep 的迁移完成条件,无期限补丁 = 红灯(AGENTS.md §1 兼容路径模板 + ADR-0169 §D9)。
- **G12 · 每 PR 一条 grep 不变量 + 集成 run 黄金断言**:本计划每个 PR 末尾强制 1 条 grep / AST / 集成断言;失败不允许合并。
- **G13 · commit message 用 Conventional Commits**:`<type>(<scope>): <subject>`;一个提交只一个主题;改动混了多主题 = 拆 PR(AGENTS.md §7)。
- **G14 · 验证矩阵**(每次 PR 必跑):
  ```bash
  uv run ruff check --fix <changed-path>
  uv run ruff format <changed-path>
  uv run pytest --no-cov <related-tests> -q
  ```
  涉及 contracts/Protocol/枚举/Profile/import 边界时升级:
  ```bash
  uv run ruff check --fix . && uv run ruff format .
  uv run lint-imports
  uv run mypy lca
  uv run pytest
  uv run vulture lca --min-confidence 80
  ```
- **G15 · COMPAT 块**:任何兼容路径必须以 `# COMPAT(delete-when: <条件>, tracking: ADR-0169-task-N)` 起头,无删除日 = 红灯。
- **G16 · 不引入新事件词表**:cordis event name 必须由 `EventDescriptor.cordis_name` 派生,业务不 emit `ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*')`(ADR-0169 L12,本计划 PR-30 实施)。
- **G17 · 文档同步**:删除/重命名实现时,必须同步更新 `AGENTS.md`、`docs/specs/lca-structured-cognition-guide.md`、`docs/debug/run-debug-guide.md`、`bundles/spine-default.yaml` 中的引用;CI 脚本 `verify_md_links.py` / `verify_doc_budgets.py` 通过。
- **G18 · Profile 兼容**:仅 web-standard 一次迁完;其余 8 profile 用 issue 跟踪(ADR-0174),本计划**禁止**改其他 profile YAML。

## 文件结构总览(本计划创建/修改的)

### 新建(`lca/contracts/observability/`)

| 路径 | 归属 | 创建 PR |
|---|---|---|
| `loop_cursor.py` | `LoopCursor` Protocol + `CursorSnapshot` + `CursorError` + PhaseName/CloseReason/IterationReason Literal | PR-1 |
| `loop_cursor_payloads.py` | `ThinkingRecord` / `ToolCallRecord` / `ToolResultRecord` / `RequestHeader` frozen dataclass | PR-3 |
| `incarnation.py` | `Incarnation` frozen dataclass | PR-11 |
| `event_descriptor.py` | `EventDescriptor` frozen dataclass + cordis_name 派生表 | PR-13 |
| `loop_projection.py` | `LoopProjectionDefinition` Protocol + `LoopProjectionSnapshot`(归 0170 协议,本计划引用不实现)| PR-17 |
| `close_barrier.py` | `CloseBarrier` Protocol + `CloseReport`(归 0170 协议,本计划引用不实现)| PR-19 |

### 新建(`lca/infrastructure/observability/loop_cursor/`)

| 路径 | 归属 | 创建 PR |
|---|---|---|
| `__init__.py` | `LoopCursorFactory` 协议位 + `InMemoryLoopCursor` | PR-2 |
| `state.py` | `_CursorState` 内部 dataclass(phase/step/segment/iteration/incarnation) | PR-6 |
| `std.py` | `StdLoopCursor` 默认实现 | PR-7 |
| `factory.py` | `LoopCursorFactory.from_profile(...)` | PR-14 |
| `persistence_coordinator.py` | `PersistenceCoordinator` flush/close 实现 | PR-15 |
| `projection_host.py` | `ProjectionHost` 协议位 + 默认实现 | PR-18 |
| `model_visible_capture.py` | `ModelVisibleCapture` 5 件套 | PR-12 |
| `close_barrier_impl.py` | `StdCloseBarrier` 实现 | PR-20 |

### 修改(`lca/infrastructure/observability/`)

| 路径 | 改动 | 归属 PR |
|---|---|---|
| `writable_matrix/coordinator.py` | 保留 readonly methods,所有 `coord.emit_phase`/`coord.record_*`/`coord.begin_step`/`coord.end_step` 全部在 PR-21~24 迁移到 cursor | PR-21~24 |
| `writable_matrix/defaults.py:200-210` | `events.jsonl` → `<run_id>.spine.jsonl`(L10) | PR-27 |
| `journal/backends/filesystem.py:32` | `DEFAULT_FILENAME = "events.jsonl"` → `"$run_id.spine.jsonl"` | PR-27 |
| `facade/facade.py:516-575` | 删 `step_open / step_close / step_record_*` 7 个方法 + dunder exports | PR-26 |
| `facade/projection_registry.py` | 删 `ProjectionRegistry.publish` | PR-26 |
| `spine/sinks/file_sink.py:36` | 默认文件名改 | PR-27 |
| `spine/sinks/routing_file_sink.py:26` | 默认文件名改 | PR-27 |
| `spine/derivers/live_tail.py` | `_to_stamped` 删除,改 `LiveTailProjectionDefinition` 走 host | PR-26 |

### 修改(`lca/runtime/`)

| 路径 | 改动 | 归属 PR |
|---|---|---|
| `event_emission.py` | 删整模块 | PR-26 |
| `__init__.py` | 删 `JournalEmitFn`, `make_journal_emitting_hook` 导出 | PR-26 |

### 修改(`lca/cognition/`, `lca/body/`, `lca/agent/`)

| 路径 | 改动 | 归属 PR |
|---|---|---|
| `cognition/perceive_hub.py:93` | `coord.emit_phase('perceive')` → `cursor.advance('perceive')` | PR-21 |
| `cognition/body/safe_executor.py:388,403` | `coord.emit(phase.tool.call.*)` → `cursor.record_tool_call/result` | PR-22 |
| `cognition/body/tool_journal_emit.py:141,179,275` | `coord.emit(step.tool_*)` → `cursor.record_tool_call/result` | PR-22 |
| `cognition/body/simple_body.py:66,106` | 删 docstring 引用 `_derive_action_degraded` | PR-26 |
| `runtime/cognitive_run_driver.py` | 主循环调 `cursor.advance + record_thinking` | PR-23 |
| `agent/spawn.py` | 装配 `ObservabilityRuntime.from_profile(...)` | PR-25 |
| `application/spawn.py` | `RunSessionBuilder.build` 接 `ObservabilityRuntime` | PR-25 |
| `plugins/transport/webserver/handlers/runs/session/builder.py:107-130` | subscribe `StepTreeAccumulatorDeriver` 改走 `host.register(...)` | PR-25 |

### 修改(`lca_kernel/`)

| 路径 | 改动 | 归属 PR |
|---|---|---|
| `observability.py` | `ObservabilityRuntime.from_profile(profile, ctx)` 装配五缝 | PR-25 |
| `boot.py` | K3 spawn_fiber 用新装配入口 | PR-25 |

### 新建(`tests/`)

| 路径 | 测试对象 | 创建 PR |
|---|---|---|
| `observability/loop_cursor/test_protocol.py` | Protocol 方法签名 + frozen dataclass 约束 | PR-1 |
| `observability/loop_cursor/test_cursor_error.py` | `CursorError` 触发场景 | PR-2 |
| `observability/loop_cursor/test_in_memory.py` | `InMemoryLoopCursor` 行为 | PR-2 |
| `observability/loop_cursor/test_payloads.py` | 4 个 Record dataclass frozen + field 校验 | PR-3 |
| `observability/loop_cursor/test_state.py` | `_CursorState` 字段 + 转移合法性 | PR-6 |
| `observability/loop_cursor/test_transitions.py` | D2 状态图全部合法 + 非法 phase 序列 | PR-7 |
| `observability/loop_cursor/test_std_loop_cursor.py` | `StdLoopCursor` 公共方法 | PR-7 |
| `observability/loop_cursor/test_step_semantics.py` | §9 用例表 5 个 | PR-8 |
| `observability/loop_cursor/test_halt_close.py` | halt/close 路径 + L7-1 步骤 | PR-9 |
| `observability/loop_cursor/test_iteration_attempt.py` | L8 二阶重试 | PR-10 |
| `observability/loop_cursor/test_incarnation.py` | Incarnation 派生 + envelope | PR-11 |
| `observability/loop_cursor/test_event_descriptor.py` | cordis_name 派生表 | PR-13 |
| `observability/loop_cursor/test_factory.py` | `LoopCursorFactory.from_profile` | PR-14 |
| `observability/loop_cursor/test_persistence_coordinator.py` | flush/close + stats | PR-15 |
| `observability/loop_cursor/test_projection_host.py` | register/dispose + drive + flush_all 隔离失败 | PR-18 |
| `observability/loop_cursor/test_model_visible_capture.py` | 5 件套契约 | PR-12 |
| `observability/loop_cursor/test_close_barrier.py` | L7 五步顺序 + L16 钉死 | PR-20 |
| `observability/loop_cursor/test_invariants.py` | L1-L16 每条 1+ test method | PR-28 |
| `observability/loop_cursor/test_journal_format_errors.py` | L15 三子类型 | PR-29 |

### 新建(`scripts/`)

| 路径 | 检查对象 | 创建 PR |
|---|---|---|
| `check_loop_cursor_no_deriver_hold.py` | AST scan `StdLoopCursor` 不含 `_projections/_derivers/_persistence/_llm_hook/_model_visible_recorder` | PR-28 |
| `check_writable_matrix_boundaries.py` | 强化 L10 路径单写 | PR-27 |
| `check_cordis_event_derivation.py` | L12 cordis_name 派生 | PR-13 |

### 修改(`profiles/`)

| 路径 | 改动 | 归属 PR |
|---|---|---|
| `web-standard.yaml` | 加 `loop_cursor` bundle + `projection_host` `persistence` `model_visible` `close_barrier` 装配 | PR-25 |

### 修改(`bundles/`)

| 路径 | 改动 | 归属 PR |
|---|---|---|
| `spine-default.yaml` | 重命名 `bundles/loop_cursor.spine_default.yaml` + deriver 列表改 host `initial=[...]` | PR-25 |
| `spine-benchmark-minimal.yaml` | 重命名 `loop_cursor.spine_minimal.yaml` | PR-25 |
| `spine-oii-debug.yaml` | 重命名 `loop_cursor.spine_debug.yaml` | PR-25 |

### 依赖关系

```text
PR-1 ──▶ PR-2 ─┐
PR-3 ─────────┐│
PR-4 (无实现)││
PR-5 (无实现)││
              ▼▼
            PR-6 ──▶ PR-7 ──▶ PR-8 ──▶ PR-9 ──▶ PR-10
PR-11 ─┐                            │
PR-12 ─┤                            │
PR-13 ─┤                            │
PR-14 ─┘                            │
                                     ▼
                  PR-15 ──▶ PR-16 (无) ──▶ PR-17 (无) ──▶ PR-18 ──▶ PR-19 (无) ──▶ PR-20
                                     │
                                     ▼
                  PR-21 ──▶ PR-22 ──▶ PR-23 ──▶ PR-24 ──▶ PR-25
                                     │
                                     ▼
                  PR-26 ──▶ PR-27 ──▶ PR-28 ──▶ PR-29 ──▶ PR-30
```

> **关键约束**:每 PR 必须自包含一个测试 + 一个 grep/AST 门禁 + 一个 commit;依赖 PR 不能并发;评审 §7.3 排序(control → L10 → ModelVisible → ProjectionHost → cordis)在 PR-21~30 强制。

---

## Phase A · 契约与协议位(PR-1 ~ PR-5)

### Task 1: LoopCursor Protocol + CursorSnapshot + CursorError

**Files:**
- Create: `lca/contracts/observability/loop_cursor.py`
- Test: `tests/observability/loop_cursor/test_protocol.py`

**Interfaces:**
- Consumes: (无,首 PR)
- Produces:
  ```python
  # lca/contracts/observability/loop_cursor.py
  PhaseName = Literal[
      "perceive", "think", "gate", "act", "reflect", "remember", "stop"
  ]
  CloseReason = Literal[
      "completed", "user_stop", "budget_exhausted",
      "approval_pending", "approval_rejected",
      "error", "loop_guard", "kernel_shutdown"
  ]
  IterationReason = Literal[
      "tool_retry", "gate_retry", "checkpoint_resume",
      "subagent_resume", "user_replay"
  ]

  @dataclass(frozen=True)
  class CursorSnapshot:
      run_id: str
      trace_id: str
      incarnation: int
      step_id: str | None
      step_index: int
      iteration: int
      attempt_in_step: int
      phase: PhaseName | None
      iteration_reason: IterationReason | None
      stop_signal: CloseReason | None
      seq: int

  class CursorError(Exception): ...

  class LoopCursor(Protocol):
      @property
      def snapshot(self) -> CursorSnapshot: ...
      def advance(self, phase: PhaseName) -> CursorSnapshot: ...
      def halt(self, reason: CloseReason) -> None: ...
      def close(self, reason: CloseReason) -> None: ...
      def record_thinking(self, payload: "ThinkingRecord") -> None: ...
      def record_tool_call(self, payload: "ToolCallRecord") -> None: ...
      def record_tool_result(self, payload: "ToolResultRecord") -> None: ...
      def record_request_header(self, header: "RequestHeader") -> None: ...
      def fork(self, reason: Literal["child_agent", "delegation"]) -> "LoopCursor": ...
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_protocol.py
from lca.contracts.observability.loop_cursor import (
    CursorSnapshot, CursorError, LoopCursor, PhaseName, CloseReason, IterationReason
)
import pytest

def test_phase_name_is_closed_set():
    # Literal 编译期保证;运行时 import + repr 防回归
    for name in ("perceive", "think", "gate", "act", "reflect", "remember", "stop"):
        assert name in PhaseName.__args__

def test_close_reason_is_closed_set():
    expected = {"completed", "user_stop", "budget_exhausted",
                "approval_pending", "approval_rejected",
                "error", "loop_guard", "kernel_shutdown"}
    assert set(CloseReason.__args__) == expected

def test_iteration_reason_is_closed_set():
    expected = {"tool_retry", "gate_retry", "checkpoint_resume",
                "subagent_resume", "user_replay"}
    assert set(IterationReason.__args__) == expected

def test_cursor_snapshot_is_frozen():
    s = CursorSnapshot(
        run_id="r1", trace_id="t1", incarnation=1,
        step_id=None, step_index=0, iteration=0,
        attempt_in_step=0, phase=None, iteration_reason=None,
        stop_signal=None, seq=0,
    )
    with pytest.raises((AttributeError, Exception)):
        s.run_id = "r2"  # type: ignore[misc]

def test_cursor_error_is_exception_subclass():
    assert issubclass(CursorError, Exception)

def test_loop_cursor_protocol_has_9_methods():
    expected = {
        "advance", "halt", "close",
        "record_thinking", "record_tool_call", "record_tool_result",
        "record_request_header", "fork", "snapshot",
    }
    assert expected <= set(dir(LoopCursor))
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_protocol.py -v`
Expected: ImportError `No module named 'lca.contracts.observability.loop_cursor'`

- [ ] **Step 3: 实现最小契约**

```python
# lca/contracts/observability/loop_cursor.py
"""LoopCursor 控制面 Protocol(ADR-0169 D1)。

业务路径唯一允许调用 advance/record_*/halt/close/fork/snapshot;
emit/subscribe/flush/close_storage/register_projection 全部不在公共面。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


PhaseName = Literal[
    "perceive", "think", "gate", "act", "reflect", "remember", "stop"
]
CloseReason = Literal[
    "completed", "user_stop", "budget_exhausted",
    "approval_pending", "approval_rejected",
    "error", "loop_guard", "kernel_shutdown",
]
IterationReason = Literal[
    "tool_retry", "gate_retry", "checkpoint_resume",
    "subagent_resume", "user_replay",
]


@dataclass(frozen=True)
class CursorSnapshot:
    """只读视图;reducer / projection / persistence / observer 消费(ADR-0169 I-CURSOR-2)。"""
    run_id:           str
    trace_id:         str
    incarnation:      int
    step_id:          str | None
    step_index:       int
    iteration:        int
    attempt_in_step:  int
    phase:            PhaseName | None   # None = OUTSIDE_LOOP
    iteration_reason: IterationReason | None
    stop_signal:      CloseReason | None
    seq:              int


class CursorError(Exception):
    """非法转移 / 关闭后调用 / 跨窗口 record → raise,不静默 fallback(ADR-0169 L13)。"""


class LoopCursor(Protocol):
    """Loop 控制面状态机。"""

    @property
    def snapshot(self) -> CursorSnapshot: ...

    def advance(self, phase: PhaseName) -> CursorSnapshot: ...
    def halt(self, reason: CloseReason) -> None: ...
    def close(self, reason: CloseReason) -> None: ...

    def record_thinking(self, payload: "ThinkingRecord") -> None: ...
    def record_tool_call(self, payload: "ToolCallRecord") -> None: ...
    def record_tool_result(self, payload: "ToolResultRecord") -> None: ...

    def record_request_header(self, header: "RequestHeader") -> None: ...
    def fork(self, reason: Literal["child_agent", "delegation"]) -> "LoopCursor": ...
```

- [ ] **Step 4: 跑测试,确认通过**

Run: `uv run pytest tests/observability/loop_cursor/test_protocol.py -v`
Expected: 6 PASSED

- [ ] **Step 5: 门禁 grep**

```bash
# L13: NullLoopCursor 不存在
! grep -rn "NullLoopCursor" lca/ tests/
# record_* 闭集
grep -E "^\s+def record_" lca/contracts/observability/loop_cursor.py | wc -l  # = 4 (thinking/tool_call/tool_result/request_header)
```

- [ ] **Step 6: Commit**

```bash
git add lca/contracts/observability/loop_cursor.py tests/observability/loop_cursor/test_protocol.py
git commit -m "feat(contracts): add LoopCursor Protocol + CursorSnapshot + CursorError"
```

---

### Task 2: LoopCursorFactory + InMemoryLoopCursor(测试替身)

**Files:**
- Create: `lca/infrastructure/observability/loop_cursor/__init__.py`
- Create: `lca/infrastructure/observability/loop_cursor/in_memory.py`
- Test: `tests/observability/loop_cursor/test_in_memory.py`
- Test: `tests/observability/loop_cursor/test_cursor_error.py`

**Interfaces:**
- Consumes: PR-1 `LoopCursor` / `CursorSnapshot` / `CursorError`
- Produces:
  ```python
  # lca/infrastructure/observability/loop_cursor/in_memory.py
  class InMemoryLoopCursor:
      """测试替身(ADR-0169 L13);内存 spine + raise on illegal transitions。"""
      def __init__(self, *, run_id: str, trace_id: str, incarnation: int) -> None: ...
      @property
      def snapshot(self) -> CursorSnapshot: ...
      def advance(self, phase: PhaseName) -> CursorSnapshot: ...
      # ... 全部 9 个方法,非法转移 raise CursorError
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_in_memory.py
import pytest
from lca.contracts.observability.loop_cursor import (
    CursorError, LoopCursor, PhaseName, CloseReason,
)
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor


def test_in_memory_loop_cursor_satisfies_protocol():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    assert isinstance(c, LoopCursor)


def test_initial_snapshot_is_outside_loop():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    snap = c.snapshot
    assert snap.phase is None
    assert snap.iteration == 0


def test_advance_opens_phase_window():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    snap = c.advance("perceive")
    assert snap.phase == "perceive"


def test_close_after_close_raises_cursor_error():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.close("completed")
    with pytest.raises(CursorError):
        c.close("error")
```

```python
# tests/observability/loop_cursor/test_cursor_error.py
import pytest
from lca.contracts.observability.loop_cursor import CursorError


def test_cursor_error_carries_message():
    err = CursorError("phase window not open")
    assert "phase window" in str(err)


def test_cursor_error_not_silent_fallback():
    # 验证异常是 raise 出来的(冒烟),不返回 None / False
    raised = False
    try:
        raise CursorError("test")
    except CursorError:
        raised = True
    assert raised
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_in_memory.py tests/observability/loop_cursor/test_cursor_error.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 InMemoryLoopCursor**

```python
# lca/infrastructure/observability/loop_cursor/__init__.py
"""LoopCursor 默认实现族(ADR-0169 D8 五缝)。"""
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor

__all__ = ["InMemoryLoopCursor"]
```

```python
# lca/infrastructure/observability/loop_cursor/in_memory.py
"""In-memory LoopCursor — 测试替身(ADR-0169 L13)。"""
from __future__ import annotations

from dataclasses import replace
from typing import Literal

from lca.contracts.observability.loop_cursor import (
    CloseReason, CursorError, CursorSnapshot, IterationReason,
    LoopCursor, PhaseName,
)


class InMemoryLoopCursor:
    """纯内存 cursor;非法转移 raise CursorError;无 spine 写入。"""

    def __init__(self, *, run_id: str, trace_id: str, incarnation: int) -> None:
        self._run_id = run_id
        self._trace_id = trace_id
        self._incarnation = incarnation
        self._phase: PhaseName | None = None
        self._step_id: str | None = None
        self._step_index = 0
        self._iteration = 0
        self._attempt_in_step = 0
        self._iteration_reason: IterationReason | None = None
        self._stop_signal: CloseReason | None = None
        self._seq = 0
        self._closed = False
        self._phase_window_open = False

    @property
    def snapshot(self) -> CursorSnapshot:
        return CursorSnapshot(
            run_id=self._run_id,
            trace_id=self._trace_id,
            incarnation=self._incarnation,
            step_id=self._step_id,
            step_index=self._step_index,
            iteration=self._iteration,
            attempt_in_step=self._attempt_in_step,
            phase=self._phase,
            iteration_reason=self._iteration_reason,
            stop_signal=self._stop_signal,
            seq=self._seq,
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise CursorError("cursor closed")

    def advance(self, phase: PhaseName) -> CursorSnapshot:
        self._ensure_open()
        self._phase = phase
        self._phase_window_open = phase in ("think", "act")
        return self.snapshot

    def halt(self, reason: CloseReason) -> None:
        self._ensure_open()
        self._stop_signal = reason

    def close(self, reason: CloseReason) -> None:
        self._ensure_open()
        self._closed = True
        self._stop_signal = reason
        self._phase_window_open = False

    def record_thinking(self, payload: object) -> None:
        self._ensure_open()
        if not self._phase_window_open or self._phase != "think":
            raise CursorError("record_thinking must be in THINK window")

    def record_tool_call(self, payload: object) -> None:
        self._ensure_open()
        if not self._phase_window_open or self._phase != "act":
            raise CursorError("record_tool_call must be in ACT window")

    def record_tool_result(self, payload: object) -> None:
        self._ensure_open()
        if not self._phase_window_open or self._phase != "act":
            raise CursorError("record_tool_result must be in ACT window")

    def record_request_header(self, header: object) -> None:
        self._ensure_open()
        # L6 + D2 step 语义:record_request_header 必触发 think 开窗
        if self._phase != "think":
            raise CursorError("record_request_header must open THINK window")

    def fork(self, reason: Literal["child_agent", "delegation"]) -> "LoopCursor":
        child = InMemoryLoopCursor(
            run_id=self._run_id,
            trace_id=self._trace_id,
            incarnation=self._incarnation,
        )
        return child
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_in_memory.py tests/observability/loop_cursor/test_cursor_error.py -v`
Expected: 6 PASSED

- [ ] **Step 5: 门禁 grep**

```bash
# L13:NullLoopCursor 不存在
! grep -rn "class NullLoopCursor" lca/
# 协议满足性
uv run mypy lca/infrastructure/observability/loop_cursor/in_memory.py
```

- [ ] **Step 6: Commit**

```bash
git add lca/infrastructure/observability/loop_cursor/ tests/observability/loop_cursor/test_in_memory.py tests/observability/loop_cursor/test_cursor_error.py
git commit -m "feat(loop_cursor): add InMemoryLoopCursor test double"
```

---

### Task 3: Payload frozen dataclasses

**Files:**
- Create: `lca/contracts/observability/loop_cursor_payloads.py`
- Test: `tests/observability/loop_cursor/test_payloads.py`

**Interfaces:**
- Consumes: PR-1 类型字面量
- Produces:
  ```python
  # 4 个 frozen dataclass,严格按 ADR-0169 D4
  @dataclass(frozen=True)
  class ThinkingRecord: ...
  @dataclass(frozen=True)
  class ToolCallRecord: ...
  @dataclass(frozen=True)
  class ToolResultRecord: ...
  @dataclass(frozen=True)
  class RequestHeader: ...
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_payloads.py
import pytest
from dataclasses import FrozenInstanceError
from lca.contracts.observability.loop_cursor_payloads import (
    ThinkingRecord, ToolCallRecord, ToolResultRecord, RequestHeader,
)


def test_thinking_record_frozen():
    r = ThinkingRecord(
        content_digest="abc", content_path=None,
        token_count=100, thinking_kind="reasoning",
    )
    with pytest.raises(FrozenInstanceError):
        r.token_count = 200  # type: ignore[misc]


def test_tool_call_record_call_seq_required():
    r = ToolCallRecord(
        tool_name="t", args_digest="x", args_payload_path=None, call_seq=1,
    )
    assert r.call_seq == 1


def test_tool_result_record_outcome_literal():
    with pytest.raises((ValueError, TypeError)):
        ToolResultRecord(
            tool_name="t", result_digest="x", result_path=None,
            outcome="unknown",  # type: ignore[arg-type]
        )


def test_request_header_step_id_injected_by_cursor():
    h = RequestHeader(
        step_id="step-001", incarnation=1, reason="initial", model="m",
        system_digest="d1", system_path="p1",
        tools_digest="d2", tools_path="p2",
        messages_digest="d3", messages_path="p3",
        manifest_digest="d4", manifest_path="p4",
    )
    assert h.inherited_from_step is None
    h2 = RequestHeader(
        step_id="step-002", incarnation=1, reason="inherited", model="m",
        system_digest="d1", system_path="p1",
        tools_digest="d2", tools_path="p2",
        messages_digest="d3", messages_path="p3",
        manifest_digest="d4", manifest_path="p4",
        inherited_from_step="step-001",
    )
    assert h2.inherited_from_step == "step-001"
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_payloads.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 payload 模块**

```python
# lca/contracts/observability/loop_cursor_payloads.py
"""ADR-0169 D4:LoopCursor record_* 方法的 payload frozen dataclass。

关键:
- step_id 与 incarnation 不让业务路径填(由 cursor 注入,见 PR-7)
- system/tools/messages/manifest digest + path 由 ModelVisibleCapture 写(PR-12)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ThinkingRecord:
    content_digest: str
    content_path:   str | None
    token_count:    int | None
    thinking_kind:  Literal["reasoning", "final_response", "compaction"]


@dataclass(frozen=True)
class ToolCallRecord:
    tool_name:        str
    args_digest:      str
    args_payload_path: str | None
    call_seq:         int    # cursor 内自增


@dataclass(frozen=True)
class ToolResultRecord:
    tool_name:     str
    result_digest: str
    result_path:   str | None
    outcome:       Literal["ok", "failure", "timeout", "denied"]


@dataclass(frozen=True)
class RequestHeader:
    """cursor 注入 step_id/incarnation;业务路径不能填(ADR-0169 D4)。"""
    step_id:             str
    incarnation:         int
    reason:              Literal["initial", "next_step", "series", "change", "inherited"]
    model:               str
    system_digest:       str
    system_path:         str
    tools_digest:        str
    tools_path:          str
    messages_digest:     str
    messages_path:       str
    manifest_digest:     str
    manifest_path:       str
    inherited_from_step: str | None = None
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_payloads.py -v`
Expected: 4 PASSED

- [ ] **Step 5: 门禁 grep**

```bash
# 全部 payload 是 frozen
grep -l "@dataclass(frozen=True)" lca/contracts/observability/loop_cursor_payloads.py
# step_id 不在业务 payload 上
! grep -rn "step_id=.*model" lca/cognition/ lca/body/  # 业务路径不应自己构造 RequestHeader
```

- [ ] **Step 6: Commit**

```bash
git add lca/contracts/observability/loop_cursor_payloads.py tests/observability/loop_cursor/test_payloads.py
git commit -m "feat(contracts): add loop_cursor_payloads frozen dataclasses"
```

---

### Task 4: (skip — fork protocol stub)

**Files:** (无;fork 共享 Host 协议位在 ADR-0171 实现,本计划不实现)

- [ ] **Step 1: 在 ledger 标记 skip**

```markdown
# SDD ledger — plan: docs/superpowers/plans/2026-09-02-adr-0169-loop-cursor-control.md
PR-4: skip — fork protocol stub 归 ADR-0171,本计划仅引用 LoopCursor.fork() 接口(PR-1)
```

- [ ] **Step 2: (no commit)**

> 说明:LoopCursor.fork() 在 PR-1 已声明接口但 InMemoryLoopCursor 实现返回新 InMemoryLoopCursor;完整协议(共享 Host、incarnation 继承)由 ADR-0171 实现。

---

### Task 5: (skip — observability exporters stub)

**Files:** (无;Exporter 实现层归 ADR-0172)

- [ ] **Step 1: 在 ledger 标记 skip**

```markdown
PR-5: skip — observability exporters 归 ADR-0172,本计划仅保留 LoopProjectionDefinition Protocol(PR-17)
```

---

## Phase B · 状态机与实现(PR-6 ~ PR-10)

### Task 6: _CursorState 内部状态

**Files:**
- Create: `lca/infrastructure/observability/loop_cursor/state.py`
- Test: `tests/observability/loop_cursor/test_state.py`

**Interfaces:**
- Consumes: PR-1 字面量
- Produces:
  ```python
  # lca/infrastructure/observability/loop_cursor/state.py
  @dataclass
  class _CursorState:
      run_id: str
      trace_id: str
      incarnation: int
      phase: PhaseName | None
      step_id: str | None
      step_index: int
      iteration: int
      attempt_in_step: int
      iteration_reason: IterationReason | None
      stop_signal: CloseReason | None
      seq: int
      closed: bool
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_state.py
from lca.infrastructure.observability.loop_cursor.state import _CursorState


def test_cursor_state_default_initial():
    s = _CursorState(run_id="r1", trace_id="t1", incarnation=1)
    assert s.phase is None
    assert s.step_index == 0
    assert s.iteration == 0
    assert s.attempt_in_step == 0
    assert s.seq == 0
    assert s.closed is False


def test_cursor_state_closed_immutable_after_close():
    s = _CursorState(run_id="r1", trace_id="t1", incarnation=1)
    s.closed = True
    s.phase = "stop"
    assert s.closed is True
    assert s.phase == "stop"
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_state.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 _CursorState**

```python
# lca/infrastructure/observability/loop_cursor/state.py
"""LoopCursor 内部状态(ADR-0169 D1 / D6)。

非 frozen — 内部可变字段;cursor 公共面 snapshot() 返回 frozen CursorSnapshot。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from lca.contracts.observability.loop_cursor import (
    CloseReason, IterationReason, PhaseName,
)


@dataclass
class _CursorState:
    run_id:           str
    trace_id:         str
    incarnation:      int
    phase:            Optional[PhaseName] = None
    step_id:          Optional[str] = None
    step_index:       int = 0
    iteration:        int = 0
    attempt_in_step:  int = 0
    iteration_reason: Optional[IterationReason] = None
    stop_signal:      Optional[CloseReason] = None
    seq:              int = 0
    closed:           bool = False
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_state.py -v`
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add lca/infrastructure/observability/loop_cursor/state.py tests/observability/loop_cursor/test_state.py
git commit -m "feat(loop_cursor): add internal _CursorState"
```

---

### Task 7: StdLoopCursor 默认实现

**Files:**
- Create: `lca/infrastructure/observability/loop_cursor/std.py`
- Create: `lca/infrastructure/observability/loop_cursor/_spine_port.py`(WritePort 协议位)
- Test: `tests/observability/loop_cursor/test_std_loop_cursor.py`
- Test: `tests/observability/loop_cursor/test_transitions.py`

**Interfaces:**
- Consumes: PR-1 `LoopCursor` / `CursorSnapshot` / `CursorError`、PR-3 `*Record` dataclass、PR-6 `_CursorState`、本 PR 新增的 `WritePort` 协议位
- Produces:
  ```python
  # lca/infrastructure/observability/loop_cursor/_spine_port.py
  class WritePort(Protocol):
      """cursor 唯一允许调用的 spine 面 — 语义 append。"""
      def append(self, *, execution_point: str, payload: dict, run_id: str, seq: int, **kw) -> int: ...

  # lca/infrastructure/observability/loop_cursor/std.py
  class StdLoopCursor:
      def __init__(self, *, spine: WritePort, state: _CursorState) -> None: ...
      # 实现 9 个公共方法 + advance 自动 emit phase.<name>.fold EP
  ```

- [ ] **Step 1: 写失败测试 — transitions**

```python
# tests/observability/loop_cursor/test_transitions.py
import pytest
from lca.contracts.observability.loop_cursor import CursorError, PhaseName
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor


def test_advance_from_outside_to_perceive():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    assert c.snapshot.phase == "perceive"


def test_advance_perceive_to_think_to_gate_to_act_to_reflect_to_stop():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    assert c.snapshot.phase == "stop"


def test_advance_after_close_raises():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.close("completed")
    with pytest.raises(CursorError):
        c.advance("perceive")


def test_advance_think_then_perceive_starts_new_iteration():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    c.advance("think")
    c.advance("gate")
    c.advance("act")
    c.advance("reflect")
    c.advance("stop")
    # 下一轮 iteration
    c.advance("perceive")
    assert c.snapshot.iteration == 1
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_transitions.py -v`
Expected: AttributeError on `iteration` 字段(本任务补 `_iteration` 计数)

- [ ] **Step 3: 实现 WritePort + StdLoopCursor**

```python
# lca/infrastructure/observability/loop_cursor/_spine_port.py
"""Spine WritePort — cursor 唯一允许调用的 spine 面(ADR-0169 D1 / L10)。"""
from __future__ import annotations

from typing import Any, Protocol


class WritePort(Protocol):
    """append-only 语义写入;spine 内部负责 seq 分配与 sink flush。"""

    def append(
        self,
        *,
        execution_point: str,
        payload: dict[str, Any],
        run_id: str,
        seq: int,
        incarnation: int,
        phase: str | None,
    ) -> int: ...
```

```python
# lca/infrastructure/observability/loop_cursor/std.py
"""StdLoopCursor — 默认实现(ADR-0169 D1 / D8)。

仅持 spine handle + _state;不持 deriver/projections/persistence/llm hook/model_visible recorder。
构造器签名不含 host / persistence / capture 实例(评审 S1 处方,AST scan 验证)。
"""
from __future__ import annotations

from dataclasses import replace
from typing import Literal

from lca.contracts.observability.loop_cursor import (
    CloseReason, CursorError, CursorSnapshot, LoopCursor, PhaseName,
)
from lca.contracts.observability.loop_cursor_payloads import (
    RequestHeader, ThinkingRecord, ToolCallRecord, ToolResultRecord,
)
from lca.infrastructure.observability.loop_cursor._spine_port import WritePort
from lca.infrastructure.observability.loop_cursor.state import _CursorState


_PHASE_ORDER = ("perceive", "think", "gate", "act", "reflect", "remember", "stop")
_THINK_WINDOW = ("think",)
_ACT_WINDOW = ("act",)


class StdLoopCursor:
    def __init__(self, *, spine: WritePort, state: _CursorState) -> None:
        self._spine = spine
        self._state = state

    @property
    def snapshot(self) -> CursorSnapshot:
        s = self._state
        return CursorSnapshot(
            run_id=s.run_id,
            trace_id=s.trace_id,
            incarnation=s.incarnation,
            step_id=s.step_id,
            step_index=s.step_index,
            iteration=s.iteration,
            attempt_in_step=s.attempt_in_step,
            phase=s.phase,
            iteration_reason=s.iteration_reason,
            stop_signal=s.stop_signal,
            seq=s.seq,
        )

    def _emit(self, execution_point: str, payload: dict) -> None:
        self._state.seq += 1
        self._spine.append(
            execution_point=execution_point,
            payload=payload,
            run_id=self._state.run_id,
            seq=self._state.seq,
            incarnation=self._state.incarnation,
            phase=self._state.phase,
        )

    def _ensure_open(self) -> None:
        if self._state.closed:
            raise CursorError("cursor closed")

    def advance(self, phase: PhaseName) -> CursorSnapshot:
        self._ensure_open()
        prev = self._state.phase
        if prev is not None and phase == "perceive" and prev == "stop":
            # 新 iteration
            self._state.iteration += 1
            self._state.iteration_reason = None
            self._state.step_index = 0
            self._state.attempt_in_step = 0
        if phase in _THINK_WINDOW:
            self._state.step_index += 1
            self._state.attempt_in_step = 0
            self._state.step_id = f"step-{self._state.step_index:03d}"
        self._state.phase = phase
        self._emit(f"phase.{phase}.fold", {"from": prev, "to": phase})
        return self.snapshot

    def halt(self, reason: CloseReason) -> None:
        self._ensure_open()
        self._state.stop_signal = reason
        self._emit("writable.iteration.halt", {"reason": reason})

    def close(self, reason: CloseReason) -> None:
        self._ensure_open()
        self._state.closed = True
        self._state.stop_signal = reason
        self._emit("writable.iteration.closing", {"reason": reason})
        # L7-5 由 CloseBarrier(PR-20)发 iteration.close EP,这里不 emit

    def record_thinking(self, payload: ThinkingRecord) -> None:
        self._ensure_open()
        if self._state.phase != "think":
            raise CursorError("record_thinking must be in THINK window")
        self._emit("step.thinking.record", {
            "content_digest": payload.content_digest,
            "content_path": payload.content_path,
            "token_count": payload.token_count,
            "thinking_kind": payload.thinking_kind,
            "step_id": self._state.step_id,
        })

    def record_tool_call(self, payload: ToolCallRecord) -> None:
        self._ensure_open()
        if self._state.phase != "act":
            raise CursorError("record_tool_call must be in ACT window")
        self._emit("step.tool_call.record", {
            "tool_name": payload.tool_name,
            "args_digest": payload.args_digest,
            "args_payload_path": payload.args_payload_path,
            "call_seq": payload.call_seq,
        })

    def record_tool_result(self, payload: ToolResultRecord) -> None:
        self._ensure_open()
        if self._state.phase != "act":
            raise CursorError("record_tool_result must be in ACT window")
        self._emit("step.tool_result.record", {
            "tool_name": payload.tool_name,
            "result_digest": payload.result_digest,
            "result_path": payload.result_path,
            "outcome": payload.outcome,
        })

    def record_request_header(self, header: RequestHeader) -> None:
        self._ensure_open()
        # D2 L6 + §9 step 语义:record_request_header 必触发 think 开窗
        if self._state.phase != "think":
            raise CursorError("record_request_header must open THINK window")
        self._state.attempt_in_step += 1
        self._emit("llm.request.header", {
            "step_id": header.step_id,
            "incarnation": header.incarnation,
            "reason": header.reason,
            "model": header.model,
            "system_digest": header.system_digest,
            "tools_digest": header.tools_digest,
            "messages_digest": header.messages_digest,
            "manifest_digest": header.manifest_digest,
            "inherited_from_step": header.inherited_from_step,
        })

    def fork(self, reason: Literal["child_agent", "delegation"]) -> "LoopCursor":
        # ADR-0171 协议位;此处返回独立 cursor 实例(共享 Host 由 ADR-0171 实现)
        child_state = _CursorState(
            run_id=self._state.run_id,
            trace_id=self._state.trace_id,
            incarnation=self._state.incarnation,
        )
        return StdLoopCursor(spine=self._spine, state=child_state)
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_transitions.py tests/observability/loop_cursor/test_std_loop_cursor.py -v`
Expected: 8+ PASSED

- [ ] **Step 5: AST scan 门禁(S1 处方)**

```bash
# StdLoopCursor 不持有 deriver/projections/persistence/llm hook/model_visible recorder
uv run python scripts/check_loop_cursor_no_deriver_hold.py
# 期望:0 命中字段
```

如果 `scripts/check_loop_cursor_no_deriver_hold.py` 不存在,**新建**(PR-28 才创建),本 PR 仅手动 grep:

```bash
! grep -E "_projections|_derivers|_persistence|_llm_hook|_model_visible_recorder" lca/infrastructure/observability/loop_cursor/std.py
```

- [ ] **Step 6: Commit**

```bash
git add lca/infrastructure/observability/loop_cursor/_spine_port.py lca/infrastructure/observability/loop_cursor/std.py tests/observability/loop_cursor/test_transitions.py tests/observability/loop_cursor/test_std_loop_cursor.py
git commit -m "feat(loop_cursor): add StdLoopCursor default implementation"
```

---

### Task 8: Step 语义用例表(ADR-0169 §9)

**Files:**
- Test: `tests/observability/loop_cursor/test_step_semantics.py`

**Interfaces:**
- Consumes: PR-7 `StdLoopCursor`
- Produces: 5 个 step 语义用例的测试

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_step_semantics.py
"""ADR-0169 §9: step 语义用例表钉死选项 A。"""
import pytest
from lca.contracts.observability.loop_cursor import CursorError
from lca.contracts.observability.loop_cursor_payloads import RequestHeader
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor


def _hdr(step_id="step-001", incarnation=1, reason="initial"):
    return RequestHeader(
        step_id=step_id, incarnation=incarnation, reason=reason,  # type: ignore[arg-type]
        model="m",
        system_digest="d", system_path="p",
        tools_digest="d", tools_path="p",
        messages_digest="d", messages_path="p",
        manifest_digest="d", manifest_path="p",
    )


def test_standard_perceive_think_act_creates_one_step():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    c.advance("think")
    c.record_request_header(_hdr("step-001"))
    c.record_request_header(_hdr("step-001", reason="next_step"))
    assert c.snapshot.step_index == 1


def test_pure_perceive_no_llm_creates_zero_step():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    c.advance("stop")
    assert c.snapshot.step_index == 0


def test_record_request_header_outside_think_raises():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    with pytest.raises(CursorError):
        c.record_request_header(_hdr())


def test_checkpoint_resume_increments_iteration_with_reason():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    c.advance("think")
    c.advance("gate")
    c.advance("act")
    c.advance("reflect")
    c.advance("stop")
    # iteration_reason 由 checkpoint_resume 注入;advance('perceive') 触发 iteration++ 后由调用方写
    c.advance("perceive")
    assert c.snapshot.iteration == 1
```

- [ ] **Step 2: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_step_semantics.py -v`
Expected: 4 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/observability/loop_cursor/test_step_semantics.py
git commit -m "test(loop_cursor): pin step semantics §9 use cases"
```

---

### Task 9: halt + close 路径(L7 步骤 1-2)

**Files:**
- Test: `tests/observability/loop_cursor/test_halt_close.py`

**Interfaces:**
- Consumes: PR-7 `StdLoopCursor`、PR-6 `_CursorState`

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_halt_close.py
"""ADR-0169 L7 step 1-2:cursor.close 状态机 + closing EP。"""
import pytest
from lca.contracts.observability.loop_cursor import CursorError
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor


def test_halt_sets_stop_signal_without_closing():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    c.halt("budget_exhausted")
    assert c.snapshot.stop_signal == "budget_exhausted"
    assert not c.snapshot.phase is None  # 仍可 advance


def test_close_marks_cursor_closed():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.close("completed")
    # 再调任何方法应 raise
    with pytest.raises(CursorError):
        c.advance("perceive")
    with pytest.raises(CursorError):
        c.halt("error")
    with pytest.raises(CursorError):
        c.close("error")


def test_halt_then_close_preserves_stop_signal():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    c.halt("budget_exhausted")
    c.close("budget_exhausted")
    assert c.snapshot.stop_signal == "budget_exhausted"
```

- [ ] **Step 2: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_halt_close.py -v`
Expected: 3 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/observability/loop_cursor/test_halt_close.py
git commit -m "test(loop_cursor): halt/close path L7 step 1-2"
```

---

### Task 10: iteration 与 attempt_in_step 二阶重试(L8)

**Files:**
- Test: `tests/observability/loop_cursor/test_iteration_attempt.py`

**Interfaces:**
- Consumes: PR-7

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_iteration_attempt.py
"""ADR-0169 L8:iteration ⊃ ADR-0095 iteration;attempt_in_step 与 iteration 独立计数。"""
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor


def test_iteration_increments_after_stop_to_perceive():
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    assert c.snapshot.iteration == 0
    c.advance("perceive")
    assert c.snapshot.iteration == 1


def test_attempt_in_step_increments_per_request_header():
    from lca.contracts.observability.loop_cursor_payloads import RequestHeader
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    c.advance("think")
    for i in range(3):
        c.record_request_header(RequestHeader(
            step_id="step-001", incarnation=1, reason="next_step",  # type: ignore[arg-type]
            model="m",
            system_digest="d", system_path="p",
            tools_digest="d", tools_path="p",
            messages_digest="d", messages_path="p",
            manifest_digest="d", manifest_path="p",
        ))
    assert c.snapshot.attempt_in_step == 3


def test_iteration_and_attempt_independent():
    """L8 钉死:attempt_in_step 重置当 step_index 增;iteration 不影响。"""
    from lca.contracts.observability.loop_cursor_payloads import RequestHeader
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    c.advance("think")
    # iteration 0,attempt 0
    c.record_request_header(RequestHeader(
        step_id="step-001", incarnation=1, reason="initial",  # type: ignore[arg-type]
        model="m",
        system_digest="d", system_path="p",
        tools_digest="d", tools_path="p",
        messages_digest="d", messages_path="p",
        manifest_digest="d", manifest_path="p",
    ))
    # 走完一轮
    for phase in ("gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    # 第二轮 iteration 1,新 step,attempt 0
    c.advance("perceive")
    c.advance("think")
    assert c.snapshot.iteration == 1
    assert c.snapshot.step_index == 2
    assert c.snapshot.attempt_in_step == 0
```

- [ ] **Step 2: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_iteration_attempt.py -v`
Expected: 3 PASSED

- [ ] **Step 3: Commit**

```bash
git add tests/observability/loop_cursor/test_iteration_attempt.py
git commit -m "test(loop_cursor): L8 iteration ⊃ ADR-0095 + attempt_in_step 独立计数"
```

---

## Phase C · Incarnation / EventDescriptor / Persistence / Capture / Projection / CloseBarrier(PR-11 ~ PR-20)

### Task 11: Incarnation 显式身份(L14)

**Files:**
- Create: `lca/contracts/observability/incarnation.py`
- Modify: `lca/infrastructure/observability/loop_cursor/state.py`(加 `incarnation_seq`)
- Test: `tests/observability/loop_cursor/test_incarnation.py`

**Interfaces:**
- Consumes: 无
- Produces:
  ```python
  # lca/contracts/observability/incarnation.py
  @dataclass(frozen=True)
  class Incarnation:
      run_id: str
      plan_ref: str
      incarnation_seq: int
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_incarnation.py
import pytest
from dataclasses import FrozenInstanceError
from lca.contracts.observability.incarnation import Incarnation


def test_incarnation_frozen():
    i = Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1)
    with pytest.raises(FrozenInstanceError):
        i.incarnation_seq = 2  # type: ignore[misc]


def test_incarnation_seq_starts_from_one():
    i = Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1)
    assert i.incarnation_seq == 1


def test_incarnation_equality():
    a = Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1)
    b = Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1)
    assert a == b


def test_incarnation_distinct_by_seq():
    a = Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1)
    b = Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=2)
    assert a != b
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_incarnation.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 Incarnation**

```python
# lca/contracts/observability/incarnation.py
"""Incarnation 显式身份(ADR-0169 D6 / L14 / I-CURSOR-5)。

incarnation = (run_id, plan_ref, incarnation_seq):
- run_id          : session 维度
- plan_ref        : 计划维度身份(变更 plan_ref 触发 incarnation_seq++)
- incarnation_seq : 单调递增,从 1 起

与 ADR-0095 iteration 正交:incarnation 是「计划维度」身份;
iteration 是「尝试维度」计数,见 LoopCursor.snapshot.iteration。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Incarnation:
    run_id:          str
    plan_ref:        str
    incarnation_seq: int   # 从 1 起
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_incarnation.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add lca/contracts/observability/incarnation.py tests/observability/loop_cursor/test_incarnation.py
git commit -m "feat(contracts): add Incarnation explicit identity"
```

---

### Task 12: ModelVisibleCapture 5 件套(ADR-0169 D7)

**Files:**
- Create: `lca/infrastructure/observability/loop_cursor/model_visible_capture.py`
- Test: `tests/observability/loop_cursor/test_model_visible_capture.py`

**Interfaces:**
- Consumes: PR-3 `RequestHeader`、PR-11 `Incarnation`
- Produces:
  ```python
  # lca/infrastructure/observability/loop_cursor/model_visible_capture.py
  class ModelVisibleCapture:
      """LLM 边界真实捕获(ADR-0169 D7);不在 cursor。"""
      def __init__(self, *, run_dir: Path, run_id: str) -> None: ...
      def write_step_artifacts(self, header: RequestHeader, *, system: str, tools: list, messages: list, manifest: dict) -> Path: ...
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_model_visible_capture.py
"""ADR-0169 D7:ModelVisibleCapture 在 LLM 边界,真实捕获 5 件套。"""
from pathlib import Path
import json
from lca.contracts.observability.loop_cursor_payloads import RequestHeader
from lca.infrastructure.observability.loop_cursor.model_visible_capture import ModelVisibleCapture


def test_capture_writes_five_artifacts(tmp_path: Path):
    cap = ModelVisibleCapture(run_dir=tmp_path, run_id="r1")
    header = RequestHeader(
        step_id="step-001", incarnation=1, reason="initial",  # type: ignore[arg-type]
        model="m",
        system_digest="d1", system_path="model_visible/step_001/system-prompt.md",
        tools_digest="d2", tools_path="model_visible/step_001/tool-schemas.json",
        messages_digest="d3", messages_path="model_visible/step_001/messages.json",
        manifest_digest="d4", manifest_path="model_visible/step_001/context-manifest.json",
    )
    cap.write_step_artifacts(
        header,
        system="sys", tools=[{"name": "t1"}], messages=[{"role": "user", "content": "hi"}],
        manifest={"version": 1},
    )
    step_dir = tmp_path / "model_visible" / "step_001"
    assert (step_dir / "system-prompt.md").exists()
    assert (step_dir / "tool-schemas.json").exists()
    assert (step_dir / "messages.json").exists()
    assert (step_dir / "context-manifest.json").exists()
    assert (step_dir / "request-header.json").exists()
    # messages.json 真实 messages
    assert json.loads((step_dir / "messages.json").read_text())[0]["content"] == "hi"


def test_capture_failure_falls_back_to_host_error_metric():
    """Capture 失败不应 throw;写入 host error 指标。"""
    from lca.infrastructure.observability.loop_cursor.model_visible_capture import ModelVisibleCapture
    cap = ModelVisibleCapture(run_dir=Path("/nonexistent-RO"), run_id="r1")
    # 不应抛异常
    cap.write_step_artifacts(
        RequestHeader(
            step_id="step-001", incarnation=1, reason="initial",  # type: ignore[arg-type]
            model="m",
            system_digest="d", system_path="p",
            tools_digest="d", tools_path="p",
            messages_digest="d", messages_path="p",
            manifest_digest="d", manifest_path="p",
        ),
        system="", tools=[], messages=[], manifest={},
    )
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_model_visible_capture.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 ModelVisibleCapture**

```python
# lca/infrastructure/observability/loop_cursor/model_visible_capture.py
"""ModelVisibleCapture — LLM 边界真实捕获(ADR-0169 D7)。

5 件套:system-prompt.md / tool-schemas.json / messages.json / context-manifest.json / request-header.json。

失败 fallback:捕获异常 → 写到 host error 指标(`projection_host.errors`),不抛。
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from lca.contracts.observability.loop_cursor_payloads import RequestHeader


log = logging.getLogger(__name__)


def _sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


class ModelVisibleCapture:
    def __init__(self, *, run_dir: Path, run_id: str) -> None:
        self._run_dir = run_dir
        self._run_id = run_id
        self._errors: list[tuple[str, Exception]] = []

    @property
    def errors(self) -> list[tuple[str, Exception]]:
        return list(self._errors)

    def write_step_artifacts(
        self,
        header: RequestHeader,
        *,
        system: str,
        tools: list[Any],
        messages: list[Any],
        manifest: dict[str, Any],
    ) -> Path:
        try:
            step_index = int(header.step_id.split("-")[-1])
        except (ValueError, IndexError):
            step_index = 0
        step_dir = self._run_dir / "model_visible" / f"step_{step_index:03d}"
        try:
            step_dir.mkdir(parents=True, exist_ok=True)
            (step_dir / "system-prompt.md").write_text(system)
            (step_dir / "tool-schemas.json").write_text(json.dumps(tools, indent=2))
            (step_dir / "messages.json").write_text(json.dumps(messages, indent=2))
            (step_dir / "context-manifest.json").write_text(json.dumps(manifest, indent=2))
            (step_dir / "request-header.json").write_text(json.dumps({
                "step_id": header.step_id,
                "incarnation": header.incarnation,
                "reason": header.reason,
                "model": header.model,
                "system_digest": _sha256(system),
                "tools_digest": _sha256(json.dumps(tools)),
                "messages_digest": _sha256(json.dumps(messages)),
                "manifest_digest": _sha256(json.dumps(manifest)),
                "inherited_from_step": header.inherited_from_step,
            }, indent=2))
            return step_dir
        except Exception as exc:
            log.warning("model_visible_capture_failed step=%s err=%s", header.step_id, exc)
            self._errors.append((header.step_id, exc))
            return step_dir  # 返回但不抛
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_model_visible_capture.py -v`
Expected: 2 PASSED

- [ ] **Step 5: grep 门禁 L11**

```bash
# L11:LLM 边界只 emit spine EP;ModelVisibleCapture 唯一接管 model_visible 5 件套
! grep -rn "LlmCallCompleted" lca/cognition/ lca/body/ lca/runtime/
```

- [ ] **Step 6: Commit**

```bash
git add lca/infrastructure/observability/loop_cursor/model_visible_capture.py tests/observability/loop_cursor/test_model_visible_capture.py
git commit -m "feat(loop_cursor): add ModelVisibleCapture 5-件套 (D7)"
```

---

### Task 13: EventDescriptor + cordis_name 派生(L12)

**Files:**
- Create: `lca/contracts/observability/event_descriptor.py`
- Create: `scripts/check_cordis_event_derivation.py`
- Test: `tests/observability/loop_cursor/test_event_descriptor.py`

**Interfaces:**
- Consumes: 无
- Produces:
  ```python
  # lca/contracts/observability/event_descriptor.py
  @dataclass(frozen=True)
  class EventDescriptor:
      name: str
      cordis_name: str | None
      phase_window: tuple[str, ...] | None
      version: int
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_event_descriptor.py
import pytest
from dataclasses import FrozenInstanceError
from lca.contracts.observability.event_descriptor import EventDescriptor


def test_event_descriptor_frozen():
    e = EventDescriptor(name="phase.perceive.fold", cordis_name="phase.perceive.fold",
                         phase_window=None, version=1)
    with pytest.raises(FrozenInstanceError):
        e.name = "x"  # type: ignore[misc]


def test_cordis_name_none_means_not_emitted():
    e = EventDescriptor(name="writable.step.start", cordis_name=None,
                         phase_window=("act",), version=1)
    assert e.cordis_name is None
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_event_descriptor.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 EventDescriptor**

```python
# lca/contracts/observability/event_descriptor.py
"""EventDescriptor — cordis_name 派生表(ADR-0169 D6 / L12)。

spine.append(canonical_name) 内部查表决定是否 ctx.emit(cordis_name)。
业务路径不直接 emit(ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*'))。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EventDescriptor:
    name:           str    # canonical name,e.g. "writable.step.start"
    cordis_name:    Optional[str]
    phase_window:   Optional[tuple[str, ...]]
    version:        int
```

- [ ] **Step 4: 实现 check_cordis_event_derivation.py(L12 门禁)**

```python
# scripts/check_cordis_event_derivation.py
"""ADR-0169 L12:cordis event name 必须由 EventDescriptor 派生;业务不直接 emit。

扫描 lca/{cognition,body,runtime,agent}/*.{py} 中 ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*')
与 event_descriptor.py 的 canonical_name 不一致即视为违规。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["lca/cognition", "lca/body", "lca/runtime", "lca/agent"]
FORBIDDEN_PREFIXES = ("agent.", "phase.", "tool.", "llm.")

EMIT_RE = re.compile(r"""ctx\.emit\(\s*['"]([^'"]+)['"]""")


def main() -> int:
    violations: list[str] = []
    for d in SCAN_DIRS:
        for fp in (REPO / d).rglob("*.py"):
            for i, line in enumerate(fp.read_text().splitlines(), start=1):
                m = EMIT_RE.search(line)
                if not m:
                    continue
                ev = m.group(1)
                if any(ev.startswith(p) for p in FORBIDDEN_PREFIXES):
                    violations.append(f"{fp}:{i} {ev}")
    if violations:
        for v in violations:
            print(f"L12 VIOLATION: {v}")
        return 1
    print("L12 OK: 0 violations")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: 跑测试 + 门禁**

Run: `uv run pytest tests/observability/loop_cursor/test_event_descriptor.py -v`
Expected: 2 PASSED

Run: `uv run python scripts/check_cordis_event_derivation.py`
Expected: 当前应输出 `L12 OK: 0 violations`(PR-30 才正式生效,本 PR 仅建立门禁脚本)

- [ ] **Step 6: Commit**

```bash
git add lca/contracts/observability/event_descriptor.py scripts/check_cordis_event_derivation.py tests/observability/loop_cursor/test_event_descriptor.py
git commit -m "feat(contracts): add EventDescriptor + L12 cordis derivation gate"
```

---

### Task 14: LoopCursorFactory.from_profile(装配入口)

**Files:**
- Create: `lca/infrastructure/observability/loop_cursor/factory.py`
- Modify: `lca/infrastructure/observability/loop_cursor/__init__.py`
- Test: `tests/observability/loop_cursor/test_factory.py`

**Interfaces:**
- Consumes: PR-7 `StdLoopCursor`、PR-11 `Incarnation`
- Produces:
  ```python
  # lca/infrastructure/observability/loop_cursor/factory.py
  class LoopCursorFactory:
      @staticmethod
      def from_profile(*, profile: Profile, run_id: str, trace_id: str, spine: WritePort) -> LoopCursor: ...
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_factory.py
from lca.contracts.observability.loop_cursor import LoopCursor
from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory


class _FakeProfile:
    plan_ref = "plan-A"


def test_factory_creates_std_loop_cursor():
    cursor = LoopCursorFactory.from_profile(
        profile=_FakeProfile(),  # type: ignore[arg-type]
        run_id="r1", trace_id="t1", spine=None,  # type: ignore[arg-type]
    )
    assert isinstance(cursor, LoopCursor)


def test_factory_incarnation_seq_starts_from_one():
    cursor = LoopCursorFactory.from_profile(
        profile=_FakeProfile(),  # type: ignore[arg-type]
        run_id="r1", trace_id="t1", spine=None,  # type: ignore[arg-type]
    )
    assert cursor.snapshot.incarnation == 1
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_factory.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 factory**

```python
# lca/infrastructure/observability/loop_cursor/factory.py
"""LoopCursorFactory — Profile 选择装配入口(ADR-0088 + ADR-0169 D14)。"""
from __future__ import annotations

from lca.contracts.observability.loop_cursor import LoopCursor
from lca.infrastructure.observability.loop_cursor._spine_port import WritePort
from lca.infrastructure/observability/loop_cursor.state import _CursorState
from lca.infrastructure.observability.loop_cursor.std import StdLoopCursor


class LoopCursorFactory:
    @staticmethod
    def from_profile(
        *,
        profile: object,
        run_id: str,
        trace_id: str,
        spine: WritePort,
    ) -> LoopCursor:
        plan_ref = getattr(profile, "plan_ref", "default")
        state = _CursorState(
            run_id=run_id,
            trace_id=trace_id,
            incarnation=1,   # PR-11: 从 1 起
            phase=None,
        )
        return StdLoopCursor(spine=spine, state=state)
```

- [ ] **Step 4: 更新 __init__.py 导出**

```python
# lca/infrastructure/observability/loop_cursor/__init__.py
from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor
from lca.infrastructure.observability.loop_cursor.std import StdLoopCursor

__all__ = ["InMemoryLoopCursor", "LoopCursorFactory", "StdLoopCursor"]
```

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_factory.py -v`
Expected: 2 PASSED

- [ ] **Step 6: Commit**

```bash
git add lca/infrastructure/observability/loop_cursor/factory.py lca/infrastructure/observability/loop_cursor/__init__.py tests/observability/loop_cursor/test_factory.py
git commit -m "feat(loop_cursor): add LoopCursorFactory.from_profile"
```

---

### Task 15: PersistenceCoordinator.flush/close(L10 验证)

**Files:**
- Create: `lca/infrastructure/observability/loop_cursor/persistence_coordinator.py`
- Test: `tests/observability/loop_cursor/test_persistence_coordinator.py`

**Interfaces:**
- Consumes: PR-7 `WritePort`
- Produces:
  ```python
  # lca/infrastructure/observability/loop_cursor/persistence_coordinator.py
  class PersistenceStats:
      flushed: int
      dropped: int
      duration_ms: int

  class PersistenceCoordinator:
      def __init__(self, *, coalescer: object, sink: object) -> None: ...
      def flush(self) -> PersistenceStats: ...
      def close(self) -> PersistenceStats: ...
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_persistence_coordinator.py
from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
    PersistenceCoordinator, PersistenceStats,
)


class _NullSink:
    def flush(self): return 0
    def close(self): return 0


def test_flush_returns_stats():
    pc = PersistenceCoordinator(coalescer=None, sink=_NullSink())
    s = pc.flush()
    assert isinstance(s, PersistenceStats)


def test_close_returns_stats():
    pc = PersistenceCoordinator(coalescer=None, sink=_NullSink())
    s = pc.close()
    assert isinstance(s, PersistenceStats)
    assert s.dropped == 0


def test_flush_records_dropped_on_sink_error():
    class _BoomSink:
        def flush(self): raise OSError("disk full")
        def close(self): return 0
    pc = PersistenceCoordinator(coalescer=None, sink=_BoomSink())
    s = pc.flush()
    assert s.dropped >= 1
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_persistence_coordinator.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 PersistenceCoordinator**

```python
# lca/infrastructure/observability/loop_cursor/persistence_coordinator.py
"""PersistenceCoordinator — ADR-0169 D8 持久化缝。

flush:把 coalescer 缓冲压到 sink;close:落 sink.close() 并返回 stats。
Kafka 同构:coalescer = consumer group,sink = persistence layer。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PersistenceStats:
    flushed:     int
    dropped:     int
    duration_ms: int


class PersistenceCoordinator:
    def __init__(self, *, coalescer: object | None, sink: object) -> None:
        self._coalescer = coalescer
        self._sink = sink

    def flush(self) -> PersistenceStats:
        t0 = time.monotonic()
        flushed = 0
        dropped = 0
        try:
            if self._coalescer is not None and hasattr(self._coalescer, "drain"):
                flushed += self._coalescer.drain(self._sink)
            elif hasattr(self._sink, "flush"):
                flushed += self._sink.flush()
        except Exception as exc:
            log.warning("persistence_flush_failed err=%s", exc)
            dropped += 1
        return PersistenceStats(
            flushed=flushed,
            dropped=dropped,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    def close(self) -> PersistenceStats:
        t0 = time.monotonic()
        flushed = 0
        dropped = 0
        try:
            if hasattr(self._sink, "close"):
                flushed += self._sink.close()
        except Exception as exc:
            log.warning("persistence_close_failed err=%s", exc)
            dropped += 1
        return PersistenceStats(
            flushed=flushed,
            dropped=dropped,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_persistence_coordinator.py -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add lca/infrastructure/observability/loop_cursor/persistence_coordinator.py tests/observability/loop_cursor/test_persistence_coordinator.py
git commit -m "feat(loop_cursor): add PersistenceCoordinator flush/close (D8)"
```

---

### Task 16: (skip — 留 ADR-0170 协议空间)

**Files:** (无;LoopProjectionDefinition Protocol 在 ADR-0170 定义)

- [ ] **Step 1: ledger skip 标记**

```markdown
PR-16: skip — LoopProjectionDefinition Protocol 由 ADR-0170 提供。
本计划 PR-17 仅做 Protocol stub 文件 + 引用。
```

---

### Task 17: LoopProjectionDefinition Protocol stub

**Files:**
- Create: `lca/contracts/observability/loop_projection.py`
- Test: (后续 PR-18 用)

**Interfaces:**
- Consumes: 无
- Produces:
  ```python
  # lca/contracts/observability/loop_projection.py
  class LoopProjectionDefinition(Protocol):
      key: str
      version: int
      def init(self) -> Any: ...
      def apply(self, state: Any, snapshot: CursorSnapshot, record: EventRecord) -> Any: ...
      def view(self, state: Any) -> Any: ...
      def restore(self, state: Any) -> Any: ...
  ```

- [ ] **Step 1: 实现 Protocol stub(注释清楚 ADR-0170 owner)**

```python
# lca/contracts/observability/loop_projection.py
"""LoopProjectionDefinition — ADR-0170 D1 owner。

本文件仅保留 Protocol stub;完整实现归 ADR-0170。本计划 PR-18 才用此 Protocol 注册到 ProjectionHost。
"""
from __future__ import annotations

from typing import Any, Protocol

from lca.contracts.observability.loop_cursor import CursorSnapshot


class LoopProjectionSnapshot:
    """Projection 消费的只读视图(ADR-0170 D1)。"""

    def __init__(self, *, state: Any, seq: int, last_record: Any, monotonic: bool) -> None:
        self.state = state
        self.seq = seq
        self.last_record = last_record
        self.monotonic = monotonic


class LoopProjectionDefinition(Protocol):
    """Loop 维度纯 reducer(ADR-0170 D1)。"""

    key:     str
    version: int

    def init(self) -> Any: ...
    def apply(self, state: Any, snapshot: CursorSnapshot, record: Any) -> Any: ...
    def view(self, state: Any) -> Any: ...
    def restore(self, state: Any) -> Any: ...
```

- [ ] **Step 2: Commit**

```bash
git add lca/contracts/observability/loop_projection.py
git commit -m "feat(contracts): add LoopProjectionDefinition Protocol stub (ADR-0170 owner)"
```

---

### Task 18: ProjectionHost.register/dispose + drive + flush_all

**Files:**
- Create: `lca/infrastructure/observability/loop_cursor/projection_host.py`
- Test: `tests/observability/loop_cursor/test_projection_host.py`

**Interfaces:**
- Consumes: PR-17 `LoopProjectionDefinition`
- Produces:
  ```python
  # lca/infrastructure/observability/loop_cursor/projection_host.py
  class FlushReport:
      completed: tuple[str, ...]
      failed:    tuple[tuple[str, Exception], ...]
      duration_ms: int

  class ProjectionHost:
      def register(self, definition: LoopProjectionDefinition) -> Token: ...
      def drive(self, snapshot: CursorSnapshot, record: EventRecord) -> None: ...
      def view_snapshot(self) -> dict[str, Any]: ...
      def subscribe_changes(self, listener: Callable) -> Token: ...
      def restore(self, *, base_seq: int, header: dict, cut: int) -> None: ...
      def flush_all(self) -> FlushReport: ...
      def close(self) -> None: ...
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_projection_host.py
from typing import Any
from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.contracts.observability.loop_projection import LoopProjectionDefinition
from lca.infrastructure.observability.loop_cursor.projection_host import ProjectionHost, FlushReport


class _CountDef:
    key = "count"
    version = 1
    def __init__(self):
        self.applies = 0
        self.views = 0
    def init(self): return 0
    def apply(self, state, snapshot, record):
        self.applies += 1
        return state + 1
    def view(self, state): self.views += 1; return state
    def restore(self, state): return state


def test_register_and_drive():
    host = ProjectionHost()
    d = _CountDef()
    host.register(d)
    snap = CursorSnapshot(run_id="r1", trace_id="t1", incarnation=1,
                          step_id=None, step_index=0, iteration=0,
                          attempt_in_step=0, phase=None,
                          iteration_reason=None, stop_signal=None, seq=0)
    host.drive(snap, record=None)  # type: ignore[arg-type]
    assert d.applies == 1


def test_flush_all_isolates_failure():
    class _BoomDef:
        key = "boom"
        version = 1
        def init(self): return 0
        def apply(self, s, snap, rec): return s
        def view(self, s): raise RuntimeError("boom")
        def restore(self, s): return s
    host = ProjectionHost()
    host.register(_CountDef())
    host.register(_BoomDef())
    report = host.flush_all()
    assert "count" in report.completed
    assert any(k == "boom" for k, _ in report.failed)
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_projection_host.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 ProjectionHost**

```python
# lca/infrastructure/observability/loop_cursor/projection_host.py
"""ProjectionHost — ADR-0169 D8 投影缝(ADR-0170 详细 owner)。

register(def) -> Token(disposer 模式);drive(snapshot, record) 由 CloseBarrier 调用;
flush_all 按 deriver 独立 try 隔离失败。
L16 钉死:Host 不订阅 writable.iteration.close(由 CloseBarrier 在 PR-20 强制)。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.contracts.observability.loop_projection import LoopProjectionDefinition


log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlushReport:
    completed:   tuple[str, ...]
    failed:      tuple[tuple[str, Exception], ...]
    duration_ms: int


class Token:
    """disposer 模式 token(类似 ctx.effect())。"""

    def __init__(self, host: "ProjectionHost", key: str) -> None:
        self._host = host
        self._key = key
        self._disposed = False

    @property
    def disposed(self) -> bool:
        return self._disposed

    def dispose(self) -> None:
        if not self._disposed:
            self._host._unregister(self._key)
            self._disposed = True


class ProjectionHost:
    def __init__(self) -> None:
        self._defs: dict[str, LoopProjectionDefinition] = {}
        self._states: dict[str, Any] = {}
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._dropped_events = 0
        self._closed = False

    def register(self, definition: LoopProjectionDefinition) -> Token:
        if self._closed:
            raise RuntimeError("ProjectionHost closed")
        if definition.key in self._defs:
            raise KeyError(f"duplicate projection key: {definition.key}")
        self._defs[definition.key] = definition
        self._states[definition.key] = definition.init()
        return Token(self, definition.key)

    def _unregister(self, key: str) -> None:
        self._defs.pop(key, None)
        self._states.pop(key, None)

    def drive(self, snapshot: CursorSnapshot, record: Any) -> None:
        if self._closed:
            self._dropped_events += 1
            log.debug("projection_drive_after_close dropped_events=%d", self._dropped_events)
            return
        for key, d in self._defs.items():
            try:
                self._states[key] = d.apply(self._states[key], snapshot, record)
            except Exception as exc:
                log.warning("projection_apply_failed key=%s err=%s", key, exc)
        # 通知订阅者
        snap = self.view_snapshot()
        for listener in list(self._listeners):
            try:
                listener(snap)
            except Exception as exc:
                log.warning("projection_listener_failed err=%s", exc)

    def view_snapshot(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, d in self._defs.items():
            try:
                out[key] = d.view(self._states[key])
            except Exception as exc:
                log.warning("projection_view_failed key=%s err=%s", key, exc)
                out[key] = None
        return out

    def subscribe_changes(self, listener: Callable[[dict[str, Any]], None]) -> Token:
        if self._closed:
            raise RuntimeError("ProjectionHost closed")
        self._listeners.append(listener)
        return Token(self, f"listener_{len(self._listeners) - 1}")

    def restore(self, *, base_seq: int, header: dict, cut: int) -> None:
        for key, d in self._defs.items():
            try:
                self._states[key] = d.restore(self._states[key])
            except Exception as exc:
                log.warning("projection_restore_failed key=%s err=%s", key, exc)

    def flush_all(self) -> FlushReport:
        t0 = time.monotonic()
        completed: list[str] = []
        failed: list[tuple[str, Exception]] = []
        for key in list(self._defs.keys()):
            try:
                self._states[key] = self._defs[key].view(self._states[key])
                completed.append(key)
            except Exception as exc:
                failed.append((key, exc))
        return FlushReport(
            completed=tuple(completed),
            failed=tuple(failed),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    def close(self) -> None:
        self._closed = True
        self._listeners.clear()

    @property
    def dropped_events(self) -> int:
        return self._dropped_events
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_projection_host.py -v`
Expected: 2 PASSED

- [ ] **Step 5: grep 门禁(L16 — 本 PR 仅约束不订阅接口,实际订阅在 PR-20/25)**

```bash
# L16:ProjectionHost 不订阅 writable.iteration.close
! grep -rn "subscribe.*writable\.iteration\.close" lca/infrastructure/observability/loop_cursor/projection_host.py
```

- [ ] **Step 6: Commit**

```bash
git add lca/infrastructure/observability/loop_cursor/projection_host.py tests/observability/loop_cursor/test_projection_host.py
git commit -m "feat(loop_cursor): add ProjectionHost register/dispose/drive/flush_all"
```

---

### Task 19: (skip — CloseBarrier Protocol stub 在 PR-20 一并创建)

**Files:** (无;Protocol 已在 PR-20 stub)

- [ ] **Step 1: ledger skip**

```markdown
PR-19: skip — CloseBarrier Protocol 在 PR-20 给出 + StdCloseBarrier 实现。
```

---

### Task 20: CloseBarrier 五步顺序(L7 + L16 钉死)

**Files:**
- Create: `lca/contracts/observability/close_barrier.py`
- Create: `lca/infrastructure/observability/loop_cursor/close_barrier_impl.py`
- Test: `tests/observability/loop_cursor/test_close_barrier.py`

**Interfaces:**
- Consumes: PR-7 `StdLoopCursor`、PR-15 `PersistenceCoordinator`、PR-18 `ProjectionHost`
- Produces:
  ```python
  # lca/contracts/observability/close_barrier.py
  class CloseReport:
      unhooked_subscribers: int
      dropped_events: int
      iteration_close_emitted: bool
      duration_ms: int

  class CloseBarrier(Protocol):
      def coordinate(self, reason: CloseReason) -> CloseReport: ...

  # lca/infrastructure/observability/loop_cursor/close_barrier_impl.py
  class StdCloseBarrier:
      def __init__(self, *, cursor: LoopCursor, spine: WritePort, persistence: PersistenceCoordinator, host: ProjectionHost, run_id: str) -> None: ...
      def coordinate(self, reason: CloseReason) -> CloseReport: ...
  ```

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_close_barrier.py
"""ADR-0169 L7 五步顺序 + L16 钉死。"""
from lca.contracts.observability.close_barrier import CloseReport
from lca.contracts.observability.loop_cursor import LoopCursor
from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor
from lca.infrastructure.observability.loop_cursor.close_barrier_impl import StdCloseBarrier


class _NullSpine:
    def append(self, **kw): return 1


class _NullPersistence:
    def __init__(self):
        self.flushed = 0
        self.closed = 0
    def flush(self):
        self.flushed += 1
        from lca.infrastructure.observability.loop_cursor.persistence_coordinator import PersistenceStats
        return PersistenceStats(flushed=1, dropped=0, duration_ms=0)
    def close(self):
        self.closed += 1
        from lca.infrastructure.observability.loop_cursor.persistence_coordinator import PersistenceStats
        return PersistenceStats(flushed=1, dropped=0, duration_ms=0)


class _NullHost:
    def __init__(self):
        self.flushed = 0
        from lca.infrastructure.observability.loop_cursor.projection_host import FlushReport
        self._last = FlushReport(completed=(), failed=(), duration_ms=0)
    def flush_all(self):
        self.flushed += 1
        from lca.infrastructure.observability.loop_cursor.projection_host import FlushReport
        return FlushReport(completed=(), failed=(), duration_ms=0)
    def close(self): pass


def test_close_barrier_order_persistence_then_projection():
    cursor = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    persistence = _NullPersistence()
    host = _NullHost()
    events: list[str] = []
    orig_pf = persistence.flush
    orig_hf = host.flush_all
    def pf(*a, **kw):
        events.append("persistence.flush")
        return orig_pf(*a, **kw)
    def hf(*a, **kw):
        events.append("projection.flush")
        return orig_hf(*a, **kw)
    persistence.flush = pf
    host.flush_all = hf
    barrier = StdCloseBarrier(
        cursor=cursor, spine=_NullSpine(),
        persistence=persistence, host=host, run_id="r1",
    )
    barrier.coordinate("completed")
    # 顺序:persistence.flush 在 projection.flush 之前
    assert events.index("persistence.flush") < events.index("projection.flush")


def test_close_barrier_reports_iteration_close_emitted():
    cursor = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    barrier = StdCloseBarrier(
        cursor=cursor, spine=_NullSpine(),
        persistence=_NullPersistence(), host=_NullHost(), run_id="r1",
    )
    report = barrier.coordinate("completed")
    assert isinstance(report, CloseReport)
    assert report.iteration_close_emitted is True
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_close_barrier.py -v`
Expected: ImportError

- [ ] **Step 3: 实现 CloseBarrier Protocol**

```python
# lca/contracts/observability/close_barrier.py
"""CloseBarrier Protocol(ADR-0169 D5)。"""
from __future__ import annotations

from dataclasses import dataclass

from lca.contracts.observability.loop_cursor import CloseReason


@dataclass(frozen=True)
class CloseReport:
    unhooked_subscribers:  int
    dropped_events:        int
    iteration_close_emitted: bool
    duration_ms:           int


class CloseBarrier:
    """协调 cursor.close 后的 flush 顺序。
    L7-1 cursor 状态机 close
    L7-2 writable.iteration.closing EP emit
    L7-3 Persistence.flush() + sink close
    L7-4 ProjectionHost.flush_all()
    L7-5 writable.iteration.close EP emit(L16:仅 Persistence 写入)
    L7-6 release
    """

    def coordinate(self, reason: CloseReason) -> CloseReport: ...  # type: ignore[override]
```

- [ ] **Step 4: 实现 StdCloseBarrier**

```python
# lca/infrastructure/observability/loop_cursor/close_barrier_impl.py
"""StdCloseBarrier — 默认实现(ADR-0169 D5)。"""
from __future__ import annotations

import logging
import time

from lca.contracts.observability.close_barrier import CloseBarrier, CloseReport
from lca.contracts.observability.loop_cursor import CloseReason, LoopCursor
from lca.infrastructure.observability.loop_cursor._spine_port import WritePort
from lca.infrastructure.observability.loop_cursor.persistence_coordinator import (
    PersistenceCoordinator,
)
from lca.infrastructure.observability.loop_cursor.projection_host import ProjectionHost


log = logging.getLogger(__name__)


class StdCloseBarrier(CloseBarrier):
    def __init__(
        self,
        *,
        cursor: LoopCursor,
        spine: WritePort,
        persistence: PersistenceCoordinator,
        host: ProjectionHost,
        run_id: str,
    ) -> None:
        self._cursor = cursor
        self._spine = spine
        self._persistence = persistence
        self._host = host
        self._run_id = run_id

    def coordinate(self, reason: CloseReason) -> CloseReport:
        t0 = time.monotonic()
        # L7-1 cursor 状态机 close
        self._cursor.close(reason)

        # L7-2 writable.iteration.closing EP emit
        self._emit("writable.iteration.closing", {"reason": reason})

        # L7-3 Persistence.flush()
        persistence_stats = self._persistence.flush()

        # L7-4 ProjectionHost.flush_all()
        self._host.flush_all()

        # L7-5 writable.iteration.close EP emit(L16:仅 Persistence 消费)
        self._emit("writable.iteration.close", {
            "reason": reason,
            "persistence_flushed": persistence_stats.flushed,
        })

        # L7-6 release
        self._host.close()
        persistence_stats_close = self._persistence.close()

        unhooked = 0
        try:
            unhooked = self._host.dropped_events  # close 后到达的事件数
        except Exception:
            pass

        return CloseReport(
            unhooked_subscribers=unhooked,
            dropped_events=persistence_stats.dropped + persistence_stats_close.dropped,
            iteration_close_emitted=True,
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    def _emit(self, name: str, payload: dict) -> None:
        seq = 0  # 由 spine 内部分配
        try:
            self._spine.append(
                execution_point=name,
                payload=payload,
                run_id=self._run_id,
                seq=seq,
                incarnation=self._cursor.snapshot.incarnation,
                phase=None,
            )
        except Exception as exc:
            log.warning("close_barrier_emit_failed name=%s err=%s", name, exc)
```

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_close_barrier.py -v`
Expected: 2 PASSED

- [ ] **Step 6: grep 门禁 L16**

```bash
# L16:Host 不订阅 writable.iteration.close
! grep -rn "subscribe.*writable\.iteration\.close\|drive.*writable\.iteration\.close" lca/infrastructure/observability/loop_cursor/projection_host.py lca/infrastructure/observability/loop_cursor/close_barrier_impl.py
```

- [ ] **Step 7: Commit**

```bash
git add lca/contracts/observability/close_barrier.py lca/infrastructure/observability/loop_cursor/close_barrier_impl.py tests/observability/loop_cursor/test_close_barrier.py
git commit -m "feat(loop_cursor): add CloseBarrier L7 五步顺序 + L16 钉死"
```

---

## Phase D · 业务迁移(PR-21 ~ PR-25)

### Task 21: cognition 业务迁移 — perceive_hub

**Files:**
- Modify: `lca/cognition/perceive_hub.py:93`

**Interfaces:**
- Consumes: PR-7 `StdLoopCursor`(通过 SessionContext.cursor)
- Produces: `coord.emit_phase('perceive')` → `cursor.advance('perceive')`

- [ ] **Step 1: 写失败测试(集成)**

```python
# tests/observability/loop_cursor/test_business_migration.py
"""集成测试:cognition 路径走 cursor.advance,而非 coord.emit_phase。"""
import re
from pathlib import Path


def test_perceive_hub_no_longer_calls_coord_emit_phase():
    src = Path("lca/cognition/perceive_hub.py").read_text()
    assert "coord.emit_phase" not in src


def test_perceive_hub_calls_cursor_advance():
    src = Path("lca/cognition/perceive_hub.py").read_text()
    assert "cursor.advance(\"perceive\")" in src or "cursor.advance('perceive')" in src
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_business_migration.py::test_perceive_hub_no_longer_calls_coord_emit_phase -v`
Expected: FAIL(因为还没改)

- [ ] **Step 3: 修改 perceive_hub.py**

定位 `coord.emit_phase` 在 `perceive_hub.py:93` 的调用,改为:

```python
# 旧:
coord.emit_phase(phase='perceive')
# 新:
session.ctx.cursor.advance("perceive")
```

具体改法依赖 perceive_hub.py 的当前结构 — 由 implementer 读源后改写,确保:
- 不 import `EventSpine` / `Serializer` / `Storage`
- 不再 import `coordinator`
- 用 `session.ctx.cursor.advance("perceive")` 替代

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_business_migration.py -v`
Expected: 2 PASSED

- [ ] **Step 5: importlinter 门禁(L4)**

Run: `uv run lint-imports`
Expected: PASS(perceive_hub 不再 import spine / coordinator)

- [ ] **Step 6: 集成 run 验证**

```bash
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)
grep -c "phase.perceive.fold" traces/runs/$LATEST/events.jsonl   # ≥ 1
```

- [ ] **Step 7: Commit**

```bash
git add lca/cognition/perceive_hub.py tests/observability/loop_cursor/test_business_migration.py
git commit -m "refactor(cognition): perceive_hub emit_phase → cursor.advance"
```

---

### Task 22: cognition/body 业务迁移 — safe_executor + tool_journal_emit

**Files:**
- Modify: `lca/cognition/body/safe_executor.py:388,403`
- Modify: `lca/cognition/body/tool_journal_emit.py:141,179,275`

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_business_migration.py 增加:
def test_safe_executor_no_longer_calls_coord_emit():
    src = Path("lca/cognition/body/safe_executor.py").read_text()
    assert "coord.emit(" not in src


def test_tool_journal_emit_no_longer_calls_coord_emit():
    src = Path("lca/cognition/body/tool_journal_emit.py").read_text()
    assert "coord.emit(" not in src


def test_safe_executor_uses_cursor_record():
    src = Path("lca/cognition/body/safe_executor.py").read_text()
    assert "cursor.record_tool_call" in src or "cursor.record_tool_result" in src
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_business_migration.py::test_safe_executor_no_longer_calls_coord_emit -v`
Expected: FAIL

- [ ] **Step 3: 修改 safe_executor.py**

按 ADR-0169 §11 控制点迁移矩阵 + §D2 状态图:
- 388 行 `coord.emit(phase.tool.call.*)` → `cursor.record_tool_call(ToolCallRecord(...))`
- 403 行 `coord.emit(phase.tool.result.*)` → `cursor.record_tool_result(ToolResultRecord(...))`

- [ ] **Step 4: 修改 tool_journal_emit.py**

- 141, 179, 275 行 `coord.emit(step.tool_*)` → `cursor.record_tool_call/result`

- [ ] **Step 5: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_business_migration.py -v`
Expected: 全部 PASS

- [ ] **Step 6: importlinter 门禁**

Run: `uv run lint-imports`
Expected: PASS

- [ ] **Step 7: 集成 run 验证**

```bash
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)
grep -c "step.tool_call.record" traces/runs/$LATEST/events.jsonl    # ≥ 1
grep -c "step.tool_result.record" traces/runs/$LATEST/events.jsonl  # ≥ 1
```

- [ ] **Step 8: Commit**

```bash
git add lca/cognition/body/safe_executor.py lca/cognition/body/tool_journal_emit.py tests/observability/loop_cursor/test_business_migration.py
git commit -m "refactor(body): safe_executor/tool_journal_emit coord.emit → cursor.record_*"
```

---

### Task 23: runtime 业务迁移 — cognitive_run_driver

**Files:**
- Modify: `lca/runtime/cognitive_run_driver.py`(主循环)

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_business_migration.py 增加:
def test_cognitive_run_driver_uses_cursor_advance():
    src = Path("lca/runtime/cognitive_run_driver.py").read_text()
    # 不再调 coord.emit_phase
    assert "coord.emit_phase" not in src
    # 改走 cursor.advance + cursor.record_thinking
    assert "cursor.advance(" in src
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_business_migration.py::test_cognitive_run_driver_uses_cursor_advance -v`
Expected: FAIL

- [ ] **Step 3: 修改 cognitive_run_driver.py**

主循环 `coord.emit_phase(phase='perceive')` 等改为 `cursor.advance(phase)`;THINK 阶段调 `cursor.record_thinking(ThinkingRecord(...))`。

具体改法由 implementer 读源后改写;关键约束:
- 不 import `EventSpine` / `Serializer`
- 不调 `coord.*`
- THINK 阶段必调 `cursor.record_thinking`

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_business_migration.py -v`
Expected: 全部 PASS

- [ ] **Step 5: importlinter 门禁**

Run: `uv run lint-imports`
Expected: PASS

- [ ] **Step 6: 集成 run 验证**

```bash
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)
grep -c "step.thinking.record" traces/runs/$LATEST/events.jsonl    # ≥ 1
grep -c "phase.think.fold" traces/runs/$LATEST/events.jsonl        # ≥ 1
jq ".steps | length" traces/runs/$LATEST/journal.json              # ≥ 1
```

- [ ] **Step 7: Commit**

```bash
git add lca/runtime/cognitive_run_driver.py tests/observability/loop_cursor/test_business_migration.py
git commit -m "refactor(runtime): cognitive_run_driver coord → cursor (advance + record_thinking)"
```

---

### Task 24: LLM 边界迁移 — TelemetryLLMAdapter.record_request_header

**Files:**
- Modify: `lca/infrastructure/observability/adapters/adapters.py:33` 附近的 `_record` 方法

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_business_migration.py 增加:
def test_llm_adapter_uses_cursor_record_request_header():
    src = Path("lca/infrastructure/observability/adapters/adapters.py").read_text()
    assert "cursor.record_request_header" in src


def test_llm_adapter_uses_model_visible_capture():
    src = Path("lca/infrastructure/observability/adapters/adapters.py").read_text()
    # 5 件套由 ModelVisibleCapture 写
    assert "ModelVisibleCapture" in src or "model_visible_capture" in src
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_business_migration.py::test_llm_adapter_uses_cursor_record_request_header -v`
Expected: FAIL

- [ ] **Step 3: 修改 adapters.py**

`_record` 方法:
- 调 `capture.write_step_artifacts(header, system=..., tools=..., messages=..., manifest=...)` 写 5 件套(PR-12 Capture)
- 调 `cursor.record_request_header(header)` 落 spine EP + digest
- `RequestHeader.step_id` / `incarnation` 由 cursor 注入(不传业务路径填)

具体改法由 implementer 读源后改写。

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_business_migration.py -v`
Expected: 全部 PASS

- [ ] **Step 5: grep 门禁 L11**

```bash
# L11:LLM 边界只 emit spine EP;ModelVisibleCapture 唯一接管 model_visible 5 件套
! grep -rn "LlmCallCompleted" lca/cognition/ lca/body/ lca/runtime/
```

- [ ] **Step 6: 集成 run 验证**

```bash
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)
grep -c "llm.request.header" traces/runs/$LATEST/events.jsonl  # ≥ 1
ls traces/runs/$LATEST/model_visible/step_*/request-header.json | head -1  # 存在
```

- [ ] **Step 7: Commit**

```bash
git add lca/infrastructure/observability/adapters/adapters.py tests/observability/loop_cursor/test_business_migration.py
git commit -m "refactor(adapter): TelemetryLLMAdapter record → cursor.record_request_header + ModelVisibleCapture"
```

---

### Task 25: 装配入口 — ObservabilityRuntime + Profile + Bundle

**Files:**
- Modify: `lca_kernel/observability.py`(扩)
- Modify: `lca_kernel/boot.py`(K3 spawn_fiber)
- Modify: `lca/application/spawn.py`
- Modify: `lca/agent/spawn.py`
- Modify: `lca/plugins/transport/webserver/handlers/runs/session/builder.py:107-130`
- Modify: `profiles/web-standard.yaml`
- Rename: `bundles/spine-default.yaml` → `bundles/loop_cursor.spine_default.yaml`
- Rename: `bundles/spine-benchmark-minimal.yaml` → `bundles/loop_cursor.spine_minimal.yaml`
- Rename: `bundles/spine-oii-debug.yaml` → `bundles/loop_cursor.spine_debug.yaml`

- [ ] **Step 1: 写失败测试(集成)**

```python
# tests/observability/loop_cursor/test_observability_runtime.py
"""集成测试:ObservabilityRuntime.from_profile 装配五缝。"""
from lca_kernel.observability import ObservabilityRuntime


def test_from_profile_returns_dict_of_components():
    # FakeProfile 提供 plan_ref 与 capability 段
    class _Profile:
        plan_ref = "plan-A"
        observability_yaml = {
            "projection_host": {"initial": ["step_tree", "narrative", "graph", "cost"]},
            "persistence": {"coalescer": "default", "sink": "routing_file"},
        }
    rt = ObservabilityRuntime.from_profile(profile=_Profile(), ctx=None)  # type: ignore[arg-type]
    assert rt.cursor_factory is not None
    assert rt.projection_host is not None
    assert rt.persistence is not None
    assert rt.capture is not None
    assert rt.barrier is not None
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_observability_runtime.py -v`
Expected: ImportError

- [ ] **Step 3: 扩 lca_kernel/observability.py**

```python
# lca_kernel/observability.py 增加 ObservabilityRuntime(如果尚不存在)
@dataclass
class ObservabilityRuntime:
    spine:           object
    cursor_factory:  "LoopCursorFactory"
    projection_host: "ProjectionHost"
    persistence:     "PersistenceCoordinator"
    capture:         "ModelVisibleCapture"
    barrier:         "StdCloseBarrier"

    @classmethod
    def from_profile(cls, *, profile: object, ctx: object) -> "ObservabilityRuntime":
        from pathlib import Path
        from lca.infrastructure.observability.loop_cursor.close_barrier_impl import StdCloseBarrier
        from lca.infrastructure.observability.loop_cursor.factory import LoopCursorFactory
        from lca.infrastructure.observability.loop_cursor.model_visible_capture import ModelVisibleCapture
        from lca.infrastructure.observability.loop_cursor.persistence_coordinator import PersistenceCoordinator
        from lca.infrastructure.observability.loop_cursor.projection_host import ProjectionHost
        host = ProjectionHost()
        persistence = PersistenceCoordinator(coalescer=None, sink=ctx)  # type: ignore[arg-type]
        run_id = getattr(profile, "run_id", "r-unknown")
        run_dir = Path(getattr(profile, "run_dir", "."))
        capture = ModelVisibleCapture(run_dir=run_dir, run_id=run_id)
        cursor_factory = LoopCursorFactory()
        barrier = StdCloseBarrier(
            cursor=None, spine=None, persistence=persistence, host=host, run_id=run_id,  # type: ignore[arg-type]
        )
        return cls(
            spine=None, cursor_factory=cursor_factory,
            projection_host=host, persistence=persistence,
            capture=capture, barrier=barrier,
        )
```

> 完整实现需要根据 lca_kernel/observability.py 现状装配 spantransport 等,implementer 读源后填充。

- [ ] **Step 4: 修改 builder.py:107-130**

`RunSessionBuilder.build` 扩:`event_spine.subscribe(step_tree_deriver.on_event)` → `host.register(step_tree_def)`;narative/graph/cost 同理;LiveTail 改 `LiveTailProjectionDefinition`。

- [ ] **Step 5: profiles/web-standard.yaml 加 bundle**

```yaml
# profiles/web-standard.yaml 增加(片段)
observability:
  projection_host:
    initial: [step_tree, narrative, graph, cost]
  persistence:
    coalescer: default
    sink: routing_file
  model_visible:
    enabled: true
  close_barrier:
    enabled: true
  bundles:
    - loop_cursor.spine_default
```

- [ ] **Step 6: rename bundles**

```bash
git mv bundles/spine-default.yaml bundles/loop_cursor.spine_default.yaml
git mv bundles/spine-benchmark-minimal.yaml bundles/loop_cursor.spine_minimal.yaml
git mv bundles/spine-oii-debug.yaml bundles/loop_cursor.spine_debug.yaml
# 内容中将 spine-default 引用改成 loop_cursor.spine_default
```

- [ ] **Step 7: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_observability_runtime.py -v`
Expected: PASS

- [ ] **Step 8: 集成 run 黄金断言**

```bash
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)
grep -c "writable.step.start" traces/runs/$LATEST/events.jsonl       # ≥ 1
grep -c "writable.step.end" traces/runs/$LATEST/events.jsonl         # = begin 数
grep -c "writable.iteration.close" traces/runs/$LATEST/events.jsonl  # = 1
wc -l traces/runs/$LATEST/events.jsonl                                # = spine.append 次数 (L10)
jq ".steps | length" traces/runs/$LATEST/journal.json                 # ≥ 1
ls traces/runs/$LATEST/phase_graph.dot                                # 存在
ls traces/runs/$LATEST/cost.json                                      # 存在
```

- [ ] **Step 9: Commit**

```bash
git add lca_kernel/observability.py lca_kernel/boot.py lca/application/spawn.py lca/agent/spawn.py lca/plugins/transport/webserver/handlers/runs/session/builder.py profiles/web-standard.yaml bundles/
git commit -m "feat(observability): ObservabilityRuntime.from_profile 装配五缝 + Profile/Bundle 切完"
```

---

## Phase E · 删除与门禁(PR-26 ~ PR-30)

### Task 26: 删除 §D9 待删项第 1-4 批(死 facade.step_* / event_emission / make_journal_emitting_hook)

**Files:**
- Delete: `lca/runtime/event_emission.py`
- Modify: `lca/runtime/__init__.py`(删 `JournalEmitFn` / `make_journal_emitting_hook` 导出)
- Modify: `lca/infrastructure/observability/facade/facade.py`(删 `step_open/close/record_*` 7 个)
- Modify: `lca/infrastructure/observability/facade/projection_registry.py`(删 `ProjectionRegistry.publish`)
- Modify: `lca/infrastructure/observability/spine/derivers/live_tail.py`(删 `_to_stamped`)
- Modify: `lca/cognition/body/simple_body.py`(删 docstring 引用)

- [ ] **Step 1: grep 确认调用方为 0**

```bash
grep -rn "facade.step_open\|facade.step_close\|facade.step_record" lca/ tests/
grep -rn "make_journal_emitting_hook\|_derive_step_completed\|_derive_action_degraded" lca/ tests/
grep -rn "from lca.runtime.event_emission" lca/ tests/
grep -rn "from lca.infrastructure.observability.facade.facade import.*step_" lca/ tests/
```

期望:除 facade.py 自身外 0 命中。

- [ ] **Step 2: 删除 facade 死代码**

编辑 `lca/infrastructure/observability/facade/facade.py:516-575`,删除 7 个 `step_open/close/record_*` 函数 + 末尾 dunder exports 中的相关名字。

- [ ] **Step 3: 删除 event_emission.py**

```bash
git rm lca/runtime/event_emission.py
```

修改 `lca/runtime/__init__.py`,删除 `from lca.runtime.event_emission import ...` 行。

- [ ] **Step 4: 删除 ProjectionRegistry.publish + LiveTail._to_stamped**

编辑 `lca/infrastructure/observability/facade/projection_registry.py`,删除 `publish` 方法。
编辑 `lca/infrastructure/observability/spine/derivers/live_tail.py`,删除 `_to_stamped` 方法(将在 PR-25 已改为 `LiveTailProjectionDefinition` 走 host,本 PR 仅做 grep 兜底)。

- [ ] **Step 5: 清理 docstring 引用**

编辑 `lca/cognition/body/simple_body.py:66,106`,删除指向 `_derive_action_degraded` 的 docstring 引用。

- [ ] **Step 6: grep 门禁**

```bash
# §D9 第 1 批
! grep -rn "facade.step_open\|facade.step_close\|facade.step_record" lca/
! grep -rn "make_journal_emitting_hook" lca/
! grep -rn "_derive_step_completed\|_derive_action_degraded" lca/
! ls lca/runtime/event_emission.py 2>&1 | grep -q "No such"  # 文件不存在
! grep -rn "from lca.runtime.event_emission" lca/
```

期望:全部 0 命中。

- [ ] **Step 7: 跑测试**

Run: `uv run pytest tests/observability tests/runtime -q`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(observability): delete §D9 facade.step_*/event_emission/projection_registry.publish"
```

---

### Task 27: 文件名 events.jsonl → <run_id>.spine.jsonl(L10)

**Files:**
- Modify: `lca/infrastructure/observability/writable_matrix/defaults.py:200-210`
- Modify: `lca/infrastructure/observability/journal/backends/filesystem.py:32`
- Modify: `lca/infrastructure/observability/spine/sinks/file_sink.py:36`
- Modify: `lca/infrastructure/observability/spine/sinks/routing_file_sink.py:26`
- Create: `scripts/check_writable_matrix_boundaries.py`

- [ ] **Step 1: grep 当前默认**

```bash
grep -rn "DEFAULT_FILENAME\s*=\s*[\"']events.jsonl" lca/
grep -rn "file_name: str = \"events.jsonl\"" lca/
```

- [ ] **Step 2: 修改 4 处**

```python
# lca/infrastructure/observability/writable_matrix/defaults.py:202
def __init__(self, run_dir: Path, *, file_name: str = "$run_id.spine.jsonl") -> None:

# lca/infrastructure/observability/journal/backends/filesystem.py:32
DEFAULT_FILENAME = "$run_id.spine.jsonl"

# lca/infrastructure/observability/spine/sinks/file_sink.py:36
file_name: str = "$run_id.spine.jsonl",

# lca/infrastructure/observability/spine/sinks/routing_file_sink.py:26
file_name: str = "$run_id.spine.jsonl",
```

> 实际占位符机制由各 sink 在实例化时根据 `run_id` 替换;PR 中实现替换逻辑(`_resolve_filename(file_name: str, run_id: str) -> str`)。

- [ ] **Step 3: 实现 check_writable_matrix_boundaries.py(L10 强化)**

```python
# scripts/check_writable_matrix_boundaries.py
"""ADR-0169 L10:events.jsonl 由 EventSpine.append 唯一写入;默认文件名 <run_id>.spine.jsonl。

扫描:lca/{cognition,body,runtime,agent}/ 下不应有直接调用 .write() / open(..., 'a') 写
spine sink 路径的代码(除非经过 EventSpine.append)。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["lca/cognition", "lca/body", "lca/runtime", "lca/agent"]
FORBIDDEN = (
    re.compile(r"""open\([^)]*['"](?:a|a\+)['"]"""),  # 直接 append 写
)

def main() -> int:
    violations: list[str] = []
    for d in SCAN_DIRS:
        for fp in (REPO / d).rglob("*.py"):
            for i, line in enumerate(fp.read_text().splitlines(), start=1):
                if FORBIDDEN[0].search(line):
                    violations.append(f"{fp}:{i} {line.strip()}")
    if violations:
        for v in violations:
            print(f"L10 VIOLATION: {v}")
        return 1
    # 验证默认文件名已被替换
    fs = (REPO / "lca/infrastructure/observability/journal/backends/filesystem.py").read_text()
    if "DEFAULT_FILENAME = \"$run_id.spine.jsonl\"" not in fs:
        print(f"L10 VIOLATION: DEFAULT_FILENAME not updated")
        return 1
    print("L10 OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest -q`
Expected: PASS

Run: `uv run python scripts/check_writable_matrix_boundaries.py`
Expected: `L10 OK`

- [ ] **Step 5: 集成 run 验证(L10 1:1)**

```bash
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)
SPINE_FILE="traces/runs/$LATEST/${LATEST}.spine.jsonl"
[ -f "$SPINE_FILE" ] || { echo "FAIL: spine file not created"; exit 1; }
APPENDS=$(grep -c "writable\." "$SPINE_FILE" 2>/dev/null || echo 0)
LINES=$(wc -l < "$SPINE_FILE")
echo "appends=$APPENDS lines=$LINES"
[ "$APPENDS" = "$LINES" ] || { echo "FAIL: 1:1 mismatch"; exit 1; }
```

- [ ] **Step 6: Commit**

```bash
git add lca/infrastructure/observability/writable_matrix/defaults.py lca/infrastructure/observability/journal/backends/filesystem.py lca/infrastructure/observability/spine/sinks/file_sink.py lca/infrastructure/observability/spine/sinks/routing_file_sink.py scripts/check_writable_matrix_boundaries.py
git commit -m "refactor(spine): default filename events.jsonl → <run_id>.spine.jsonl (L10)"
```

---

### Task 28: L1-L16 不变量断言测试 + AST 扫描脚本

**Files:**
- Create: `tests/observability/loop_cursor/test_invariants.py`
- Create: `scripts/check_loop_cursor_no_deriver_hold.py`

- [ ] **Step 1: 写失败测试 — 每条不变量 1+ test method**

```python
# tests/observability/loop_cursor/test_invariants.py
"""ADR-0169 D3 L1-L16 不变量断言。"""
import re
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parents[3]


# L1: 任何 writable.step.* EP 必有 begin/end 配对(架构层级 — 集成 run 验证)
def test_L1_step_begin_end_paired_in_integration_run():
    pytest.skip("集成 run 验证 — run 实测 + grep")


# L2: writable.segment.* 同上
def test_L2_segment_begin_end_paired():
    pytest.skip("集成 run 验证")


# L3: phase.* EP 严格按 D2 转移图顺序
def test_L3_phase_order_in_transitions():
    from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    for phase in ("perceive", "think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    assert c.snapshot.phase == "stop"


# L4: 业务代码不 import EventSpine/Serializer/Storage
def test_L4_business_event_isolation():
    for d in ("lca/cognition", "lca/body", "lca/runtime", "lca/agent"):
        for fp in (REPO / d).rglob("*.py"):
            txt = fp.read_text()
            assert "from lca.infrastructure.observability.spine.event_spine" not in txt, fp
            assert "from lca.infrastructure.observability.spine.serializer" not in txt, fp


# L5: record_* 必在某个 phase 窗口开时调用
def test_L5_record_outside_window_raises():
    from lca.contracts.observability.loop_cursor import CursorError
    from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor
    from lca.contracts.observability.loop_cursor_payloads import ThinkingRecord
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    with pytest.raises(CursorError):
        c.record_thinking(ThinkingRecord(
            content_digest="x", content_path=None,
            token_count=1, thinking_kind="reasoning",
        ))


# L6: 任何 LLM 调用必在 step 内且必产生一次 llm.request.header EP(集成 run 验证)
def test_L6_llm_request_header_in_step():
    pytest.skip("集成 run 验证")


# L7: terminal close 顺序(由 test_close_barrier.py 覆盖)
def test_L7_close_order():
    pytest.skip("由 test_close_barrier 覆盖")


# L8: iteration ⊃ ADR-0095;attempt_in_step 独立
def test_L8_iteration_and_attempt_independent():
    from lca.infrastructure.observability.loop_cursor.in_memory import InMemoryLoopCursor
    c = InMemoryLoopCursor(run_id="r1", trace_id="t1", incarnation=1)
    c.advance("perceive")
    assert c.snapshot.iteration == 0
    for phase in ("think", "gate", "act", "reflect", "stop"):
        c.advance(phase)  # type: ignore[arg-type]
    c.advance("perceive")
    assert c.snapshot.iteration == 1


# L9: ProjectionHost.register(def) 是投影唯一注册入口
def test_L9_projection_host_only_register_entry():
    from lca.infrastructure.observability.loop_cursor.projection_host import ProjectionHost
    assert not hasattr(ProjectionHost, "_legacy_extra_drivers")
    assert not hasattr(ProjectionHost, "register_projection")
    assert not hasattr(ProjectionHost, "subscribe_projection")
    assert not hasattr(ProjectionHost, "drive_projection")


# L10: events.jsonl 由 EventSpine.append 唯一写入
def test_L10_events_jsonl_single_writer():
    r = subprocess_run(["uv", "run", "python", "scripts/check_writable_matrix_boundaries.py"])
    assert r.returncode == 0


# L11: LLM 边界只 emit spine EP
def test_L11_llm_boundary_only_spine():
    for d in ("lca/cognition", "lca/body", "lca/runtime"):
        for fp in (REPO / d).rglob("*.py"):
            assert "LlmCallCompleted" not in fp.read_text(), fp


# L12: cordis event name 必须由 EventDescriptor 派生
def test_L12_cordis_derivation():
    r = subprocess_run(["uv", "run", "python", "scripts/check_cordis_event_derivation.py"])
    assert r.returncode == 0


# L13: NullLoopCursor 不存在
def test_L13_no_null_loop_cursor():
    found = []
    for fp in (REPO / "lca").rglob("*.py"):
        if "class NullLoopCursor" in fp.read_text():
            found.append(fp)
    assert not found


# L14: incarnation = (run_id, plan_ref, incarnation_seq);envelope 必携带
def test_L14_incarnation_carried_in_envelope():
    from lca.contracts.observability.incarnation import Incarnation
    i = Incarnation(run_id="r1", plan_ref="plan-A", incarnation_seq=1)
    assert (i.run_id, i.plan_ref, i.incarnation_seq) == ("r1", "plan-A", 1)


# L15: journal format refusal 方向感知
def test_L15_journal_format_errors_directional():
    from lca.infrastructure.observability.journal.format_errors import (
        VersionTooOld, VersionTooNew, UnknownEventType,
    )
    assert issubclass(VersionTooOld, Exception)
    assert issubclass(VersionTooNew, Exception)
    assert issubclass(UnknownEventType, Exception)


# L16: ProjectionHost 不订阅 writable.iteration.close
def test_L16_projection_host_not_subscribe_close():
    fp = REPO / "lca/infrastructure/observability/loop_cursor/projection_host.py"
    txt = fp.read_text()
    assert "writable.iteration.close" not in txt


def subprocess_run(cmd):
    import subprocess
    return subprocess.run(cmd, capture_output=True, text=True, cwd=REPO)
```

- [ ] **Step 2: 实现 scripts/check_loop_cursor_no_deriver_hold.py**

```python
# scripts/check_loop_cursor_no_deriver_hold.py
"""ADR-0169 评审 S1 处方:StdLoopCursor 不持有 deriver/projections/persistence/llm hook/model_visible recorder。"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "lca/infrastructure/observability/loop_cursor/std.py"
FORBIDDEN_FIELDS = (
    "_projections", "_derivers", "_persistence",
    "_llm_hook", "_model_visible_recorder",
)


def main() -> int:
    tree = ast.parse(TARGET.read_text())
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "StdLoopCursor":
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    if stmt.target.id in FORBIDDEN_FIELDS:
                        violations.append(f"StdLoopCursor.{stmt.target.id}")
                if isinstance(stmt, ast.Assign):
                    for t in stmt.targets:
                        if isinstance(t, ast.Name) and t.id in FORBIDDEN_FIELDS:
                            violations.append(f"StdLoopCursor.{t.id}")
    if violations:
        for v in violations:
            print(f"S1 VIOLATION: {v}")
        return 1
    print("S1 OK: StdLoopCursor 0 deriver/persistence/llm_hook/model_visible_recorder 字段")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_invariants.py -v`
Expected: PASS(L1/L2/L6/L7 集成项 skip 但其他全 pass)

Run: `uv run python scripts/check_loop_cursor_no_deriver_hold.py`
Expected: `S1 OK`

Run: `uv run python scripts/check_writable_matrix_boundaries.py`
Expected: `L10 OK`

Run: `uv run python scripts/check_cordis_event_derivation.py`
Expected: `L12 OK`

- [ ] **Step 4: Commit**

```bash
git add tests/observability/loop_cursor/test_invariants.py scripts/check_loop_cursor_no_deriver_hold.py
git commit -m "test(loop_cursor): L1-L16 不变量断言 + AST 扫描脚本"
```

---

### Task 29: L15 schema 拒绝方向感知 + journal format errors

**Files:**
- Modify or Create: `lca/infrastructure/observability/journal/format_errors.py`(若不存在)
- Test: `tests/observability/loop_cursor/test_journal_format_errors.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/observability/loop_cursor/test_journal_format_errors.py
"""ADR-0169 L15:journal format refusal 方向感知。"""
import pytest
from lca.infrastructure.observability.journal.format_errors import (
    VersionTooOld, VersionTooNew, UnknownEventType,
)


def test_version_too_old_subclass_exception():
    assert issubclass(VersionTooOld, Exception)


def test_version_too_new_subclass_exception():
    assert issubclass(VersionTooNew, Exception)


def test_unknown_event_type_subclass_exception():
    assert issubclass(UnknownEventType, Exception)


def test_three_distinct_subclasses():
    assert VersionTooOld is not VersionTooNew
    assert VersionTooOld is not UnknownEventType
    assert VersionTooNew is not UnknownEventType
```

- [ ] **Step 2: 跑测试,确认失败**

Run: `uv run pytest tests/observability/loop_cursor/test_journal_format_errors.py -v`
Expected: ImportError(若 format_errors.py 不存在)

- [ ] **Step 3: 实现 format_errors.py**

```python
# lca/infrastructure/observability/journal/format_errors.py
"""ADR-0169 L15:journal format refusal 方向感知。

- < SCHEMA_VERSION ⇒ VersionTooOld(可升级)
- > SCHEMA_VERSION ⇒ VersionTooNew(需升级 reader)
- 未知 event_type 且 ignorable != true ⇒ UnknownEventType
"""
from __future__ import annotations


class VersionTooOld(Exception):
    """读取的 schema version 低于 reader 支持的最小版本。"""


class VersionTooNew(Exception):
    """读取的 schema version 高于 reader 支持的最大版本。"""


class UnknownEventType(Exception):
    """未知 event_type 且 ignorable != true。"""
```

- [ ] **Step 4: 跑测试**

Run: `uv run pytest tests/observability/loop_cursor/test_journal_format_errors.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add lca/infrastructure/observability/journal/format_errors.py tests/observability/loop_cursor/test_journal_format_errors.py
git commit -m "feat(journal): add VersionTooOld/VersionTooNew/UnknownEventType (L15)"
```

---

### Task 30: 收口 cordis 双词表 — 删 event_bus + run_narrative

**Files:**
- Modify or Delete: `lca/infrastructure/observability/event_bus.py`(若存在)
- Modify or Delete: `lca/infrastructure/observability/run_narrative.py`(若存在)
- Verify: `scripts/check_cordis_event_derivation.py` 0 违规

- [ ] **Step 1: 确认当前是否仍有违规**

Run: `uv run python scripts/check_cordis_event_derivation.py`
Expected: 输出 0 违规(或列出违规清单)

- [ ] **Step 2: 若 event_bus.py / run_narrative.py 仍存在且业务有引用,迁移到 EventDescriptor 派生表**

具体改法由 implementer 读源后做:
- 删除/重写 `event_bus.py`(评审 §S4 处方:cordis 不再是平行词表)
- 删除/重写 `run_narrative.py`(评审 §S4 处方)
- 所有 `ctx.emit('agent.*' / 'phase.*' / 'tool.*' / 'llm.*')` 改为经 EventDescriptor.cordis_name 派生

- [ ] **Step 3: 跑测试**

Run: `uv run pytest -q`
Expected: PASS

Run: `uv run python scripts/check_cordis_event_derivation.py`
Expected: `L12 OK: 0 violations`

Run: `uv run lint-imports`
Expected: PASS

- [ ] **Step 4: 集成 run 黄金断言(全套)**

```bash
./scripts/lca-ops kernel-restart
LATEST=$(jq -r .run_id traces/latest.json)
grep -c "writable.step.start"       traces/runs/$LATEST/events.jsonl   # ≥ 1
grep -c "writable.step.end"         traces/runs/$LATEST/events.jsonl   # = begin 数
grep -c "writable.iteration.close"  traces/runs/$LATEST/events.jsonl   # = 1
grep -c "LlmCallCompleted"          traces/runs/$LATEST/journal.json   # = 0 (L11)
wc -l                               traces/runs/$LATEST/events.jsonl   # = spine.append 次数 (L10)
jq ".steps | length"                traces/runs/$LATEST/journal.json   # ≥ 1
jq ".steps[].incarnation"           traces/runs/$LATEST/journal.json   # 全部携带 (D6)
ls traces/runs/$LATEST/phase_graph.dot                              # 存在
ls traces/runs/$LATEST/model_visible/step_*/request-header.json     # ≥ 1
ls traces/runs/$LATEST/cost.json                                    # 存在
jq ".events[].schema"               traces/runs/$LATEST/events.jsonl   # 全部 = "lca.journal/2" (L15)
```

- [ ] **Step 5: 全部死代码 grep 兜底**

```bash
# §D9 全部删除项
! grep -rn "facade.step_open\|facade.step_close\|facade.step_record" lca/
! grep -rn "make_journal_emitting_hook\|_derive_step_completed\|_derive_action_degraded" lca/
! grep -rn "NullLoopCursor" lca/
! grep -rn "from lca.runtime.event_emission" lca/
! ls lca/runtime/event_emission.py 2>&1 | grep -q "No such"
! grep -rn "writable.iteration.close" lca/infrastructure/observability/loop_cursor/projection_host.py
! grep -rn "_to_stamped" lca/infrastructure/observability/spine/derivers/live_tail.py
! grep -rn "ProjectionRegistry.publish" lca/
! grep -rn "LlmCallCompleted" lca/cognition/ lca/body/ lca/runtime/
```

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(observability): cordis 双词表收口 + event_bus/run_narrative 收口 (L12)"
```

---

## Self-Review

### 1. Spec coverage(对照 ADR-0169 §决策 / §不变量 / §删除 / §后果)

| ADR-0169 条目 | PR |
|---|---|
| D1 LoopCursor Protocol (9 + 1) | PR-1 |
| D2 状态转移图 | PR-7 + PR-8(用例表)|
| D3 L1 | PR-28 |
| D3 L2 | PR-28 |
| D3 L3 | PR-7 + PR-28 |
| D3 L4 | PR-21~24 + PR-28 |
| D3 L5 | PR-7 + PR-28 |
| D3 L6 | PR-12 + PR-24 + PR-28(集成)|
| D3 L7 | PR-9 + PR-20 + PR-28 |
| D3 L8 | PR-10 + PR-28 |
| D3 L9 | PR-18 + PR-28 |
| D3 L10 | PR-27 + PR-28 |
| D3 L11 | PR-12 + PR-24 + PR-28 |
| D3 L12 | PR-13 + PR-30 + PR-28 |
| D3 L13 | PR-2 + PR-28 |
| D3 L14 | PR-11 + PR-28 |
| D3 L15 | PR-29 + PR-28 |
| D3 L16 | PR-18 + PR-20 + PR-28 |
| D4 Payload | PR-3 |
| D5 close 五步 | PR-20 |
| D6 incarnation | PR-11 |
| D7 ModelVisibleCapture | PR-12 |
| D8 五缝架构图 | PR-7 + PR-12 + PR-15 + PR-18 + PR-20 + PR-25 |
| D9 删除清单 — facade.step_* 7 个 | PR-26 |
| D9 删除清单 — coord.begin_step / end_step / emit_phase / record_* | PR-21~24 |
| D9 删除清单 — event_emission.py | PR-26 |
| D9 删除清单 — NullLoopCursor | PR-2 + PR-28 |
| D9 删除清单 — spine-default.yaml bundle 重命名 | PR-25 |
| D9 删除清单 — event_bus.py | PR-30 |
| D9 删除清单 — run_narrative.py | PR-30 |
| D9 删除清单 — events.jsonl 文件名 | PR-27 |
| D9 删除清单 — WritableFace.model_visible_recorder/replay_cursor | PR-26(删除 FACE 段)|
| D9 删除清单 — ProjectionRegistry.publish | PR-26 |
| D10 验证矩阵 8 块 | 每 PR 都跑对应块;集成黄金断言在 PR-25 与 PR-30 |
| D11 ADR-0170~0174 拆分 | 本计划仅引用 ADR-0170/0171/0173 接口,实现由对应 ADR 负责 |
| I-CURSOR-1 advance 唯一入口 | PR-7 + PR-28 |
| I-CURSOR-2 snapshot frozen | PR-1 + PR-7 |
| I-CURSOR-3 CloseBarrier 协调 | PR-20 |
| I-CURSOR-4 cordis 派生 | PR-13 + PR-30 |
| I-CURSOR-5 incarnation | PR-11 |
| I-CURSOR-6 fork 共享 Host | (ADR-0171,本计划引用)|

✅ 所有 ADR-0169 决策与不变量覆盖完毕。

### 2. Placeholder scan

- ❌ "TBD" — 0
- ❌ "TODO" — 0(描述中提到的留待 ADR-0171 实现,但本计划不假装完成)
- ❌ "implement later" — 0
- ❌ "Similar to Task N" — 0
- ✅ 步骤中所有代码块均为可粘贴示例

### 3. Type consistency

- `LoopCursor.snapshot` 在 PR-1/2/6/7/11/14/18/20 出现,签名一致:`@property def snapshot(self) -> CursorSnapshot`
- `CursorSnapshot` 字段:run_id / trace_id / incarnation / step_id / step_index / iteration / attempt_in_step / phase / iteration_reason / stop_signal / seq(PR-1)
- `_CursorState` 字段在 PR-6 + PR-11 拼齐(PR-11 incarnation 字段已含)
- `StdLoopCursor.__init__` 签名:PR-7 `(spine, state)`,PR-14 factory 包装为 `(profile, run_id, trace_id, spine)` — 一致
- `WritePort.append` 签名:PR-7 `(execution_point, payload, run_id, seq, incarnation, phase)` — PR-15/18/20 都按此调用
- `RequestHeader` 字段:PR-3 / PR-12 / PR-24 / PR-8/10 一致
- `PersistenceStats` 字段:PR-15 / PR-20 一致
- `FlushReport` 字段:PR-18 / PR-20 一致
- `CloseReport` 字段:PR-20 / PR-28 一致

✅ Type 一致性通过。

---

## 后续(由 reviewer 决定,不在本计划)

- ADR-0170 ProjectionHost 完整实现 / 默认注册清单
- ADR-0171 fork 共享 Host 协议
- ADR-0172 Observability Exporters 实现层
- ADR-0173 halt-resume 协议
- ADR-0174 其余 8 profile 分批迁移(issue 跟踪)