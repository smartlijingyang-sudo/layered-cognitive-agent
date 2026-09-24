# 账号差异化权重、错峰接力流水线与贡献模型实施计划

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 在 Antigravity 监控控制台中落地账号容量差异化权重（Pro 3x / Free 1x）、7 天错峰回血接力流水线大盘与账号算力/交互贡献模型，使用户一目了然看清各账号的定位差异、接力序列与工作量贡献。

**Architecture:** 后端在 `app.py` 中引入容量权重 $w_i$ 计算加权等效算力池、构建按 $T_{rem}$ 严格升序排序的错峰流水线接力序列，并聚合计算算力消耗吞吐贡献与交互次数贡献；前端在驾驶舱顶部装配横向接力流水线微时间轴，在卡片上显式突出权重角色、回血倒计时与贡献徽章。

**Tech Stack:** Python 3.12, FastAPI, SQLite3, Vue 3, Tailwind CSS, FontAwesome, Pytest.

---

### Task 1: 后端容量加权算力池与错峰接力流水线算法 (app.py)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/app.py:235-300`
- Does NOT own: `/home/lichao/layered-cognitive-agent/*`, OAuth tokens, external CDNs (AP-01)
- Invariants to test:
  - INV-DIFF-01: 加权配额池均值必然属于 $[0.0, 100.0]$。
  - INV-DIFF-02: 流水线排序必然按 `remaining_hours` 严格升序。
  - INV-DIFF-04: Pro 账号 `weight=3.0`，Free 账号 `weight=1.0`。

**Step 1: 编写失败测试**
在 `test_dashboard_enhancements.py` 中编写 `test_weighted_pool_and_pipeline_calculation`。

**Step 2: 运行测试验证失败**
运行 `/opt/lca/venv/bin/pytest test_dashboard_enhancements.py -k test_weighted_pool_and_pipeline_calculation -v`，预期失败。

**Step 3: 编写核心实现**
在 `app.py` 中实现：
- `calculate_pipeline_timeline(quotas, accounts)`：返回按 `remaining_hours` 升序排列的 8 账号梯队，包含 `tier_stage`（临近回血/中坚过渡/满血储备）。
- 升级 `calculate_cluster_aggregate`：增加 `gemini_weighted_avg`、`claude_weighted_avg` 与 `pipeline_timeline`。

**Step 4: 运行测试验证通过**
运行 `/opt/lca/venv/bin/pytest test_dashboard_enhancements.py -k test_weighted_pool_and_pipeline_calculation -v`，预期通过。

**Step 5: 提交**
提交测试与实现。

---

### Task 2: 后端账号贡献模型与任务数据注入 (app.py)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/app.py:870-990`
- Does NOT own: `/home/lichao/layered-cognitive-agent/*`, OAuth tokens (AP-01)
- Invariants to test:
  - INV-DIFF-03: 当存在消耗时，各账号算力贡献百分比之和归一化为 $100.0\% \pm 0.2\%$。

**Step 1: 编写失败测试**
在 `test_dashboard_enhancements.py` 中编写 `test_account_contributions_calculation`。

**Step 2: 运行测试验证失败**
运行 `/opt/lca/venv/bin/pytest test_dashboard_enhancements.py -k test_account_contributions_calculation -v`，预期失败。

**Step 3: 编写实现**
在 `app.py` 的 `get_cluster_live_tasks` 中：
- 计算每个账号的 `weight`（Pro 3.0 / Free 1.0）。
- 计算全集群算力消耗总值与交互总值，并计算每个账号的 `burn_contribution_pct` 与 `prompt_contribution_pct`。
- 将 `pipeline_info`、`capacity_weight` 与贡献指标注入 `tasks` 返回体。

**Step 4: 运行测试验证通过**
运行 `/opt/lca/venv/bin/pytest test_dashboard_enhancements.py -k test_account_contributions_calculation -v`，预期通过。

**Step 5: 提交**
提交测试与实现。

---

### Task 3: 前端错峰接力流水线与差异化卡片重构 (static/index.html)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/static/index.html`
- Does NOT own: `/home/lichao/layered-cognitive-agent/*`, external CDNs (AP-01)
- Invariants to test:
  - 前端必须包含流水线微时间轴容器与账号贡献徽章渲染逻辑。

**Step 1: 编写断言测试**
在 `test_dashboard_enhancements.py` 中增加对 `pipeline_timeline`、`加权等效算力池`、`算力贡献` 等 DOM 关键特征的断言。

**Step 2: 更新前端模板与脚本**
- 顶部算力池增加加权等效池与算术均值双轨指示。
- 顶部增加「7天错峰回血流水线」横向微时间轴，直观列出按回血时间先后排序的账号胶囊。
- 8 账号卡片中增加容量权重标识（`PRO 3×权` / `FREE 1×权`）、流水线接力梯队角色与算力/工作量贡献徽章。

**Step 3: 运行自动化测试验证通过**
运行 `/opt/lca/venv/bin/pytest -v`，确保 100% 通过。

---

### Task 4: 服务平滑重启与全链路端到端回归验证

**Files:**
- Modify: `/home/lichao/layered-cognitive-agent/docs/plans/task.md`
- Command: `bash /home/lichao/agy-monitor-dashboard/start.sh`

**Step 1: 平滑重启服务**
运行 `bash start.sh`，确保 tmux 会话健康。

**Step 2: 端到端活体验证**
编写测试脚本请求 `http://127.0.0.1:1888/api/quota` 与 `/api/cluster/live_tasks`，验证加权配额、错峰流水线排序与贡献百分比输出。

**Step 3: 更新任务进度并提交**
更新 `docs/plans/task.md`，提交变更。
