# Antigravity Dashboard 驾驶舱重构与周步调算法实施计划 (Implementation Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 消除仪表盘 4 个 Tab 的功能重叠，建立单域真值全能驾驶舱（SSOT Cockpit），实现周配额时间步调健康模型（Weekly Quota Pace Index），并将运维长篇 SOP 改造为渐进式折叠手风琴。

**Architecture:** 后端 Python 动态解析 7 天滚动重置窗口与时间流速偏差，前端收敛为 3 个权威 Tab，首页汇聚配额、任务、心跳与运维入口，消灭重复卡片。

**Tech Stack:** Python 3.12, FastAPI, Vue 3, Tailwind CSS, SVG.

---

### Task 1: 后端周配额时间步调算法与集群宏观步调指标 (`app.py`)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/app.py`
- Test: `/home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py`
- Does NOT own: `/home/lichao/layered-cognitive-agent/*`, `/home/lichao/.agy-accounts/*/`
- Invariants to test:
  - `calculate_weekly_pacing` 正确计算 168 小时周期下理论应剩百分比、偏差 $\Delta$ 及状态
  - `/api/quota` 返回体中的每个账号配额对象包含 `gemini_pacing` 与 `claude_pacing`
  - `aggregate` 包含全集群的 `gemini_pacing_delta` 与 `claude_pacing_delta`

**Step 1: 编写测试用例**
在 `test_dashboard_enhancements.py` 增加：
```python
def test_weekly_pacing_calculation():
    # 模拟还有 3 天重置 (72 小时 / 168 小时 ≈ 42.86%)
    now = datetime.datetime.now(datetime.timezone.utc)
    future_reset = (now + datetime.timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # 实际余量 50.0% > 42.9% -> 慢于时间流速，健康
    res = app.calculate_weekly_pacing(future_reset, 50.0)
    assert res["status"] == "HEALTHY"
    assert res["pacing_delta"] > 0
    assert abs(res["expected_percent"] - 42.9) < 1.0

    # 实际余量 10.0% < 42.9% -> 透支超速
    res_burn = app.calculate_weekly_pacing(future_reset, 10.0)
    assert res_burn["status"] == "OVERBURNING"
    assert res_burn["pacing_delta"] < -15.0
```

**Step 2: 运行测试验证失败**
```bash
/opt/lca/venv/bin/pytest /home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py -k test_weekly_pacing_calculation -v
```

**Step 3: 实现步调计算与聚合逻辑**
在 `app.py` 中实现 `calculate_weekly_pacing` 并在 `fetch_single_account_quota` 和 `calculate_cluster_aggregate` 中完成装配。

**Step 4: 运行测试验证通过**
```bash
/opt/lca/venv/bin/pytest /home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py -v
```

---

### Task 2: 首页一体化驾驶舱重构 (合并任务与矩阵，消灭重复卡片) (`static/index.html`)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/static/index.html`
- Does NOT own: `/home/lichao/layered-cognitive-agent/*`
- Invariants to test:
  - Tab 导航收敛为 3 个：`cockpit`（驾驶舱）、`analytics`（数据洞察）、`operations`（运维中心）
  - 彻底移除旧 Tab 0 中的冗余 mini-matrix 和旧 Tab 1 中的冗余推荐横幅
  - 8 个账号在首页只有唯一一体化综合卡片，完整呈现：身份+心跳+配额与步调偏差+实时活动+快捷运维入口
  - 顶部集群聚合池展示周配额步调状态（如 `🟢 慢于时间流速 +28.5%`）

**Step 1: 收敛 Tab 导航栏与默认 Tab**
将 `currentTab` 默认值设为 `'cockpit'`，导航栏精简为 3 个 Tab（快捷键 1 对应驾驶舱，2 对应数据洞察，3 对应运维中心）。

**Step 2: 升级顶部全集群算力池与时间步调展示**
在 `ClusterAggregateBar` 中加入 Gemini 与 Claude 的周步调偏差标签（`比时间流速 快/慢 X%`）。

**Step 3: 打造 8 账号一体化综合卡片 (SSOT)**
将旧有的任务卡片和配额卡片合并为单一综合卡片，左半部分为配额与步调，右半部分为当前活跃任务与历史 Prompt 展开。

---

### Task 3: 运维中心 (Tab 3) 长篇 SOP 渐进式折叠手风琴重构 (`static/index.html`)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/static/index.html`
- Does NOT own: `/home/lichao/layered-cognitive-agent/*`
- Invariants to test:
  - 4 大运维章节全部使用 `<details class="glass-card">` 折叠收纳
  - 默认全部收起，只展示事故警示标题与重要性徽章，点击平滑展开

**Step 1: 将 Tab 3 长文重组为 4 个折叠模块**
1. 事故复盘与 Session Expired 防废号铁律
2. 异地风控与 Google Cloud Shell 信任初始化
3. Google AI Pro 订阅与未成年排查
4. 新账号接入与快速克隆 SOP

**Step 2: 优化会话管理快捷面板置顶**
使运维人员在 Tab 3 首先看到会话列表与管理操作，不再被长文遮挡。

---

### Task 4: 服务平滑重启与端到端回归验证

**Files:**
- Execute: `/home/lichao/agy-monitor-dashboard/start.sh`
- Test: 自动化验证 3 Tab 结构、周步调计算、SOP 折叠与端到端 API
- Update: `docs/plans/task.md`
