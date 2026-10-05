# 代码库深度架构加深与接缝收敛实施计划 (第二轮 - Round 2)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 深度重构与收敛全仓 4 处过度微拆分、套娃结构与滞留垫片代码（DecisionGates 扁平化、Transport Ingest 流水线收纳、ContextFiles 垫片清理与 MemoryTools 接缝、Read Runs 读侧投影聚合），提升模块深度、就地理解性与维护效率。

**Architecture:** 依据 John Ousterhout 深度模块原则与 LCA 架构守则，消除浅微目录与空 `__init__.py`，收拢分散的微逻辑为高内聚深度类与模块，提供统一简洁的高杠杆门面，通过自动化测试不变量（INV-ARCH-08 ~ INV-ARCH-15）全程防护。

**Tech Stack:** Python 3.12, Pytest, FastAPI, Pydantic, Ruff

---

### Task 1: Cognition DecisionGates 微目录扁平化与策略聚合

**Files:**
- Create:
  - `lca/cognition/brain/decision_gates/chained.py`
  - `lca/cognition/brain/decision_gates/repeat.py`
  - `lca/cognition/brain/decision_gates/loop_guards.py`
  - `lca/cognition/brain/decision_gates/multi_tool_loop.py`
  - `lca/cognition/brain/decision_gates/delivery.py`
  - `lca/cognition/brain/decision_gates/terminal.py`
  - `lca/cognition/brain/decision_gates/artifact.py`
  - `lca/cognition/brain/decision_gates/auth.py`
  - `lca/cognition/brain/decision_gates/consult.py`
  - `lca/cognition/brain/decision_gates/office.py`
- Modify:
  - `lca/cognition/brain/decision_gates/__init__.py`
  - `lca/plugins/cognitive/gate/artifact_respond_injector/plugin.py`
  - `lca/plugins/cognitive/gate/chained/plugin.py`
  - `lca/plugins/cognitive/gate/delivery_satisfied/plugin.py`
  - `lca/plugins/cognitive/gate/must_consult_all/plugin.py`
  - `lca/plugins/cognitive/gate/multi_tool_loop_breaker/plugin.py`
  - `lca/plugins/cognitive/gate/progress_loop_detector/plugin.py`
  - `lca/plugins/cognitive/gate/repeat_tool_call/plugin.py`
  - `lca/plugins/cognitive/gate/terminal_respond/plugin.py`
  - `lca/plugins/cognitive/gate/tool_loop_breaker/plugin.py`
- Delete:
  - `lca/cognition/brain/decision_gates/artifact/`
  - `lca/cognition/brain/decision_gates/auth/`
  - `lca/cognition/brain/decision_gates/chained/`
  - `lca/cognition/brain/decision_gates/delivery/`
  - `lca/cognition/brain/decision_gates/loop/`
  - `lca/cognition/brain/decision_gates/must/`
  - `lca/cognition/brain/decision_gates/office/`
  - `lca/cognition/brain/decision_gates/progress/`
  - `lca/cognition/brain/decision_gates/repeat/`
  - `lca/cognition/brain/decision_gates/terminal/`
  - `lca/cognition/brain/decision_gates/tool/`
- Test:
  - `tests/cognition/brain/test_decision_gates_flattened_chain.py`
- Does NOT own: 严禁变动 `lca/nodes/think/` 内部认知图拓扑或改变 `DecisionGate` 协议签名 (AP-01)。
- Invariants to test:
  - `INV-ARCH-08`: 默认决策门链中 6 个 Gate 按序执行，各 Gate 的决策拦截/放行语义绝对不变。
  - `INV-ARCH-09`: `lca/cognition/brain/decision_gates/` 内部不再包含任何子目录或 1 行空 `__init__.py`。

**Step 1: Write the failing test**
编写 `tests/cognition/brain/test_decision_gates_flattened_chain.py` 验证各决策门在扁平化模块下的引入与链式装配，断言目录无微子目录。

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/cognition/brain/test_decision_gates_flattened_chain.py --no-cov -v`
Expected: FAIL

**Step 3: Implement minimal code**
创建扁平化模块，迁移逻辑，更新 `decision_gates/__init__.py`，更新各 plugin 与现有测试的 import，删除旧微目录。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/cognition/ tests/scenario/ -k "gate" --no-cov -v`
Expected: PASS

**Step 5: Commit**
`git add lca/cognition/brain/decision_gates/ lca/plugins/cognitive/gate/ tests/`
`git commit -m "refactor(cognition): flatten decision gates micro-directories into cohesive modules"`

---

### Task 2: Transport Ingest 文件摄取流水线深度收拢

**Files:**
- Create:
  - `lca/plugins/transport/webserver/handlers/runs/ingest/models.py`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/cache.py`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/policy.py`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/fetcher.py`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/service.py`
- Modify:
  - `lca/plugins/transport/webserver/handlers/runs/ingest/__init__.py`
  - `lca/plugins/transport/webserver/handlers/runs/api/attachment_staging.py`
- Delete:
  - `lca/plugins/transport/webserver/handlers/runs/ingest/cache/`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/fetcher/`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/ingest/`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/ingress/`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/integrity/`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/models/`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/policy/`
  - `lca/plugins/transport/webserver/handlers/runs/ingest/service/`
- Test:
  - `tests/lca_plugins/transport/webserver/test_ingest_pipeline_unified.py`
- Does NOT own: 严禁变动 `attachment_staging.py` 外部 API 响应或修改 Attachment 模型 (AP-01)。
- Invariants to test:
  - `INV-ARCH-10`: 缓存命中、SSRF 拦截、完整性校验与多文件拉取在收敛后表现一致。
  - `INV-ARCH-11`: `handlers/runs/ingest/` 下不再存在任何 `x/x.py` 套娃目录或冗余门面。

**Step 1: Write the failing test**
编写 `tests/lca_plugins/transport/webserver/test_ingest_pipeline_unified.py` 覆盖缓存、SSRF、哈希校验、无套娃目录结构。

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/lca_plugins/transport/webserver/test_ingest_pipeline_unified.py --no-cov -v`
Expected: FAIL

**Step 3: Implement minimal code**
在 `handlers/runs/ingest/` 平铺 5 个模块，更新 `__init__.py`，删除 8 个套娃子目录及 `ingest/ingest/ingest.py`。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/lca_plugins/transport/webserver/test_ingest_pipeline_unified.py --no-cov -v`
Expected: PASS

**Step 5: Commit**
`git add lca/plugins/transport/webserver/handlers/runs/ingest/ tests/lca_plugins/transport/webserver/`
`git commit -m "refactor(transport): consolidate ingest pipeline micro-packages into deep modules"`

---

### Task 3: ContextFiles 滞留垫片清零与 MemoryTools 接缝

**Files:**
- Modify:
  - `lca/infrastructure/memory/contextfiles/service/watch.py`
  - `lca/infrastructure/tools/assistant/memory_tools.py`
- Delete:
  - `lca/infrastructure/memory/contextfiles/domain/diff.py`
  - `lca/infrastructure/memory/contextfiles/domain/edit.py`
  - `lca/infrastructure/memory/contextfiles/service/memory_edit_sync.py`
- Test:
  - `tests/infrastructure/memory/test_contextfiles_shims_removed.py`
  - `tests/infrastructure/tools/test_memory_tools_unified_context_seam.py`
- Does NOT own: 严禁改变 `AssistantMemory` 语义或触碰 `lca/cognition/memory/` (AP-01)。
- Invariants to test:
  - `INV-ARCH-12`: 3 处滞留 forwarding shims 物理删除，全仓 import 洁净。
  - `INV-ARCH-13`: `_BaseMemoryTool` 提供统一文件存储与目录属性，内存工具不发生重复无状态构造与污染。

**Step 1: Write the failing test**
编写 `tests/infrastructure/memory/test_contextfiles_shims_removed.py` 与 `tests/infrastructure/tools/test_memory_tools_unified_context_seam.py`。

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/infrastructure/memory/test_contextfiles_shims_removed.py tests/infrastructure/tools/test_memory_tools_unified_context_seam.py --no-cov -v`
Expected: FAIL

**Step 3: Implement minimal code**
更新 `watch.py` 与 `memory_tools.py` 导入指向 `contextfiles/sync.py`；删除旧垫片；在 `_BaseMemoryTool` 增加 `_file_store`, `_sidechat_dir`, `_people_dir`, `_groups_dir`。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/infrastructure/memory/ tests/infrastructure/tools/ --no-cov -v`
Expected: PASS

**Step 5: Commit**
`git add lca/infrastructure/memory/contextfiles/ lca/infrastructure/tools/assistant/ tests/`
`git commit -m "refactor(memory): remove residual contextfiles shims and unify memory tools directory seam"`

---

### Task 4: Transport Read Runs 读侧微目录收拢

**Files:**
- Create:
  - `lca/plugins/transport/webserver/read/runs/terminal.py`
  - `lca/plugins/transport/webserver/read/runs/live.py`
  - `lca/plugins/transport/webserver/read/runs/evidence.py`
  - `lca/plugins/transport/webserver/read/runs/identity.py`
- Modify:
  - `lca/plugins/transport/webserver/read/runs/__init__.py`
  - `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py`
  - `lca/plugins/transport/webserver/handlers/runs/session/builder/builder.py`
- Delete:
  - `lca/plugins/transport/webserver/read/runs/artifact/`
  - `lca/plugins/transport/webserver/read/runs/error/`
  - `lca/plugins/transport/webserver/read/runs/evidence/`
  - `lca/plugins/transport/webserver/read/runs/failure/`
  - `lca/plugins/transport/webserver/read/runs/identity/`
  - `lca/plugins/transport/webserver/read/runs/journal/`
  - `lca/plugins/transport/webserver/read/runs/live/`
  - `lca/plugins/transport/webserver/read/runs/step/`
  - `lca/plugins/transport/webserver/read/runs/terminal/`
- Test:
  - `tests/lca_plugins/transport/webserver/test_read_runs_unified.py`
- Does NOT own: 严禁变动 `query_endpoints.py` 的 HTTP 路由契约或响应 JSON 格式 (AP-01)。
- Invariants to test:
  - `INV-ARCH-14`: 终态与活跃 Run 投影读取、步骤树物化结果与收拢前完全一致。

**Step 1: Write the failing test**
编写 `tests/lca_plugins/transport/webserver/test_read_runs_unified.py` 覆盖 4 个深度模块的投影查询与物化行为。

**Step 2: Run test to verify it fails**
Run: `uv run pytest tests/lca_plugins/transport/webserver/test_read_runs_unified.py --no-cov -v`
Expected: FAIL

**Step 3: Implement minimal code**
在 `read/runs/` 下实现 `terminal.py`、`live.py`、`evidence.py`、`identity.py`，更新 `__init__.py`，更新调用点，删除 8 个微目录。

**Step 4: Run test to verify it passes**
Run: `uv run pytest tests/lca_plugins/transport/webserver/test_read_runs_unified.py --no-cov -v`
Expected: PASS

**Step 5: Commit**
`git add lca/plugins/transport/webserver/read/runs/ lca/plugins/transport/webserver/handlers/ tests/`
`git commit -m "refactor(transport): consolidate read runs projections into deep modules"`

---

### Task 5: 全量回归验证、门禁体验与追踪看板闭环

**Files:**
- Modify:
  - `docs/plans/task.md`
- Does NOT own: 任何超出 4 阶段范围的代码 (AP-01)。
- Invariants to test:
  - `INV-ARCH-15`: `ruff check` 0 报错、`ruff format --check` 全通、相关自动化测试全绿、`git diff --check` clean。

**Step 1: Run all test suites across all 4 phases**
Run: `uv run pytest tests/cognition/brain/test_decision_gates_flattened_chain.py tests/lca_plugins/transport/webserver/test_ingest_pipeline_unified.py tests/infrastructure/memory/test_contextfiles_shims_removed.py tests/infrastructure/tools/test_memory_tools_unified_context_seam.py tests/lca_plugins/transport/webserver/test_read_runs_unified.py --no-cov -v`
Expected: PASS (all tests green)

**Step 2: Run linters and checks**
Run: `uv run ruff check`
Run: `git diff --check`
Expected: 0 errors, clean git diff

**Step 3: Update live task tracker**
Update `docs/plans/task.md` marking all tasks completed.

**Step 4: Commit**
`git add docs/plans/task.md`
`git commit -m "docs(plans): complete all 5 Round 2 codebase architecture deepening tasks in tracker"`
