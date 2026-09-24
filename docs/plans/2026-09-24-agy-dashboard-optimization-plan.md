# Antigravity Dashboard 沉浸运维流实施计划 (Implementation Plan)

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 基于 Awesome 生态（Uptime Kuma、Glance、Beszel、Homepage）的运维实践，为 `agy-monitor-dashboard` 注入集群配额聚合池、Uptime 心跳健康微条、双环形 SVG 微仪表盘、极客全局快捷键与一键复制运维能力。

**Architecture:** 前端纯原生 Vue 3 + Tailwind CSS（零新引入外部依赖），后端 Python FastAPI 内存中维护滑动窗口心跳队列并在 `/api/quota` 响应中输出集群聚合指标。

**Tech Stack:** Python 3.12, FastAPI, Vue 3, Tailwind CSS, Local Vendored Assets (Chart.js, FontAwesome).

---

### Task 1: 后端轻量心跳历史收集与集群聚合指标 (`app.py`)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/app.py`
- Test: `/home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py`
- Does NOT own: `/home/lichao/layered-cognitive-agent/*`, `/home/lichao/.agy-accounts/*/`
- Invariants to test:
  - 响应字典必须包含 `aggregate`（含 `gemini_weekly_avg`, `claude_weekly_avg`, `healthy_accounts` 等字段）
  - 每个账号对象中附带 `heartbeats` 列表，最大长度不超过 20
  - 单个账号超时不影响其他账号的心跳与配额统计

**Step 1: 编写测试用例**
在 `/home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py` 中编写测试：
```python
import pytest
from app import fetch_single_account_quota, HEARTBEAT_HISTORY, calculate_cluster_aggregate

def test_heartbeat_history_recording():
    # 测试心跳记录存在且长度受限
    HEARTBEAT_HISTORY.clear()
    res = fetch_single_account_quota("a")
    assert "heartbeats" in res
    assert len(res["heartbeats"]) >= 1
    assert "latency_ms" in res["heartbeats"][-1]
    assert "ok" in res["heartbeats"][-1]

def test_cluster_aggregate_calculation():
    mock_quotas = {
        "a": {"available": True, "gemini_weekly": 50.0, "claude_weekly": 40.0},
        "b": {"available": True, "gemini_weekly": 70.0, "claude_weekly": 60.0},
        "c": {"available": False, "error": "Fail"}
    }
    agg = calculate_cluster_aggregate(mock_quotas)
    assert agg["healthy_accounts"] == 2
    assert agg["total_accounts"] == 3
    assert agg["gemini_weekly_avg"] == 60.0
    assert agg["claude_weekly_avg"] == 50.0
```

**Step 2: 运行测试验证失败**
```bash
pytest /home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py -v
```
Expected: FAIL（函数尚未定义）

**Step 3: 编写核心实现代码**
在 `/home/lichao/agy-monitor-dashboard/app.py` 中：
1. 引入 `from collections import defaultdict, deque`
2. 定义 `HEARTBEAT_HISTORY = defaultdict(lambda: deque(maxlen=20))`
3. 在 `fetch_single_account_quota` 记录响应耗时 `latency_ms` 与结果状态并推入 `HEARTBEAT_HISTORY[acc_id]`
4. 实现 `calculate_cluster_aggregate(quotas)` 并在 `get_cluster_quota` 中组装 `aggregate` 返回体。

**Step 4: 运行测试验证通过**
```bash
pytest /home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py -v
```
Expected: PASS

**Step 5: 提交代码**
```bash
git add /home/lichao/agy-monitor-dashboard/app.py /home/lichao/agy-monitor-dashboard/test_dashboard_enhancements.py
```

---

### Task 2: 前端集群聚合配额池与 Uptime 心跳健康微条组件 (`static/index.html`)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/static/index.html`
- Does NOT own: `/home/lichao/layered-cognitive-agent/*`
- Invariants to test:
  - 顶部导航栏下方正确渲染 `ClusterAggregateBar`，包含 Gemini 与 Claude 3P 的百分比与储备算力进度条
  - 每个账号卡片头部下方正确渲染 20 个心跳小方块，悬停展示延迟与时间

**Step 1: 在 `index.html` 插入集群聚合条组件模板**
在导航栏与 Tab 内容区之间新增全局聚合组件：
```html
<div v-if="aggregateData" class="mb-6 p-4 rounded-2xl bg-slate-900/60 border border-white/5 shadow-lg backdrop-blur">
  <!-- Gemini 总配额池与 Claude 总配额池双进度条 -->
</div>
```

**Step 2: 在账号卡片插入心跳微条组件模板**
在账号卡片邮箱与状态徽章下方：
```html
<div class="mt-2.5 flex items-center gap-1">
  <span class="text-[10px] text-slate-500 font-mono mr-1">心跳:</span>
  <div class="flex items-center gap-0.5">
    <div 
      v-for="(hb, idx) in getHeartbeats(acc.id)" 
      :key="idx"
      class="w-1.5 h-3.5 rounded-sm transition-all hover:scale-125 cursor-pointer"
      :class="hb.ok ? (hb.latency_ms > 1500 ? 'bg-amber-400' : 'bg-emerald-400') : 'bg-rose-500'"
      :title="`${hb.time_str} · ${hb.ok ? '正常' : '异常'} (${hb.latency_ms}ms)`"
    ></div>
  </div>
</div>
```

**Step 3: 验证渲染与逻辑**
运行本地测试脚本抓取页面 DOM 元素，确认聚合数据计算正常。

---

### Task 3: 原生 SVG 双环形微仪表、全局快捷键系统与一键复制动效 (`static/index.html`)

**Files:**
- Modify: `/home/lichao/agy-monitor-dashboard/static/index.html`
- Does NOT own: `/home/lichao/layered-cognitive-agent/*`
- Invariants to test:
  - SVG 双环形微仪表（viewBox 36x36）根据余量百分比平滑呈现环形进度
  - 全局键盘监听器在用户输入文本时静默，按下 `1-4` 无缝切页，`r` 立即刷新
  - 点击卡片命令触发 `navigator.clipboard.writeText` 并呈现 Toast

**Step 1: 编写 SVG 圆环微仪表模板与着色计算**
通过计算 `stroke-dasharray`：
```html
<svg viewBox="0 0 36 36" class="w-10 h-10 transform -rotate-90">
  <path class="text-slate-800" stroke-width="3" stroke="currentColor" fill="none" d="..."/>
  <path :stroke="getRingColor(percent)" :stroke-dasharray="`${percent}, 100`" stroke-width="3" fill="none" d="..."/>
</svg>
```

**Step 2: 绑定全局快捷键监听器**
```javascript
window.addEventListener('keydown', (e) => {
  if (['INPUT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
  if (e.key === '1') currentTab.value = 'tasks';
  if (e.key === '2') currentTab.value = 'matrix';
  if (e.key === '3') currentTab.value = 'analytics';
  if (e.key === '4') currentTab.value = 'operations';
  if (e.key.toLowerCase() === 'r') fetchData(true);
});
```

**Step 3: 一键复制与 Toast 动效**
```javascript
function copyCommand(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast(`已复制: ${text}`, 'success');
  });
}
```

---

### Task 4: 服务平滑重启与端到端回归验证

**Files:**
- Execute: `/home/lichao/agy-monitor-dashboard/start.sh`
- Test: 局域网访问 `http://10.36.6.252:1888`，验证 8 个账号聚合指标与心跳流

**Step 1: 重启仪表盘服务**
```bash
/home/lichao/agy-monitor-dashboard/start.sh
```

**Step 2: 调用 `/api/quota?force=true` 验证数据完整性**
验证 `aggregate`、`heartbeats` 及 8 个账号无报错。

**Step 3: 归档与更新任务清单**
更新 `docs/plans/task.md`。
