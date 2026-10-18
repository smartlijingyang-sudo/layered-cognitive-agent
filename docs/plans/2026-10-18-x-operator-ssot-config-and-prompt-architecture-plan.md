# X-Operator SSOT 配置化、Prompt 模块化与机制透视中枢实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 彻底消除 x-operator 内部 Prompt 与策略硬编码，在后端建立强类型单写 SSOT 与零重启热生效广播，在 Web 前端打造顶级「SSOT 配置与机制透视中枢（Mechanism Studio）」，实现 6 大板块动态热编辑与内部运行机制同屏可视化解密。

**Architecture:** 采用分层领域驱动架构（DDD Layered SSOT & Reactive Mechanism Studio）。后端通过 Pydantic V2 严格定义 6 大子领域不可变契约，采用文件原子写入锁 + 历史快照保证单写一致性，通过内存事件总线向认知流水线、调度器与审评委员会广播热重载事件；前端基于 2026 Bento-grid 风格打造左轨交互编辑 + 右轨机制透视与 Live 拼装预览的双轨工作台。

**Tech Stack:** Python 3.12, FastAPI, Pydantic V2, Pytest, React 18, TypeScript, Tailwind CSS, Lucide React, Vite.

---

### Task 1: SSOT 领域契约与原子持久化单写锁强化

**Files:**
- Modify: `/home/lichao/tools/x-operator/x_operator/growth_config.py`
- Modify: `/home/lichao/tools/x-operator/x_operator/web/router_trace.py`
- Test: `/home/lichao/tools/x-operator/tests/test_growth_config_ssot.py`
- Does NOT own: `/home/lichao/tools/x-operator/x_operator/browser/`, `/home/lichao/layered-cognitive-agent/` (AP-01)
- Invariants to test: INV-SSOT-01 (单写 SSOT), INV-SSOT-02 (数值物理区间边界), INV-SSOT-05 (历史快照归档) (AP-02)

**Step 1: Write the failing test**

```python
# tests/test_growth_config_ssot.py
import pytest
from pathlib import Path
from x_operator.growth_config import load_growth_config, save_growth_config

def test_atomic_save_and_history_snapshot(tmp_path):
    cfg_file = tmp_path / "growth_config.json"
    hist_dir = tmp_path / "config_history"
    
    initial = load_growth_config(config_path=cfg_file)
    assert "account_profile" in initial
    assert "prompts" in initial
    
    # Update with strict bounds
    updated = save_growth_config(
        {
            "account_profile": {"display_name": "测试推友"},
            "comment_delay_min": 15.0,
            "comment_delay_max": 45.0,
            "critic_min_score": 88.0,
        },
        config_path=cfg_file,
        history_dir=hist_dir,
    )
    assert updated["account_profile"]["display_name"] == "测试推友"
    assert updated["comment_delay_min"] == 15.0
    
    # Assert snapshot exists in history_dir
    snapshots = list(hist_dir.glob("*.json"))
    assert len(snapshots) >= 1
```

**Step 2: Run test to verify it fails**

Run: `pytest /home/lichao/tools/x-operator/tests/test_growth_config_ssot.py -v`  
Expected: FAIL with `TypeError: save_growth_config() got an unexpected keyword argument 'history_dir'`

**Step 3: Write minimal implementation**

在 `growth_config.py` 中增加原子保存（临时文件写入后 `os.replace`）与快照自动生成逻辑，在 `router_trace.py` 中补全强类型校验门禁。

**Step 4: Run test to verify it passes**

Run: `pytest /home/lichao/tools/x-operator/tests/test_growth_config_ssot.py -v`  
Expected: PASS (100% 绿灯)

**Step 5: Commit**

```bash
git -C /home/lichao/tools/x-operator add x_operator/growth_config.py x_operator/web/router_trace.py tests/test_growth_config_ssot.py
git -C /home/lichao/tools/x-operator commit -m "feat(ssot): harden growth config with atomic write, bounds checking, and history snapshots"
```

---

### Task 2: 进程内响应式热重载与通知订阅机制

**Files:**
- Create: `/home/lichao/tools/x-operator/x_operator/config_events.py`
- Modify: `/home/lichao/tools/x-operator/x_operator/cognition/pipeline.py`
- Modify: `/home/lichao/tools/x-operator/x_operator/scheduler/pilot.py`
- Test: `/home/lichao/tools/x-operator/tests/test_ssot_hot_reload.py`
- Does NOT own: `/home/lichao/tools/x-operator/x_operator/browser/` (AP-01)
- Invariants to test: INV-SSOT-03 (零重启热生效铁律：修改 Prompt 后下次推演立即消费新提示词) (AP-02)

**Step 1: Write the failing test**

```python
# tests/test_ssot_hot_reload.py
import pytest
from x_operator.growth_config import save_growth_config
from x_operator.cognition.pipeline import CognitivePipeline

def test_pipeline_consumes_updated_prompt_immediately(tmp_path):
    cfg_file = tmp_path / "growth_config.json"
    save_growth_config(
        {"prompts": {"system_prompt_base": "【特异性测试标识999】你是在X冲浪的推友"}},
        config_path=cfg_file,
    )
    pipeline = CognitivePipeline()
    # Invalidate / reload through bus
    pipeline.reload_config(cfg_file)
    
    # Assert generated prompt carries the new identifier
    sys_prompt = pipeline._build_system_prompt_for_test(config_path=cfg_file)
    assert "【特异性测试标识999】" in sys_prompt
```

**Step 2: Run test to verify it fails**

Run: `pytest /home/lichao/tools/x-operator/tests/test_ssot_hot_reload.py -v`  
Expected: FAIL with `AttributeError: 'CognitivePipeline' object has no attribute 'reload_config'`

**Step 3: Write minimal implementation**

实现 `ConfigChangeBus`（单例订阅发布中心），在 `save_growth_config` 成功后派发事件，`CognitivePipeline` 与 `Pilot` 注册监听并在触发时清除内部配置缓存。

**Step 4: Run test to verify it passes**

Run: `pytest /home/lichao/tools/x-operator/tests/test_ssot_hot_reload.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git -C /home/lichao/tools/x-operator add x_operator/config_events.py x_operator/cognition/pipeline.py x_operator/scheduler/pilot.py tests/test_ssot_hot_reload.py
git -C /home/lichao/tools/x-operator commit -m "feat(ssot): implement in-process reactive hot-reload bus for cognitive pipeline"
```

---

### Task 3: 16-Soul 动态覆盖与隔离断言测试

**Files:**
- Modify: `/home/lichao/tools/x-operator/x_operator/curator/souls.py`
- Test: `/home/lichao/tools/x-operator/tests/test_souls_dynamic_matrix.py`
- Does NOT own: `/home/lichao/tools/x-operator/x_operator/storage/` (AP-01)
- Invariants to test: INV-SSOT-04 (16-Soul 独立覆盖与静态底座防污染) (AP-02)

**Step 1: Write the failing test**

```python
# tests/test_souls_dynamic_matrix.py
import pytest
from x_operator.curator.souls import SOUL_CATALOG, get_effective_soul_catalog, get_active_soul_ids

def test_soul_custom_prompt_and_toggle_isolation():
    override_cfg = {
        "souls_config": {
            "angry_wage_slave": {
                "enabled": True,
                "custom_prompt": "【自定义打工人Prompt】疯狂输出真实职场痛苦",
            },
            "cynical_observer": {
                "enabled": False,
            }
        }
    }
    effective = get_effective_soul_catalog(override_cfg)
    active_ids = get_active_soul_ids(override_cfg)
    
    assert effective["angry_wage_slave"].system_prompt_snippet == "【自定义打工人Prompt】疯狂输出真实职场痛苦"
    assert "cynical_observer" not in active_ids
    # Static catalog must NOT be mutated
    assert "【自定义打工人Prompt】" not in SOUL_CATALOG["angry_wage_slave"].system_prompt_snippet
```

**Step 2: Run test to verify it fails**

Run: `pytest /home/lichao/tools/x-operator/tests/test_souls_dynamic_matrix.py -v`  
Expected: FAIL or verify edge cases in immutability

**Step 3: Write minimal implementation**

强化 `souls.py` 中的 `get_effective_soul_catalog` 与 `get_active_soul_ids`，确保深拷贝（deep copy）返回，杜绝原地污染。

**Step 4: Run test to verify it passes**

Run: `pytest /home/lichao/tools/x-operator/tests/test_souls_dynamic_matrix.py -v`  
Expected: PASS

**Step 5: Commit**

```bash
git -C /home/lichao/tools/x-operator add x_operator/curator/souls.py tests/test_souls_dynamic_matrix.py
git -C /home/lichao/tools/x-operator commit -m "feat(souls): enforce immutable dynamic overrides and active filtering for 16-soul matrix"
```

---

### Task 4: 前端 Mechanism Studio 顶层视图与双轨布局组件

**Files:**
- Create: `/home/lichao/tools/x-operator/frontend/src/views/studio/MechanismStudioView.tsx`
- Create: `/home/lichao/tools/x-operator/frontend/src/views/studio/StudioConfigPanel.tsx`
- Create: `/home/lichao/tools/x-operator/frontend/src/views/studio/StudioMechanismInsight.tsx`
- Create: `/home/lichao/tools/x-operator/frontend/src/views/studio/types.ts`
- Modify: `/home/lichao/tools/x-operator/frontend/src/api/client.ts`
- Does NOT own: `/home/lichao/tools/x-operator/frontend/src/views/pipeline/` (AP-01)
- Invariants to test: INV-SSOT-06 (前端零 Mock 硬编码，100% 动态读取与回显) (AP-02)

**Step 1: Write the component specifications and types**

定义 6 大板块类别：`identity` | `prompt_pipeline` | `souls_matrix` | `prospecting_radar` | `circadian_kinetics` | `cognition_gates`，以及双轨数据传递规范。

**Step 2: Implement StudioConfigPanel**

提供 Monaco 风格文本编辑、Tag 池输入、高斯延迟双滑块与 16-Soul 象限卡片，支持实时受控状态。

**Step 3: Implement StudioMechanismInsight**

呈现「它在内部做什么」、「内部调用拓扑（五相循环节点与代码坐标）」、「实时 Prompt 组装预览（Live Interpolation）」与「硬编码治理对比卡片」。

**Step 4: Verify frontend builds without error**

Run: `npm --prefix /home/lichao/tools/x-operator/frontend run build`  
Expected: Vite build exits with 0.

**Step 5: Commit**

```bash
git -C /home/lichao/tools/x-operator add frontend/src/views/studio/ frontend/src/api/client.ts
git -C /home/lichao/tools/x-operator commit -m "feat(frontend): create 2026 double-track MechanismStudioView with live config and architecture insight"
```

---

### Task 5: 驾驶舱子 Tab 与导航无缝对接（重构 StrategyAndPromptsCard）

**Files:**
- Modify: `/home/lichao/tools/x-operator/frontend/src/components/layout/Header.tsx`
- Modify: `/home/lichao/tools/x-operator/frontend/src/App.tsx`
- Modify: `/home/lichao/tools/x-operator/frontend/src/views/cockpit/CognitiveCockpitView.tsx`
- Modify: `/home/lichao/tools/x-operator/frontend/src/views/cockpit/StrategyAndPromptsCard.tsx`
- Does NOT own: `/home/lichao/tools/x-operator/frontend/src/views/crm/` (AP-01)
- Invariants to test: 无缝双入口导航（顶栏 Studio 按钮 + 驾驶舱策略子Tab无缝直通），彻底清理写死的 Mock 数组 (AP-02)

**Step 1: Update Header navigation**

在顶栏导航中增加 `studio`（机制与配置中枢）Tab 项，并在 App.tsx 中完成路由分发。

**Step 2: Refactor StrategyAndPromptsCard**

删除写死的 `const prospectQueries = [...]` 与 `const soulQuadrants = [...]`，将其重构为指向 `MechanismStudioView` 的内嵌视图或无缝跳转面板。

**Step 3: Verify frontend compilation**

Run: `npm --prefix /home/lichao/tools/x-operator/frontend run build`  
Expected: Build passes with 0 errors.

**Step 4: Commit**

```bash
git -C /home/lichao/tools/x-operator add frontend/src/App.tsx frontend/src/components/layout/Header.tsx frontend/src/views/cockpit/
git -C /home/lichao/tools/x-operator commit -m "refactor(frontend): wire Studio into top navigation and eliminate hardcoded mock cards from cockpit"
```

---

### Task 6: 全链路不变量回归测试与 Pre-push 门禁体检

**Files:**
- Create: `/home/lichao/tools/x-operator/tests/test_mechanism_studio_conformance.py`
- Test: 全量 pytest + 前端静态检查
- Does NOT own: 宿主机非 x-operator 文件 (AP-01)
- Invariants to test: 覆盖全部 INV-SSOT-01 至 INV-SSOT-06 不变量 (AP-02)

**Step 1: Write integration conformance test**

```python
# tests/test_mechanism_studio_conformance.py
def test_full_studio_lifecycle_and_hot_reload():
    # 1. Update config through simulated API
    # 2. Check history backup
    # 3. Check cognitive pipeline output immediately carries update
    # 4. Check soul prompt override
    # 5. Check reset to default
    ...
```

**Step 2: Run full backend and frontend validation**

Run: `pytest /home/lichao/tools/x-operator/tests/ -v`  
Run: `npm --prefix /home/lichao/tools/x-operator/frontend run build`  
Expected: 100% tests pass, exit code 0.

**Step 3: Commit**

```bash
git -C /home/lichao/tools/x-operator add tests/test_mechanism_studio_conformance.py
git -C /home/lichao/tools/x-operator commit -m "test(conformance): add full lifecycle conformance test suite for SSOT and mechanism studio"
```
