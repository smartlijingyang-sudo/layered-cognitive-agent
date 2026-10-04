# Muse 活动动态弹窗高保真对齐与生产者真值归一实施计划 (Plan A+)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 彻底消除右侧抽屉动态弹窗的硬编码与重复步骤，将身份铸造与真值元数据（退出码、耗时、标准错误）上移至生产者，Fold 退化为纯按 ID 归组，以纯函数状态机与 5 要素证据面板端到端对齐 Muse 生产实机截图。

**Architecture:** 
1. **生产者契约收敛**：`llm.request.header.assistant` 隔离为 `PredictedIntent`，不触碰 `tool_calls`；`Body.dispatch_tool_calls` 一次性铸造 `invocation_id` 全链透传；`step.tool_result.record` 注入真实 `exit_code`，消灭双写与文本挖掘猜状态。
2. **纯函数状态机与纯渲染模型**：`deriveStepState` 纯函数派生（`●`、`✔`、`📄`、`✕`、`◐`）；`parse_step_evidence` 清除全部死常数，成为由真实元数据驱动的纯渲染器。
3. **前端高保真补丁**：重构 `AssistantStatusDrawer.tsx`，对齐 Muse 截图（胶囊状态药丸、极简文本点标、无多余小标题与技术标签）。

**Tech Stack:** Python 3.11+, Pydantic v2, TypeScript / React, Ant Design / @lobehub/ui, Pytest.

---

### Task 1: 生产者收敛与身份全链透传 (INV-01, INV-02)

**Files:**
- Modify: `lca/plugins/session/derivers/step_tree/journal_fold.py`
- Modify: `lca/cognition/body/executor/simple_body.py`
- Create: `tests/loop/test_tool_invocation_id_lifecycle.py`
- Create: `tests/session/derivers/test_journal_fold_zero_duplicate.py`
- Does NOT own: `lca/infrastructure/sandbox/`, `lca/cognition/brain/`
- Invariants to test: `INV-01`（唯一身份全链透传，禁止空串与 decision_id 覆写）, `INV-02`（`header.assistant` 不碰 `tool_calls`，零孪生步骤）

**Step 1: Write the failing tests**
编写 `tests/session/derivers/test_journal_fold_zero_duplicate.py` 与 `tests/loop/test_tool_invocation_id_lifecycle.py`，模拟 `llm.request.header.assistant` 伴随 `step.tool_call.record` 和 `step.tool_result.record`，断言 `len(step.tool_calls) == 1`，断言无重复步骤。

**Step 2: Run test to verify it fails**
Run: `pytest tests/session/derivers/test_journal_fold_zero_duplicate.py -v`
Expected: FAIL（当前会产生 2 个 tool_call 记录）。

**Step 3: Write minimal implementation**
- 在 `journal_fold.py` 中，当 `ep == "llm.request.header.assistant"` 时，仅记录 `predicted_intents` 到 `target.thinking`，**严禁向 `target.tool_calls` append 记录**。
- `body.tool.execute.end` 不再作为 `_assign_tool_result`，确立 `step.tool_result.record` 为单工具结果唯一事实源。
- 确保 `SimpleBody.dispatch_tool_calls` 铸造的 `call.call_id` 全链透传给 SafeExecutor 与事件。

**Step 4: Run test to verify it passes**
Run: `pytest tests/session/derivers/test_journal_fold_zero_duplicate.py tests/loop/test_tool_invocation_id_lifecycle.py -v`
Expected: PASS。

**Step 5: Commit**
```bash
git add lca/plugins/session/derivers/step_tree/journal_fold.py lca/cognition/body/executor/simple_body.py tests/session/derivers/test_journal_fold_zero_duplicate.py tests/loop/test_tool_invocation_id_lifecycle.py
git commit -m "fix(fold): isolate predicted intents and unify tool invocation id lifecycle (INV-01, INV-02)"
```

---

### Task 2: 真值字段上移与退出码契约 (INV-03)

**Files:**
- Modify: `lca/loop/commit/tool_journal.py`
- Modify: `lca/cognition/body/executor/safe_executor/executor.py`
- Create: `tests/cognition/body/test_tool_result_true_exit_code.py`
- Does NOT own: `lca/plugins/transport/webserver/`
- Invariants to test: `INV-03`（`record_step_tool_result` 携带结构化 `exit_code: int` 与真实 `duration_ms`）

**Step 1: Write the failing test**
编写 `tests/cognition/body/test_tool_result_true_exit_code.py`，验证执行成功/失败工具时，`step.tool_result.record` Payload 必须包含结构化 `exit_code: int`（成功 0，失败非 0），且 `latency_ms` 为正整数。

**Step 2: Run test to verify it fails**
Run: `pytest tests/cognition/body/test_tool_result_true_exit_code.py -v`
Expected: FAIL。

**Step 3: Write minimal implementation**
- 在 `record_step_tool_result` 的参数与 Payload 中增加 `exit_code: int = 0`。
- 在 `SafeExecutor.execute` 中，从 `observation.extra.get("exit_code")` 或 `0 if observation.success else 1` 提取真实退出码，透传给 `record_step_tool_result`。

**Step 4: Run test to verify it passes**
Run: `pytest tests/cognition/body/test_tool_result_true_exit_code.py -v`
Expected: PASS。

**Step 5: Commit**
```bash
git add lca/loop/commit/tool_journal.py lca/cognition/body/executor/safe_executor/executor.py tests/cognition/body/test_tool_result_true_exit_code.py
git commit -m "feat(executor): propagate structured exit_code and true latency in tool results (INV-03)"
```

---

### Task 3: 契约解析纯净化与魔法值清理 (INV-04, INV-06)

**Files:**
- Modify: `lca/contracts/models/observability/activity.py`
- Modify: `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py`
- Create: `tests/observability/test_activity_evidence_zero_hardcoding.py`
- Create: `tests/observability/test_step_evidence_failure_propagation.py`
- Does NOT own: `lca/infrastructure/sandbox/`
- Invariants to test: `INV-04`（零 ZZSTART 启发式、零 3841ms 魔数、零 fake pytest）, `INV-06`（失败流真实携带 exit_code 与 stderr 并提炼结论）

**Step 1: Write the failing tests**
编写 `test_activity_evidence_zero_hardcoding.py`（AST 扫描断言无 `3841`、无 `ZZSTART` 文本挖掘、无写死助理 ID）与 `test_step_evidence_failure_propagation.py`（失败工具生成的 `StepEvidence` 必须携带真实 `exit_code=1`、`iconType='error'` 与真实原因）。

**Step 2: Run test to verify it fails**
Run: `pytest tests/observability/test_activity_evidence_zero_hardcoding.py tests/observability/test_step_evidence_failure_propagation.py -v`
Expected: FAIL。

**Step 3: Write minimal implementation**
- 重构 `activity.py::parse_step_evidence`：
  - 删除 `3841ms`、`ZZSTART` 边界猜测、fake pytest、`asst_3dacffc01a90`。
  - 直接读取 `tool_result` 中的 `duration_ms`、`exit_code`、`stderr`、`stdout`、`error`。
  - 失败时输出动态验证结论：`验证结论：动作执行未达预期（退出码 {exit_code}）。原因：{error_reason}。`
- 在 `query_endpoints.py::_read_run_journal_detail` 中，防御性消重并注入提取好的真实 evidence。

**Step 4: Run test to verify it passes**
Run: `pytest tests/observability/test_activity_evidence_zero_hardcoding.py tests/observability/test_step_evidence_failure_propagation.py -v`
Expected: PASS。

**Step 5: Commit**
```bash
git add lca/contracts/models/observability/activity.py lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py tests/observability/test_activity_evidence_zero_hardcoding.py tests/observability/test_step_evidence_failure_propagation.py
git commit -m "refactor(activity): purge mock magics and ensure real failure propagation (INV-04, INV-06)"
```

---

### Task 4: COMPAT 紧邻前驱单条合并 Shim (INV-08)

**Files:**
- Modify: `lca/plugins/session/derivers/step_tree/journal_fold.py`
- Create: `tests/session/derivers/test_journal_fold_compat_shim.py`
- Does NOT own: `lca/contracts/`
- Invariants to test: `INV-08`（COMPAT Shim 仅允许合并紧邻前驱未匹配项，严禁跨多条误吞）

**Step 1: Write the failing test**
编写 `tests/session/derivers/test_journal_fold_compat_shim.py`，构造历史脏数据场景（连续两个同名同参数的独立调用），断言 Shim 绝不会把两个连续调用错吞为一条。

**Step 2: Run test to verify it fails**
Run: `pytest tests/session/derivers/test_journal_fold_compat_shim.py -v`
Expected: FAIL。

**Step 3: Write minimal implementation**
在 `journal_fold.py` 的过渡兼容分支上收窄匹配窗口为 `[-1]`（仅限紧邻前驱单条），并标明 `# COMPAT: clean up after legacy run traces migration, owner: observability, delete-when: v1.0-release`。

**Step 4: Run test to verify it passes**
Run: `pytest tests/session/derivers/test_journal_fold_compat_shim.py -v`
Expected: PASS。

**Step 5: Commit**
```bash
git add lca/plugins/session/derivers/step_tree/journal_fold.py tests/session/derivers/test_journal_fold_compat_shim.py
git commit -m "fix(fold): restrict compat merge window to immediate predecessor with delete-when (INV-08)"
```

---

### Task 5: 纯函数状态机与前端高保真双栏补丁 (INV-05, INV-07)

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Modify: `deploy/lobehub/patches/ui/assistant_status_drawer.py`
- Create: `tests/deploy/test_step_state_machine_purity.py`
- Modify: `tests/deploy/test_assistant_status_drawer.py`
- Does NOT own: `lca/contracts/`, `lca/cognition/`
- Invariants to test: `INV-05`（纯函数状态机确定性，区分 📄/✔/✕/◐/●）, `INV-07`（TSX 补丁无写死标题、无多色 Tag 堆砌、Header 状态胶囊动态联动）

**Step 1: Write the failing tests**
编写 `tests/deploy/test_step_state_machine_purity.py` 与更新 `tests/deploy/test_assistant_status_drawer.py`，断言状态机纯函数覆盖全部 5 类图标，断言 TSX 补丁中彻底清除了 `'验证Activity重启与事件完整性'` 兜底文本与 `"🧠 智能体意图与执行叙述"` 小标题。

**Step 2: Run test to verify it fails**
Run: `pytest tests/deploy/test_step_state_machine_purity.py tests/deploy/test_assistant_status_drawer.py -v`
Expected: FAIL。

**Step 3: Write minimal implementation**
- 导出并实现 `deriveStepState` 纯函数。
- 重构 `AssistantStatusDrawer.tsx`：
  - Header：还原胶囊状态药丸（`✓ 已完成` / `● 进行中` / `✕ 执行失败`）+ 任务大标题，彻底删除 `Run: run_xxx`。
  - 左栏：移除 `"本次思考与调用概要"`，基于 `deriveStepState` 渲染 `●`、`✔`、`📄`、`✕`、`◐`。
  - 右栏：二级大标题紧接自然动作叙述（删除“🧠 智能体意图与执行叙述”小标题）；`执行的命令::` bash 块；极简点标元数据（`· 退出码: 0, 耗时: 120ms`）；代码高亮块/检索结果编号列表；加粗 `验证结论`。
  - 首节点 `● 已开始` 兜底改为动态 `runDetail?.question || act.title || '智能体执行任务'`。
- 执行 `python deploy/lobehub/patch_lobehub.py`。

**Step 4: Run test to verify it passes**
Run: `pytest tests/deploy/test_step_state_machine_purity.py tests/deploy/test_assistant_status_drawer.py -v`
Expected: PASS。

**Step 5: Commit**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx deploy/lobehub/patches/ui/assistant_status_drawer.py tests/deploy/test_step_state_machine_purity.py tests/deploy/test_assistant_status_drawer.py
git commit -m "feat(ui): align activity modal with Muse UX and pure-function state machine (INV-05, INV-07)"
```

---

### Task 6: 全链路回归、Pre-push 门禁与真实端到端验收

**Files:**
- Test: All created test files
- Does NOT own: Host machine files outside repository
- Invariants to test: All INV-01 ~ INV-08

**Step 1: Run comprehensive invariant tests**
Run:
```bash
pytest tests/loop/test_tool_invocation_id_lifecycle.py \
       tests/session/derivers/test_journal_fold_zero_duplicate.py \
       tests/cognition/body/test_tool_result_true_exit_code.py \
       tests/observability/test_activity_evidence_zero_hardcoding.py \
       tests/observability/test_step_evidence_failure_propagation.py \
       tests/session/derivers/test_journal_fold_compat_shim.py \
       tests/deploy/test_step_state_machine_purity.py \
       tests/deploy/test_assistant_status_drawer.py -v
```
Expected: 100% PASS。

**Step 2: Run patch integrity check**
Run:
```bash
python deploy/lobehub/patch_lobehub.py
python deploy/lobehub/check_patch_integrity.py
```
Expected: 82/82 files byte-identical PASS。

**Step 3: Run hygiene check**
Run:
```bash
ruff check lca/ deploy/lobehub/ tests/
git diff --check
```
Expected: 0 errors, 0 warnings.

**Step 4: Restart kernel & live validation**
Run:
```bash
./scripts/lca-ops kernel-restart
curl -s -H "Authorization: Bearer lca-local" -H "x-lca-user-id: local-dev-user" http://127.0.0.1:8765/runs/run_16bb13cc3385 | jq '.steps[] | {step_id, tool_name: .tool_call.name, exit_code: .evidence.exit_code}'
```
Expected: steps 不再重复（仅 1 个 tool_search 和 1 个 composioConnect），exit_code 真实为 0，弹窗呈现 Muse 高保真双栏效果。

**Step 5: Commit & update docs**
```bash
git add docs/plans/task.md
git commit -m "docs(plans): complete Muse activity modal dynamic alignment plan (Plan A+)"
```
