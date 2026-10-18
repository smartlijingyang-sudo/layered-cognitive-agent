# 决策大脑与场景执行彻底解耦实施计划 (Implementation Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 全量废除旧版静态轮盘（`roulette.py`）与 78KB 面条脚本（`scenarios.py`），落地工业级四层解耦拟真自动化架构（生理节律层、马尔可夫效用决策大脑、微内核场景插件、反检测拟真执行底座），配备零 DOM 污染透明 HUD 大盘与确定性回放调试能力。

**Architecture:** 严格采用微内核插件与黑板解耦架构（方案 A）。生理节律与执行底座仅通过强类型 `SessionBlackboard` 与异步事件总线反哺；决策大脑实现二阶马尔可夫转移矩阵与动态效用修饰（绝无浏览器代码）；场景编排层实现微内核 `SceneSkill` 插件协议；物理执行底座强制拦截 `page.goto` 并通过 CDP 旁路流向前端双屏大盘。

**Tech Stack:** Python 3.11, Pydantic V2 (frozen models), Pytest, Playwright / Camoufox, FastAPI WebSocket, React / Tailwind CSS (零 DOM 污染透明 SVG HUD).

---

### Task 1: [黑板与事件总线] 强类型 SessionBlackboard 与异步事件模型 (Blackboard & Events)

**Files:**
- Create: `/home/lichao/tools/x-operator/x_operator/scheduler/blackboard.py`
- Create: `/home/lichao/tools/x-operator/x_operator/scheduler/events.py`
- Test: `/home/lichao/tools/x-operator/tests/scheduler/test_blackboard_and_events.py`
- Does NOT own: 任何浏览器操作、数据库主表、LCA 内核资产 (AP-01)
- Invariants to test: `INV-DECIDE-01` 状态不可变性与快照序列化；事件订阅与投影幂等 (AP-02)

**Step 1: 编写测试断言**
```python
# tests/scheduler/test_blackboard_and_events.py
from x_operator.scheduler.blackboard import SessionBlackboard, BlackboardSnapshot
from x_operator.scheduler.events import EventBus, RiskSignalEvent, BadgeStimulusEvent

def test_blackboard_initial_state_and_snapshot():
    bb = SessionBlackboard()
    snap = bb.snapshot()
    assert isinstance(snap, BlackboardSnapshot)
    assert snap.fatigue_level == 0.0
    assert snap.unfollow_cooldown_active is False
    assert snap.badge_notifications == 0

def test_event_bus_risk_signal_mutates_blackboard():
    bb = SessionBlackboard()
    bus = EventBus()
    bus.subscribe(RiskSignalEvent, bb.handle_risk_signal)
    bus.publish(RiskSignalEvent(status_code=429, reason="Too Many Requests"))
    assert bb.risk_signal_active is True
```

**Step 2: 运行单测验证失败**
Run: `pytest /home/lichao/tools/x-operator/tests/scheduler/test_blackboard_and_events.py -v`
Expected: FAIL (ModuleNotFoundError: x_operator.scheduler.blackboard)

**Step 3: 编写核心实现代码**
在 `blackboard.py` 中定义 Pydantic V2 强类型不可变模型 `BlackboardSnapshot` 与线程安全黑板 `SessionBlackboard`；在 `events.py` 中实现异步轻量事件总线 `EventBus`。

**Step 4: 运行单测验证通过**
Run: `pytest /home/lichao/tools/x-operator/tests/scheduler/test_blackboard_and_events.py -v`
Expected: PASS (All tests passed)

**Step 5: Git 提交**
```bash
git -C /home/lichao/tools/x-operator add x_operator/scheduler/blackboard.py x_operator/scheduler/events.py tests/scheduler/test_blackboard_and_events.py
git -C /home/lichao/tools/x-operator commit -m "feat(scheduler): implement SessionBlackboard and EventBus contracts (DECOUPLE-TASK-1)"
```

---

### Task 2: [决策调度层] 纯数学二阶马尔可夫与效用修正大脑 (StochasticDecisionBrain)

**Files:**
- Create: `/home/lichao/tools/x-operator/x_operator/scheduler/stochastic_brain.py`
- Test: `/home/lichao/tools/x-operator/tests/scheduler/test_stochastic_brain.py`
- Does NOT own: 任何 Playwright / DOM / 页面交互对象、旧版 roulette.py (AP-01)
- Invariants to test: `INV-DECIDE-01` 概率归一化恒等于 1.0; `INV-DECIDE-02` 红点 3.5x 放大; `INV-DECIDE-03` 取关冷却锁强制置 0; `INV-DECIDE-04` 重度疲劳写操作抑制; 8% 分心中断抽样 (AP-02)

**Step 1: 编写测试断言**
```python
# tests/scheduler/test_stochastic_brain.py
import pytest
from x_operator.scheduler.stochastic_brain import StochasticDecisionBrain, ScenarioID
from x_operator.scheduler.blackboard import SessionBlackboard

def test_inv_decide_01_probability_sum_normalized():
    brain = StochasticDecisionBrain()
    bb = SessionBlackboard()
    for state in ScenarioID:
        probs = brain.calculate_probabilities(state, bb.snapshot())
        assert abs(sum(probs.values()) - 1.0) < 1e-6
        assert all(p >= 0.0 for p in probs.values())

def test_inv_decide_02_badge_stimulus_multiplication():
    brain = StochasticDecisionBrain()
    bb = SessionBlackboard(badge_notifications=3)
    probs_normal = brain.calculate_probabilities(ScenarioID.FOR_YOU, SessionBlackboard().snapshot())
    probs_badge = brain.calculate_probabilities(ScenarioID.FOR_YOU, bb.snapshot())
    assert probs_badge[ScenarioID.NOTIFY] >= probs_normal[ScenarioID.NOTIFY] * 2.5

def test_inv_decide_03_cooldown_gate_zeroes_out():
    brain = StochasticDecisionBrain()
    bb = SessionBlackboard(unfollow_cooldown_active=True)
    probs = brain.calculate_probabilities(ScenarioID.FOR_YOU, bb.snapshot())
    assert probs[ScenarioID.GRAPH_MANAGE] == 0.0
```

**Step 2: 运行单测验证失败**
Run: `pytest /home/lichao/tools/x-operator/tests/scheduler/test_stochastic_brain.py -v`
Expected: FAIL

**Step 3: 编写核心实现代码**
在 `stochastic_brain.py` 中落地 `BaseMatrix`、链式 `UtilityModifiers`、`sample_lognormal_duration()`（对数正态时长）与 `check_attention_interrupt()`（8% 中断判定）。

**Step 4: 运行单测验证通过**
Run: `pytest /home/lichao/tools/x-operator/tests/scheduler/test_stochastic_brain.py -v`
Expected: PASS (All tests passed)

**Step 5: Git 提交**
```bash
git -C /home/lichao/tools/x-operator add x_operator/scheduler/stochastic_brain.py tests/scheduler/test_stochastic_brain.py
git -C /home/lichao/tools/x-operator commit -m "feat(scheduler): implement StochasticDecisionBrain with Markov and Utility AI (DECOUPLE-TASK-2)"
```

---

### Task 3: [微内核场景编排] 场景插件统一契约与 5 大单文件插件 (SceneSkillRegistry & Plugins)

**Files:**
- Create: `/home/lichao/tools/x-operator/x_operator/scheduler/scenes/base.py`
- Create: `/home/lichao/tools/x-operator/x_operator/scheduler/scenes/for_you.py`
- Create: `/home/lichao/tools/x-operator/x_operator/scheduler/scenes/search_interact.py`
- Create: `/home/lichao/tools/x-operator/x_operator/scheduler/scenes/notify.py`
- Create: `/home/lichao/tools/x-operator/x_operator/scheduler/scenes/graph_manage.py`
- Create: `/home/lichao/tools/x-operator/x_operator/scheduler/scenes/rest_idle.py`
- Create: `/home/lichao/tools/x-operator/x_operator/scheduler/scene_registry.py`
- Test: `/home/lichao/tools/x-operator/tests/scheduler/test_scene_skills_registry.py`
- Does NOT own: 浏览器 C++ 驱动、数据库连接 (AP-01)
- Invariants to test: 场景统一微内核协议（`can_run`, `execute`, `interrupt`）；插件间 0 直接 import (AP-02)

**Step 1: 编写测试断言**
```python
# tests/scheduler/test_scene_skills_registry.py
from x_operator.scheduler.scene_registry import SceneSkillRegistry
from x_operator.scheduler.stochastic_brain import ScenarioID
from x_operator.scheduler.blackboard import SessionBlackboard

def test_registry_registers_all_five_core_scenes():
    registry = SceneSkillRegistry.build_default()
    assert len(registry.list_skills()) == 5
    for sid in ScenarioID:
        skill = registry.get_skill(sid)
        assert skill is not None
        assert hasattr(skill, "can_run")
        assert hasattr(skill, "execute")
        assert hasattr(skill, "interrupt")
```

**Step 2: 运行单测验证失败**
Run: `pytest /home/lichao/tools/x-operator/tests/scheduler/test_scene_skills_registry.py -v`
Expected: FAIL

**Step 3: 编写核心实现代码**
在 `scenes/base.py` 固化 `SceneSkill` 抽象协议；分别落地 5 个高内聚单文件场景插件；在 `scene_registry.py` 建立即插即用注册表。

**Step 4: 运行单测验证通过**
Run: `pytest /home/lichao/tools/x-operator/tests/scheduler/test_scene_skills_registry.py -v`
Expected: PASS (All tests passed)

**Step 5: Git 提交**
```bash
git -C /home/lichao/tools/x-operator add x_operator/scheduler/scenes/ x_operator/scheduler/scene_registry.py tests/scheduler/test_scene_skills_registry.py
git -C /home/lichao/tools/x-operator commit -m "feat(scheduler): implement microkernel SceneSkillRegistry and 5 core scene plugins (DECOUPLE-TASK-3)"
```

---

### Task 4: [物理执行层与铁律收敛] StealthActuator 拟真底座与 NavigationRouter (StealthActuator)

**Files:**
- Create: `/home/lichao/tools/x-operator/x_operator/browser/navigation_router.py`
- Create: `/home/lichao/tools/x-operator/x_operator/browser/actuator.py`
- Test: `/home/lichao/tools/x-operator/tests/browser/test_stealth_actuator_and_router.py`
- Does NOT own: 决策算法、业务逻辑 (AP-01)
- Invariants to test: `INV-ACT-01` 零 page.goto 哨兵拦截（除启动外禁止直接 goto）；`INV-ACT-02` 贝塞尔加速度连续与截断 2D 高斯落点 (AP-02)

**Step 1: 编写测试断言**
```python
# tests/browser/test_stealth_actuator_and_router.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from x_operator.browser.navigation_router import NavigationRouter, ForbiddenPageGotoError
from x_operator.browser.actuator import StealthActuator

@pytest.mark.asyncio
async def test_inv_act_01_forbid_raw_page_goto():
    mock_page = MagicMock()
    mock_page.goto = AsyncMock()
    router = NavigationRouter(mock_page)
    # 模拟非法调用 goto
    with pytest.raises(ForbiddenPageGotoError):
        await router.enforce_no_page_goto("https://x.com/notifications")
```

**Step 2: 运行单测验证失败**
Run: `pytest /home/lichao/tools/x-operator/tests/browser/test_stealth_actuator_and_router.py -v`
Expected: FAIL

**Step 3: 编写核心实现代码**
在 `navigation_router.py` 中实现 SPA 原生点击路由与 `page.goto` 哨兵拦截；在 `actuator.py` 中封装 `StealthActuator`，集成 WindMouse 贝塞尔动力学、2D 高斯落点与键盘错字纠错引擎。

**Step 4: 运行单测验证通过**
Run: `pytest /home/lichao/tools/x-operator/tests/browser/test_stealth_actuator_and_router.py -v`
Expected: PASS (All tests passed)

**Step 5: Git 提交**
```bash
git -C /home/lichao/tools/x-operator add x_operator/browser/navigation_router.py x_operator/browser/actuator.py tests/browser/test_stealth_actuator_and_router.py
git -C /home/lichao/tools/x-operator commit -m "feat(browser): implement StealthActuator and NavigationRouter with zero-goto guard (DECOUPLE-TASK-4)"
```

---

### Task 5: [全量替换与旁路自愈] 彻底切除旧版 scenarios.py/roulette.py，组装生产 Pilot (Pilot Assembly)

**Files:**
- Modify: `/home/lichao/tools/x-operator/x_operator/scheduler/pilot.py`
- Deprecate/Remove: `/home/lichao/tools/x-operator/x_operator/scheduler/roulette.py` 与 `scenarios.py`
- Add CLI: `/home/lichao/tools/x-operator/x_operator/cli.py` 增加 `pilot replay-decision` 命令
- Test: `/home/lichao/tools/x-operator/tests/scheduler/test_pilot_decoupled_orchestration.py`
- Does NOT own: 数据库 schema、前端页面 (AP-01)
- Invariants to test: `INV-RISK-01` 429 毫秒级自愈熔断；确定性离线回放 (AP-02)

**Step 1: 编写测试断言**
```python
# tests/scheduler/test_pilot_decoupled_orchestration.py
import pytest
from x_operator.scheduler.pilot import MultiScenarioPilot

@pytest.mark.asyncio
async def test_inv_risk_01_pilot_reacts_to_429_immediately():
    pilot = MultiScenarioPilot.build_isolated_test_instance()
    # 模拟接收到 429 事件
    pilot.event_bus.publish_risk_429()
    # 断言黑板与大脑写操作立即归零
    decision = pilot.brain.decide_next_scene(pilot.blackboard.snapshot())
    assert decision.target_scene == ScenarioID.REST_IDLE
```

**Step 2: 运行单测验证失败**
Run: `pytest /home/lichao/tools/x-operator/tests/scheduler/test_pilot_decoupled_orchestration.py -v`
Expected: FAIL

**Step 3: 编写核心实现代码**
在 `pilot.py` 中切除 `ActionRoulette` 与 `scenarios.py`，完整装配 `SessionBlackboard`、`StochasticDecisionBrain`、`SceneSkillRegistry` 与 `StealthActuator`；在 CLI 增加 `replay-decision`。

**Step 4: 运行单测验证通过**
Run: `pytest /home/lichao/tools/x-operator/tests/scheduler/test_pilot_decoupled_orchestration.py -v`
Expected: PASS (All tests passed)

**Step 5: Git 提交**
```bash
git -C /home/lichao/tools/x-operator add x_operator/scheduler/pilot.py x_operator/cli.py tests/scheduler/test_pilot_decoupled_orchestration.py
git -C /home/lichao/tools/x-operator commit -m "feat(scheduler): wire decoupled 4-layer engine into production Pilot and deprecate legacy scenarios (DECOUPLE-TASK-5)"
```

---

### Task 6: [可视化监控与全链路门禁] FastAPI 实时双屏 WebSocket 与前端大盘集成 (Telemetry & HUD)

**Files:**
- Create: `/home/lichao/tools/x-operator/x_operator/web/router_telemetry.py`
- Modify: `/home/lichao/tools/x-operator/x_operator/web/app.py`
- Modify: `/home/lichao/tools/x-operator/frontend/src/` (挂载实时双屏大盘到 Web 控制台)
- Test: `/home/lichao/tools/x-operator/tests/web/test_telemetry_stream.py`
- Does NOT own: LCA 框架仓库、宿主机非相关服务 (AP-01)
- Invariants to test: WebSocket 遥测帧推流结构；INV-01 至 INV-07 全量回归通过 (AP-02)

**Step 1: 编写测试断言**
```python
# tests/web/test_telemetry_stream.py
from fastapi.testclient import TestClient
from x_operator.web.app import create_app

def test_telemetry_websocket_broadcasts_brain_frame():
    app = create_app()
    client = TestClient(app)
    with client.websocket_connect("/api/telemetry/ws?token=lc123") as websocket:
        data = websocket.receive_json()
        assert "brain_state" in data
        assert "transition_matrix" in data["brain_state"]
```

**Step 2: 运行单测验证失败**
Run: `pytest /home/lichao/tools/x-operator/tests/web/test_telemetry_stream.py -v`
Expected: FAIL

**Step 3: 编写核心实现代码**
在 `router_telemetry.py` 实现 WebSocket 广播端点；在前端将沙盘升级为常驻生产大盘组件；验证零 DOM 污染透明 SVG 轨迹叠加层。

**Step 4: 运行单测验证通过**
Run: `pytest /home/lichao/tools/x-operator/tests/web/test_telemetry_stream.py -v`
Expected: PASS (All tests passed)

**Step 5: Git 提交与全量回归**
```bash
git -C /home/lichao/tools/x-operator add x_operator/web/router_telemetry.py x_operator/web/app.py frontend/ tests/web/test_telemetry_stream.py
git -C /home/lichao/tools/x-operator commit -m "feat(web): provide dual-screen telemetry WebSocket and integrate production HUD (DECOUPLE-TASK-6)"
```
