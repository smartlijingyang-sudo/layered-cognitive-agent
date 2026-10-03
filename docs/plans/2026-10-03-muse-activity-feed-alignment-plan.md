# Muse 动态栏与任务详情双栏高保真对齐实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 像素级与信息架构全面对齐 Meta Muse 实机截图——抽屉列表彻底移除技术徽标并展示纯自然语言流，任务详情弹窗还原绿色状态药丸、左侧真实动作步骤树（首节点为“已开始”）与右侧 5 要素高保真证据面板（含 bash 命令语法高亮块、代码提取片段、检索结果与验证结论），并由底层通用语义解构器杜绝硬编码死字符串。

**Architecture:** 单轨事实源（Spine/Journal）驱动，通过 `ActivityIntentNamer` 通用工程语义解构器动态生成人读动作短语，扩展 `EvidenceParser` 结构化派生 5 要素证据模型，在前端 `AssistantStatusDrawer.tsx` 补丁中完成双栏高保真渲染与补丁同步，全量不变量通过自动化测试刚性守护。

**Tech Stack:** Python 3.11+, Pydantic v2, TypeScript, React, Ant Design, LobeHub patch engine, Pytest.

---

### Task 1: 契约层通用动态语义解构器与结构化证据模型

**Files:**
- Modify: `lca/contracts/models/observability/activity.py`
- Test: `tests/contracts/models/observability/test_activity_contract.py`
- Does NOT own: `deploy/lobehub/`, `lca/cognition/`, `lca/runtime/safe_executor/` (AP-01)
- Invariants to test: INV-01 (动态意图零硬编码，杜绝 "Running command"), INV-05 (右侧证据 5 要素结构化完整性) (AP-02)

**Step 1: 编写红灯测试**
在 `tests/contracts/models/observability/test_activity_contract.py` 中编写参数化测试：
```python
def test_activity_intent_namer_dynamic_deconstruction_no_running_command():
    test_cases = [
        ("run_shell", {"command": "sed -n '285,340p' activity_projector.py"}, "读取 activity_projector.py (285-340行)"),
        ("box_run_command", {"command": "grep -E 'seed_from_|rehydrate_' lca/"}, "在 lca/ 检索 seed_from_|rehydrate_ 关键词"),
        ("shell", {"command": "git worktree add -b iter-restart-1640"}, "创建工作树 iter-restart-1640"),
        ("run_shell", {"command": "python tmp/test_restart.py"}, "执行 tmp/test_restart.py 验证"),
        ("writeFile", {"name": "tmp/add_seed.py"}, "创建脚本 tmp/add_seed.py"),
    ]
    for tool_name, args, expected_keyword in test_cases:
        title, summary, icon = ActivityIntentNamer.name(tool_name, args)
        assert "Running command" not in title
        assert any(k in title for k in expected_keyword.split())

def test_evidence_parser_five_elements_structure():
    parsed = parse_step_evidence(
        tool_name="box_run_command",
        arguments={"command": "ssh252 'echo \"ZZSTART\"; sed -n \"285,340p\" activity_projector.py'"},
        tool_result={"ok": True, "latency_ms": 3841, "stdout_head": "class ActivityProjector:\n    def __init__..."}
    )
    assert parsed.command.startswith("ssh252")
    assert parsed.duration_ms == 3841
    assert parsed.exit_code == 0
    assert len(parsed.code_snippets) > 0
    assert parsed.conclusion is not None
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/contracts/models/observability/test_activity_contract.py -k "test_activity_intent_namer_dynamic_deconstruction" -v`  
Expected: FAIL (因当前仍返回 "Running command")

**Step 3: 编写核心实现**
在 `lca/contracts/models/observability/activity.py` 中实现通用语义解构器与 `StepEvidence` / `parse_step_evidence`：
- 解构常见动词：`git`, `grep/rg`, `sed/cat/head/tail`, `pytest/python`, `write/touch`, `mkdir` 等；
- 提取命令行中的目标文件名、行号、关键词、分支名，拼装为精准中文动作短语；
- 结构化提取 `command`, `code_snippets`, `metadata`, `conclusion`。

**Step 4: 运行测试验证通过**
Run: `pytest tests/contracts/models/observability/test_activity_contract.py -v`  
Expected: PASS

**Step 5: 提交代码**
```bash
git add lca/contracts/models/observability/activity.py tests/contracts/models/observability/test_activity_contract.py
git commit -m "feat(activity): add universal semantic intent deconstruction and StepEvidence model"
```

---

### Task 2: 后端真值打通与 Run Steps 结构化证据投影

**Files:**
- Modify: `lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py`
- Test: `tests/scenario/runs/test_runs_query_endpoint.py`
- Does NOT own: `lca/cognition/`, `deploy/lobehub/` (AP-01)
- Invariants to test: INV-02 (真实执行事实证据溯源), INV-06 (只读观测隔离，零控制面副作用) (AP-02)

**Step 1: 编写红灯测试**
在 `tests/scenario/runs/test_runs_query_endpoint.py` 中验证 `GET /runs/{run_id}` 返回的 steps 包含结构化的 `evidence` 对象：
```python
def test_get_run_detail_returns_structured_evidence(client, sample_journal_path):
    response = client.get("/runs/run_sample_001")
    assert response.status_code == 200
    data = response.json()
    assert "steps" in data
    first_step = data["steps"][0]
    assert "evidence" in first_step
    assert "command" in first_step["evidence"]
    assert "code_snippets" in first_step["evidence"]
    assert "conclusion" in first_step["evidence"]
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/scenario/runs/test_runs_query_endpoint.py -v`  
Expected: FAIL (缺少结构化 evidence 字段)

**Step 3: 实现 query_endpoints.py 结构化组装**
在 `_read_run_journal_detail` 中，对每个工具调用步骤调用 `parse_step_evidence`，将其作为 `evidence` 注入到 step dict 中，保留真实命令与退出码。

**Step 4: 运行测试验证通过**
Run: `pytest tests/scenario/runs/test_runs_query_endpoint.py -v`  
Expected: PASS

**Step 5: 提交代码**
```bash
git add lca/plugins/transport/webserver/handlers/runs/api/query_endpoints.py tests/scenario/runs/test_runs_query_endpoint.py
git commit -m "feat(runs): enrich run step details with structured StepEvidence"
```

---

### Task 3: 前端抽屉列表高保真对齐（清除技术徽章，纯自然语言流）

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Test: `tests/deploy/test_assistant_status_drawer.py`
- Does NOT own: 后端 Python contracts, runtime (AP-01)
- Invariants to test: INV-03 (抽屉列表无技术徽标不变量) (AP-02)

**Step 1: 编写红灯测试**
在 `tests/deploy/test_assistant_status_drawer.py` 中编写断言：
```python
def test_drawer_list_has_no_technical_badges():
    content = Path("deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx").read_text(encoding="utf-8")
    assert "COMMAND" not in content
    assert "toolBadge: a.tool_name || a.category" not in content
    assert "mapStatusToIcon" in content or "status === 'completed'" in content
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/deploy/test_assistant_status_drawer.py -k "test_drawer_list_has_no_technical_badges" -v`  
Expected: FAIL

**Step 3: 优化 AssistantStatusDrawer.tsx 抽屉条目排版**
- 彻底移除 `Tag` / `toolBadge` 显示；
- 左侧渲染深色圆角方框，内置圆形勾选图标（完成态白勾，运行态圆环，失败态红叉）；
- 中间渲染纯中文标题、一句话结果摘要与友好时间戳（`4:39 pm`）；
- 点击整行唤起详情弹窗。

**Step 4: 同步补丁并运行测试验证**
Run: `python scripts/patch_lobehub.py && pytest tests/deploy/test_assistant_status_drawer.py -v`  
Expected: PASS

**Step 5: 提交代码**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx tests/deploy/test_assistant_status_drawer.py
git commit -m "feat(ui): align activity drawer list with Muse pure natural language flow"
```

---

### Task 4: 前端任务详情双栏弹窗高保真对齐（绿色药丸 + 真实步骤树 + 5 要素证据面板）

**Files:**
- Modify: `deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx`
- Test: `tests/deploy/test_assistant_status_drawer.py`
- Does NOT own: 后端 Python 领域层 (AP-01)
- Invariants to test: INV-04 (时间轴首节点必为“已开始”，真实动作步骤排列), INV-05 (右侧证据 5 要素高保真卡片) (AP-02)

**Step 1: 编写红灯测试**
在 `tests/deploy/test_assistant_status_drawer.py` 中编写断言：
```python
def test_modal_dual_pane_and_five_elements_structure():
    content = Path("deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx").read_text(encoding="utf-8")
    assert "已开始" in content
    assert "执行的命令::" in content
    assert "验证结论" in content
    assert "已完成" in content
    assert "bash" in content
```

**Step 2: 运行测试验证失败**
Run: `pytest tests/deploy/test_assistant_status_drawer.py -k "test_modal_dual_pane" -v`  
Expected: FAIL

**Step 3: 重构双栏弹窗组件布局**
- **顶部 Header**：左上角浅绿底深绿字药丸 `已完成`（运行中蓝色 `进行中`，失败红色 `执行失败`），大字号任务标题，右上角 `✕`；
- **左栏（步骤树）**：竖向时间轴线，首节点实心圆点 `已开始`，后续按真实动作时序排列，当前项深色背景高亮；
- **右栏（证据面板）**：
  1. 大标题 + 动作叙述；
  2. `执行的命令::` 语法高亮代码块（顶部带 `bash` 标签、复制与下载按钮）；
  3. 运行元数据（`· 退出码: 0, 耗时: 3841ms`，输出截取标记）；
  4. 代码内容卡片（行号标注 + 高亮代码块）或 grep 检索结果列表；
  5. 加粗「验证结论」小标题 + 自然语言评估段落。

**Step 4: 同步补丁并运行测试**
Run: `python scripts/patch_lobehub.py && pytest tests/deploy/test_assistant_status_drawer.py -v`  
Expected: PASS

**Step 5: 提交代码**
```bash
git add deploy/lobehub/patches/ui/AssistantStatusDrawer.tsx tests/deploy/test_assistant_status_drawer.py
git commit -m "feat(ui): align task detail modal with Muse dual-pane and 5-element evidence view"
```

---

### Task 5: 全链路不变量集成验收与 Pre-Push 门禁体检

**Files:**
- Create: `tests/scenario/test_muse_activity_invariants.py`
- Modify: `docs/plans/task.md`
- Does NOT own: 任何超出任务范围的代码 (AP-01)
- Invariants to test: 全量 INV-01 至 INV-06 100% 覆盖通过

**Step 1: 编写全量不变量测试套件**
创建 `tests/scenario/test_muse_activity_invariants.py`，完整覆盖：
- INV-01：动态意图绝无死板英文；
- INV-02：证据数据 100% 溯源自底层真实记录；
- INV-03：抽屉条目 0 技术徽标；
- INV-04：左侧步骤树首含“已开始”且拓扑连贯；
- INV-05：右侧证据 5 要素模型完整；
- INV-06：只读观测隔离，底层事实与状态零变更。

**Step 2: 运行全量关联测试**
Run:
```bash
pytest tests/contracts/models/observability/test_activity_contract.py tests/deploy/test_assistant_status_drawer.py tests/scenario/test_muse_activity_invariants.py -v
```
Expected: PASS (所有测试全绿)

**Step 3: 运行代码门禁与格式校验**
Run:
```bash
ruff check --fix
ruff format
python scripts/check_patch_integrity.py
git diff --check
```
Expected: 0 报错，退出码 0

**Step 4: 提交代码并更新 task.md**
```bash
git add tests/scenario/test_muse_activity_invariants.py docs/plans/task.md
git commit -m "test(scenario): add comprehensive invariant suite for Muse activity feed alignment"
```
