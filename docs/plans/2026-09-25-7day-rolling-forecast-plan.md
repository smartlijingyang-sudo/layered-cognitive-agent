# 7-Day Rolling Compute Forecast & Relay Schedule Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 构建未来 7 天算力回血预报日程表（7-Day Rolling Forecast），按天呈现每天满血重置的账号清单、恢复的算力权单位（Capacity Units）、预计集群加权算力池跃升百分比与智能接力调度建议。

**Architecture:** 后端在 `app.py` 中基于各账号真实的 Google Code Assist `resetTime` 与容量权重，按自然日（UTC+8）推演 7 天滚动窗口，计算恢复算力权、预计回血量与接力策略；前端在 `static/index.html` 的驾驶舱错峰流水线下方渲染横向 7 天日程卡片流；编写确定性单测断言时间连续性与算力守恒。

**Tech Stack:** Python 3.12, FastAPI, Vue.js 3, Tailwind CSS, FontAwesome 6, pytest.

---

### Task 1: 后端未来 7 天回血预报算法 (`FORECAST-TASK-1`)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/app.py:320-360`
- Test: `/home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py`
- Does NOT own: `/home/lichao/layered-cognitive-agent/*` core agent contracts (AP-01)
- Invariants to test: 严格输出 7 天日程列表；日期严格单调递增；7 天内恢复的算力权总和严格等于 20.0 (AP-02)

**Step 1: Write the failing test**
在 `test_dashboard_enhancements.py` 中编写 `test_7day_forecast_calculation`：
```python
def test_7day_forecast_calculation():
    # 模拟数据
    mock_quotas = { ... }
    forecast = app.calculate_7day_forecast(mock_quotas)
    assert len(forecast) == 7
    # 检查单调性与字段
    total_restored_units = sum(d["restored_capacity_units"] for d in forecast)
    assert total_restored_units == 20.0
```

**Step 2: Run test to verify it fails**
Run: `/opt/lca/venv/bin/pytest -v /home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py::test_7day_forecast_calculation`
Expected: FAIL with "AttributeError: module 'app' has no attribute 'calculate_7day_forecast'"

**Step 3: Write minimal implementation**
在 `app.py` 中实现 `calculate_7day_forecast(quotas, accounts=None)`：
- 构造当前基准时间（UTC+8 CST）起接下来的 7 个自然日桶（Day 0-6）。
- 将每个账号按重置日期归入对应日期桶。
- 计算每天的 `restored_capacity_units`、`reset_accounts` 列表、`pool_lift_pct` 与 `relay_advice`。

**Step 4: Run test to verify it passes**
Run: `/opt/lca/venv/bin/pytest -v /home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py::test_7day_forecast_calculation`
Expected: PASS

---

### Task 2: API 响应体集成与数据注入 (`FORECAST-TASK-2`)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/app.py`
- Test: `/home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py`
- Does NOT own: External CDNs, OAuth tokens (AP-01)
- Invariants to test: `/api/quota` 的 `aggregate.forecast_7days` 存在且非空；`/api/cluster/live_tasks` 携带 `forecast_7days` (AP-02)

**Step 1: Write the failing test**
在 `test_dashboard_enhancements.py` 中增加断言：
```python
def test_quota_and_live_tasks_include_7day_forecast():
    # client 请求 /api/quota 和 /api/cluster/live_tasks
    # assert "forecast_7days" in data["aggregate"]
```

**Step 2: Implement integration**
在 `calculate_cluster_aggregate` 中将 `forecast_7days` 挂入返回字典；在 `/api/cluster/live_tasks` 的返回体中附带 `forecast_7days`。

**Step 3: Run test to verify it passes**
Run: `/opt/lca/venv/bin/pytest -v /home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py`
Expected: 14/14 PASS

---

### Task 3: 前端 7 天回血预报日程卡片流组件 (`FORECAST-TASK-3`)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/static/index.html`
- Test: `/home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py`
- Does NOT own: Core LCA code (AP-01)
- Invariants to test: DOM 包含 `7天回血预报`、`forecast_7days`、`恢复算力`、`接力建议` (AP-02)

**Step 1: Write failing test**
在 `test_index_html_enhancements_present` 中增加断言：
```python
assert "7天回血预报" in html
assert "forecast_7days" in html
assert "恢复算力" in html
```

**Step 2: Implement UI component in `static/index.html`**
在驾驶舱“错峰接力流水线”下方新增 7 天日程卡片流：
- 渲染 7 天横向响应式网格（`grid-cols-1 sm:grid-cols-2 lg:grid-cols-7`）。
- 突出显示“明天”、“后天”专属徽章。
- 卡片内部清晰呈现：
  - 日期与星期（如“明天 09-26 周六”）
  - 重置账号徽章与精准倒计时（如“B · 16:52 满血”）
  - 恢复算力权单位（如“+3 算力权”）与预计回血跃升幅度
  - 智能接力调度建议（如“⚡ 建议将主力任务切至 B 攻坚”）
- 在无重置日显示中坚稳健消耗提示。

**Step 3: Run test to verify it passes**
Run: `/opt/lca/venv/bin/pytest -v /home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py`
Expected: PASS

---

### Task 4: 服务平滑重启与全链路端到端回归验证 (`FORECAST-TASK-4`)

**Files:**
- Execute: `bash /home/lichao/agy-monitor-dashboard/start.sh`
- Verify: Live endpoints on `http://127.0.0.1:1888`
- Docs: Update `/home/lichao/layered-cognitive-agent/docs/plans/task.md`

**Step 1: Restart service**
Run: `bash /home/lichao/agy-monitor-dashboard/start.sh`

**Step 2: Run verification script**
编写 Python 探针请求 live API，验证明天周六（B 回血 +3 权）、后天周日（A 回血 +3 权）及后续 7 天完整预测数据。

**Step 3: Full test suite**
Run: `/opt/lca/venv/bin/pytest -v /home/lichao/agy-monitor-dashboard` (14/14 tests)

**Step 4: Update task.md & commit**
标记所有任务 Completed 并沉淀测试证据。
