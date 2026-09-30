# smartlijingyangs.top 邮箱注册与 Agent 调用台账独立全屏看板 Implementation Plan

> **For Antigravity:** REQUIRED WORKFLOW: Use `.agent/workflows/execute-plan.md` to execute this plan in single-flow mode.

**Goal:** 构建生产级独立全屏数据看板页面 `/ledger/mailbox`，集成宏观 KPI 统计卡片、时序注册与调用趋势图、交互式分页搜索流水表格及邮箱池资产全览，并在知识库条目中打通一键全屏直达，彻底消除原有 Modal 弹窗逼仄、超长拖动的操作痛点。

**Architecture:** 
- 后端在 `everything-library` 内新增轻量聚合引擎 `app/api/ledger_analytics.py`，秒级解析持久化事件源（`audit_events.jsonl` + `mail_pool.json`），输出结构化趋势与明细 API (`/api/ledger/mailbox/data`)；
- 前端在 `everything-library` 中新增独立全屏 Web 路由 `/ledger/mailbox` 与模板 `ledger_mailbox.html`，以 Tailwind CSS + Lucide Icons + Chart.js 打造媲美 Stripe/Linear 风格的高级质感看板；
- 首页 `index.html` 对该条目进行专页联动，点击直接全屏直达。

**Tech Stack:** Python 3.12, FastAPI, Jinja2, Tailwind CSS, Chart.js, Lucide Icons, Pytest.

---

### Task 1: 后端聚合分析引擎与数据接口 (`/api/ledger/mailbox/data`)

**Files:**
- Create: `/home/lichao/everything-library/app/api/ledger_analytics.py`
- Modify: `/home/lichao/everything-library/app/api/routes.py`
- Test: `/home/lichao/everything-library/tests/test_ledger_mailbox_api.py`
- Does NOT own: `/home/lichao/agent-mail-hub/` 核心服务逻辑、`auth.py`
- Invariants to test:
  1. 返回的 JSON 包含 `stats`, `trends`, `agents`, `events`, `mailboxes` 结构。
  2. `stats['total_mailboxes'] == stats['in_use'] + stats['available']`。
  3. `audit_events.jsonl` 缺失时优雅降级解析 Markdown，绝不抛出 500。

**Step 1: Write the failing test**
在 `/home/lichao/everything-library/tests/test_ledger_mailbox_api.py` 中编写针对聚合接口的测试用例。

**Step 2: Run test to verify it fails**
Run: `/opt/lca/venv/bin/pytest /home/lichao/everything-library/tests/test_ledger_mailbox_api.py -v`
Expected: FAIL (Module / Route not found).

**Step 3: Write minimal implementation**
- 编写 `app/api/ledger_analytics.py`，实现 `build_mailbox_ledger_analytics()`。
- 在 `app/api/routes.py` 挂载 `GET /ledger/mailbox/data`。

**Step 4: Run test to verify it passes**
Run: `/opt/lca/venv/bin/pytest /home/lichao/everything-library/tests/test_ledger_mailbox_api.py -v`
Expected: PASS.

**Step 5: Commit (in everything-library)**
```bash
cd /home/lichao/everything-library
git add app/api/ledger_analytics.py app/api/routes.py tests/test_ledger_mailbox_api.py
git commit -m "feat(ledger): add mailbox ledger analytics engine and api endpoint"
```

---

### Task 2: 全屏独立看板模板与 Web 路由 (`/ledger/mailbox`)

**Files:**
- Create: `/home/lichao/everything-library/app/web/templates/ledger_mailbox.html`
- Modify: `/home/lichao/everything-library/app/web/routes.py`
- Test: `/home/lichao/everything-library/tests/test_ledger_mailbox_web.py`
- Does NOT own: `/home/lichao/layered-cognitive-agent/` (禁止提交到 LCA)
- Invariants to test:
  1. 未登录访问 `/ledger/mailbox` 重定向至 `/login`（HTTP 303）。
  2. 模拟认证 Session 访问 `/ledger/mailbox` 返回 HTTP 200，且包含看板专属元素（如 `#mailbox-kpi-grid`, `#ledger-trend-chart`, `#events-table`）。

**Step 1: Write the failing test**
编写针对 `/ledger/mailbox` 路由鉴权与页面渲染的集成测试。

**Step 2: Run test to verify it fails**
Run: `/opt/lca/venv/bin/pytest /home/lichao/everything-library/tests/test_ledger_mailbox_web.py -v`
Expected: FAIL (404 Not Found).

**Step 3: Write minimal implementation**
- 在 `app/web/routes.py` 增加 `/ledger/mailbox` 路由。
- 编写 `ledger_mailbox.html`：包含沉浸式顶部栏、4 大 KPI 指标卡片、容量水位条、Chart.js 时序趋势图（按小时/天分析注册与提取高峰）、可搜索/可分页交互式流水表格、邮箱池资产总表、一键复制验证码 Toast、以及原始 Markdown 抽屉。

**Step 4: Run test to verify it passes**
Run: `/opt/lca/venv/bin/pytest /home/lichao/everything-library/tests/test_ledger_mailbox_web.py -v`
Expected: PASS.

**Step 5: Commit (in everything-library)**
```bash
cd /home/lichao/everything-library
git add app/web/routes.py app/web/templates/ledger_mailbox.html tests/test_ledger_mailbox_web.py
git commit -m "feat(web): add dedicated full-screen mailbox ledger dashboard page"
```

---

### Task 3: 知识库主页卡片交互联动 (`index.html`)

**Files:**
- Modify: `/home/lichao/everything-library/app/web/templates/index.html`
- Test: `/home/lichao/everything-library/tests/test_ledger_mailbox_web.py`
- Does NOT own: 其他无关条目的渲染逻辑
- Invariants to test:
  1. 卡片列表中渲染带有专用数据看板标识。
  2. 点击该条目时由前端直接重定向至 `/ledger/mailbox`，不弹起常规 `reader-modal`。

**Step 1: Write/Update test**
在 Web 测试中验证主页针对 `smartlijingyang-mail-registry-record` 的专页跳转属性存在。

**Step 2: Implement interaction link**
修改 `app/web/templates/index.html` 的 `openReader` 函数，遇到该 ID 立即通过 `window.location.href = '/ledger/mailbox'` 直达全屏专页。

**Step 3: Run tests to verify**
Run: `/opt/lca/venv/bin/pytest /home/lichao/everything-library/tests/ -k ledger -v`
Expected: PASS.

**Step 4: Commit (in everything-library)**
```bash
cd /home/lichao/everything-library
git add app/web/templates/index.html
git commit -m "feat(ui): link mailbox ledger card directly to full-screen dashboard"
```

---

### Task 4: 服务热重载、端到端探针验证与验收

**Files:**
- Does NOT own: LCA 仓库（严格保持 LCA git clean）

**Step 1: 平滑重启 Everything Library 服务 (:1889)**
```bash
cd /home/lichao/everything-library
./run.sh
```

**Step 2: 验证 API 探针与 Web 页面**
```bash
curl -s http://127.0.0.1:1889/api/ledger/mailbox/data | jq .stats
curl -I http://127.0.0.1:1889/ledger/mailbox
```

**Step 3: 确认 Git 边界与工作区卫生**
- 检查 `everything-library` 仓库 `git status`。
- 检查 `layered-cognitive-agent` 仓库 `git status`（零误触外部资产）。
