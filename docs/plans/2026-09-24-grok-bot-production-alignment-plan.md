# Grok Bot (Sand 架构) 全面生产级可用实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 全面补齐 Grok Bot（Sand 架构）生产级可用性的四大支柱能力（P0 声带流式截流与气泡交付、P1 员工机安全容器沙箱、P2 浏览器自动化与单屏互斥锁、P3 后台例程引擎与消费护栏），彻底消除虚假闭环，使 LCA 的 Grok 模式达到真实可用标准。

**Architecture:** 严格遵循 LCA 单向分层架构（`contracts → infrastructure → cognition → runtime → agent`）与 ADR-0195 SSOT 契约。在已有五相认知拓扑（Think/Gate/Act/Reflect/Remember）零侵入的前提下，通过流式钩子截流散文、标准 Tool 多态分发交付正式气泡与沙箱命令、主循环状态机停等支持 Widget 选项卡、异步调度器驱动后台意图例程。

**Tech Stack:** Python 3.11, Pydantic v2 (frozen+extra="forbid"), Playwright (无头浏览器自动化), OnlyBoxes / Docker (安全隔离容器), Starlette, Asyncio, Pytest.

---

### Task 1: 契约模型层健全（Routine, Browser, Widget & Secret Models）

**Files:**
- Create: `lca/contracts/models/routine/models.py`
- Create: `lca/contracts/models/browser/models.py`
- Modify: `lca/contracts/models/vocal/models.py`
- Test: `tests/contracts/routine/test_routine_models.py`
- Test: `tests/contracts/browser/test_browser_models.py`
- Does NOT own: 任何基础设施实现、命令执行或主循环代码（AP-01）
- Invariants to test: 模型必须不可变（`frozen=True`）、严禁多余字段（`extra="forbid"`）、字段边界合法性校验（AP-02）

**Step 1: 编写失败测试**
```python
# tests/contracts/routine/test_routine_models.py
import pytest
from pydantic import ValidationError
from lca.contracts.models.routine.models import RoutineSpec

def test_routine_spec_frozen_and_valid():
    spec = RoutineSpec(
        id="rt_check_build",
        name="检查构建日志",
        cron_expr="0 * * * *",
        prompt="检查过去一小时的构建日志，仅在发现错误时汇报",
        spend_budget_per_run=10,
        daily_budget_tokens=50_000,
        assistant_id="asst_dev",
    )
    assert spec.id == "rt_check_build"
    with pytest.raises(ValidationError):
        spec.name = "修改名称"  # frozen 校验
    with pytest.raises(ValidationError):
        RoutineSpec(id="1", name="a", prompt="b", assistant_id="c", extra_key="forbidden")
```

**Step 2: 运行测试验证失败**
Run: `.venv/bin/pytest tests/contracts/routine/test_routine_models.py`
Expected: FAIL（ModuleNotFoundError: No module named 'lca.contracts.models.routine'）

**Step 3: 编写契约模型实现**
在 `lca/contracts/models/routine/models.py` 中定义 `RoutineSpec`、`SpendBudget`；在 `lca/contracts/models/browser/models.py` 中定义 `BrowserAction`、`BrowserActionResult`；在 `vocal/models.py` 中健全相关载荷。

**Step 4: 运行测试验证通过**
Run: `.venv/bin/pytest tests/contracts/routine/ tests/contracts/browser/`
Expected: PASS

**Step 5: 提交**
```bash
git add lca/contracts/models/ tests/contracts/
git commit -m "feat(contracts): add routine and browser domain models per ADR-0248"
```

---

### Task 2: P0 认知流截流与声带气泡真实交付（Streaming Interception & Bubble Delivery）

**Files:**
- Modify: `lca/plugins/primitive/llm_call/invoke.py`
- Modify: `lca/plugins/events/hooks/model_visible/adapter.py`
- Modify: `lca/infrastructure/vocal/tool_adapter.py`
- Modify: `lca/runtime/projection/result_projection.py`
- Test: `tests/infrastructure/vocal/test_streaming_interception_and_delivery.py`
- Does NOT own: 外部前端 UI 渲染、Docker 容器通信（AP-01）
- Invariants to test: INV-01（gated 模式散文 100% 截流进 scratchpad，事件流无可见 text_delta）、INV-02（send_message 正式写入 Session 事实并回填 TerminalOutcome）（AP-02）

**Step 1: 编写失败测试**
```python
# tests/infrastructure/vocal/test_streaming_interception_and_delivery.py
import pytest
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.tool_adapter import SendMessageVocalTool

@pytest.mark.asyncio
async def test_gated_streaming_interception_and_delivery():
    gate = GatedVocalGate(operation_id="op_test")
    # 验证流式文本被截流
    gate.handle_text_chunk("模型思考过程：准备调用工具...")
    assert len(gate.get_visible_outputs()) == 0
    assert "模型思考过程" in gate.get_scratchpad()
    
    # 验证 send_message 真实产出正式交付
    tool = SendMessageVocalTool(gate)
    obs = await tool.execute({"content": "这是正式气泡内容", "type": "text"})
    assert obs.success is True
    assert len(gate.get_visible_outputs()) == 1
    assert gate.get_visible_outputs()[0]["content"] == "这是正式气泡内容"
```

**Step 2: 运行测试验证**
Run: `.venv/bin/pytest tests/infrastructure/vocal/test_streaming_interception_and_delivery.py`

**Step 3: 最小实现**
在 LLM Streaming 适配器中挂载 `gate.handle_text_chunk` 并在 gated 模式抑制对外发射可见 `text_delta`；在 `SendMessageVocalTool` 中将正式消息写入 `Session.append` 并打入 `TerminalOutcome.text_ref`。

**Step 4: 运行测试验证通过**
Run: `.venv/bin/pytest tests/infrastructure/vocal/test_streaming_interception_and_delivery.py`
Expected: PASS

**Step 5: 提交**
```bash
git add lca/plugins/primitive/llm_call/ lca/infrastructure/vocal/ lca/runtime/projection/ tests/infrastructure/vocal/
git commit -m "feat(vocal): wire real monologue interception and bubble delivery"
```

---

### Task 3: P0 Widget 停等状态机与前端选项卡闭环（Widget Stop-and-Wait）

**Files:**
- Modify: `lca/runtime/loop/runtime_loop.py`
- Modify: `lca/infrastructure/vocal/gate.py`
- Create: `deploy/lobehub/patches/ui/widget_card.py`
- Test: `tests/runtime/test_widget_stop_and_wait.py`
- Does NOT own: 员工机文件操作、浏览器驱动（AP-01）
- Invariants to test: INV-03（widget 触发 WAITING_INPUT 挂起，同轮二次发声报错阻断，提交 answer 顺畅恢复）（AP-02）

**Step 1: 编写失败测试**
```python
# tests/runtime/test_widget_stop_and_wait.py
import pytest
from lca.contracts.models.vocal.models import VocalMessageType
from lca.infrastructure.vocal.gate import GatedVocalGate
from lca.infrastructure.vocal.exceptions import VocalGateAlreadyBlockedError

def test_widget_stops_turn_and_blocks_second_message():
    gate = GatedVocalGate(operation_id="op_w")
    from lca.infrastructure.vocal.tool import SendMessageTool
    tool = SendMessageTool(gate)
    res = tool.execute(type="widget", options=[{"id": "opt1", "label": "选项一"}])
    assert res["is_terminal_for_turn"] is True
    assert gate.is_awaiting_widget() is True
    
    # 同轮严禁二次发声
    with pytest.raises(VocalGateAlreadyBlockedError):
        tool.execute(type="text", content="多余的一句话")
```

**Step 2: 运行测试验证**
Run: `.venv/bin/pytest tests/runtime/test_widget_stop_and_wait.py`

**Step 3: 最小实现**
在 `runtime_loop.py` 捕获 `gate.is_awaiting_widget()`，接入 `intervene.interrupt` 挂起状态为 `waiting_input`；落地 LobeHub 前端补丁 `widget_card.py` 支持渲染选项卡并调用 `/answer`。

**Step 4: 运行测试验证通过**
Run: `.venv/bin/pytest tests/runtime/test_widget_stop_and_wait.py`
Expected: PASS

**Step 5: 提交**
```bash
git add lca/runtime/loop/ lca/infrastructure/vocal/ deploy/lobehub/patches/ tests/runtime/
git commit -m "feat(runtime): implement widget stop-and-wait and resume flow"
```

---

### Task 4: P1 员工机安全容器沙箱化（BoxExecutionPort & Sandbox Adapter）

**Files:**
- Create: `lca/infrastructure/computer/box_port.py`
- Create: `lca/infrastructure/computer/box_sandbox_adapter.py`
- Modify: `lca/infrastructure/tools/box/tool.py`
- Test: `tests/infrastructure/computer/test_box_sandbox_adapter.py`
- Does NOT own: 用户电脑（ADR-0246 LocalExec）、浏览器子代理（AP-01）
- Invariants to test: INV-04（沙箱文件读写与命令执行严格隔离，非 root 用户，越界抛 PermissionError）（AP-02）

**Step 1: 编写失败测试**
```python
# tests/infrastructure/computer/test_box_sandbox_adapter.py
import pytest
from lca.infrastructure.computer.box_sandbox_adapter import LocalBoxAdapter

@pytest.mark.asyncio
async def test_box_adapter_isolation_and_containment(tmp_path):
    adapter = LocalBoxAdapter(root_dir=tmp_path / "box")
    await adapter.write_file("test.txt", "hello sandbox")
    content = await adapter.read_file("test.txt")
    assert content == "hello sandbox"
    
    with pytest.raises(PermissionError):
        await adapter.read_file("../../etc/passwd")
```

**Step 2: 运行测试验证**
Run: `.venv/bin/pytest tests/infrastructure/computer/test_box_sandbox_adapter.py`

**Step 3: 最小实现**
定义 `BoxExecutionPort` 协议；实现 `OnlyboxesBoxAdapter`（容器化）与 `LocalBoxAdapter`（受限回退）；重构 `BoxRunCommandTool` 与 `BoxReadFileTool` 对接该协议，消除裸 `subprocess.run` 风险。

**Step 4: 运行测试验证通过**
Run: `.venv/bin/pytest tests/infrastructure/computer/test_box_sandbox_adapter.py`
Expected: PASS

**Step 5: 提交**
```bash
git add lca/infrastructure/computer/ lca/infrastructure/tools/box/ tests/infrastructure/computer/
git commit -m "feat(box): implement BoxExecutionPort and isolated sandbox adapter"
```

---

### Task 5: P2 浏览器控制与单屏互斥锁（Browser Subagent & Desktop Lock）

**Files:**
- Create: `lca/infrastructure/computer/desktop_lock.py`
- Create: `lca/infrastructure/browser/subagent.py`
- Create: `lca/infrastructure/tools/browser/tools.py`
- Test: `tests/infrastructure/computer/test_desktop_lock.py`
- Test: `tests/infrastructure/browser/test_browser_subagent.py`
- Does NOT own: 例程调度、核心认知五相图结构（AP-01）
- Invariants to test: INV-05（子代理工具集物理剔除 send_message）、INV-06（单屏互斥与 120s TTL 超时防死锁）（AP-02）

**Step 1: 编写失败测试**
```python
# tests/infrastructure/computer/test_desktop_lock.py
import pytest
from lca.infrastructure.computer.desktop_lock import DesktopLockManager

@pytest.mark.asyncio
async def test_desktop_lock_mutual_exclusion_and_ttl():
    lock_mgr = DesktopLockManager(default_ttl_s=1)
    acquired = await lock_mgr.allocate_window(agent_id="sub_1", session_id="s1")
    assert acquired is True
    
    # 并发争夺被拒
    acquired_2 = await lock_mgr.allocate_window(agent_id="sub_2", session_id="s1")
    assert acquired_2 is False
    
    await lock_mgr.free_window(agent_id="sub_1", session_id="s1")
    assert await lock_mgr.allocate_window(agent_id="sub_2", session_id="s1") is True
```

**Step 2: 运行测试验证**
Run: `.venv/bin/pytest tests/infrastructure/computer/test_desktop_lock.py`

**Step 3: 最小实现**
实现 `DesktopLockManager`；基于 Playwright 封装 `BrowserSubagent` 与原语工具；在工具装配期由 `VocalToolFilter` 严格禁声。

**Step 4: 运行测试验证通过**
Run: `.venv/bin/pytest tests/infrastructure/computer/test_desktop_lock.py tests/infrastructure/browser/test_browser_subagent.py`
Expected: PASS

**Step 5: 提交**
```bash
git add lca/infrastructure/computer/ lca/infrastructure/browser/ lca/infrastructure/tools/browser/ tests/
git commit -m "feat(browser): add DesktopLockManager and browser subagent tools"
```

---

### Task 6: P3 声明式例程引擎与消费护栏（Routine Repository, Scheduler & Spend Guard）

**Files:**
- Create: `lca/domain/routine/repository.py`
- Create: `lca/application/routine/spend_guard.py`
- Create: `lca/application/routine/scheduler.py`
- Test: `tests/application/routine/test_routine_scheduler_and_spend_guard.py`
- Does NOT own: 前端 UI 补丁、浏览器自动化（AP-01）
- Invariants to test: INV-07（例程合法沉默放行且 0 垃圾通知）、INV-08（Token 超预算立即熔断暂停）（AP-02）

**Step 1: 编写失败测试**
```python
# tests/application/routine/test_routine_scheduler_and_spend_guard.py
import pytest
from lca.application.routine.spend_guard import SpendGuard
from lca.contracts.models.routine.models import RoutineSpec

def test_spend_guard_daily_budget_enforcement():
    guard = SpendGuard()
    spec = RoutineSpec(
        id="rt_1", name="test", prompt="test", assistant_id="a1", daily_budget_tokens=1000
    )
    guard.record_consumption("rt_1", tokens_used=800)
    assert guard.is_budget_exceeded(spec) is False
    
    guard.record_consumption("rt_1", tokens_used=300)
    assert guard.is_budget_exceeded(spec) is True  # 超限触发熔断
```

**Step 2: 运行测试验证**
Run: `.venv/bin/pytest tests/application/routine/test_routine_scheduler_and_spend_guard.py`

**Step 3: 最小实现**
落地 `JsonRoutineRepository` 持久化；落地 `SpendGuard` 熔断器；实现 `RoutineSchedulerService` 异步调度轮询服务。

**Step 4: 运行测试验证通过**
Run: `.venv/bin/pytest tests/application/routine/test_routine_scheduler_and_spend_guard.py`
Expected: PASS

**Step 5: 提交**
```bash
git add lca/domain/routine/ lca/application/routine/ tests/application/routine/
git commit -m "feat(routine): add routine repository, scheduler, and spend guard"
```

---

### Task 7: 全链路集成场景与架构门禁回归（Closed-Loop E2E & Pre-push Guards）

**Files:**
- Create: `tests/scenario/adr0248/test_grok_bot_production_closed_loop.py`
- Modify: `docs/plans/task.md`
- Test: 全量测试套件
- Does NOT own: 违背负向清单修改任何其他外部模块（AP-01）
- Invariants to test: INV-01 ~ INV-09 全不变量自动化串联通过

**Step 1: 编写全链路端到端闭环测试**
编写 `test_grok_bot_production_closed_loop.py`，串联：
1. 真实流式截流进 `scratchpad`；
2. 员工机安全容器执行命令；
3. 浏览器子代理获取信息并释放屏幕锁；
4. 调用 `send_message(content=...)` 交付气泡；
5. Settle 结算收敛；
6. 后台 Routine 定时触发并在无新事时合规沉默。

**Step 2: 运行全量关联测试**
Run: `.venv/bin/pytest tests/scenario/adr0248/ tests/infrastructure/vocal/ tests/infrastructure/computer/ tests/infrastructure/browser/ tests/application/routine/ tests/contracts/routine/ tests/contracts/browser/ -v`
Expected: 100% PASS

**Step 3: 执行全套代码工程规范检查**
```bash
ruff check --fix
ruff format
git diff --check
```

**Step 4: 更新进度并提交**
```bash
git add tests/ docs/plans/task.md
git commit -m "test(adr0248): add comprehensive grok-bot production closed-loop tests"
```
