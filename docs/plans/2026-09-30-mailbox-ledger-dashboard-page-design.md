# Design Document: smartlijingyangs.top 邮箱注册与 Agent 调用台账独立全屏数据看板专页

## 1. 背景与目标

当前 Everything Library（`10.36.6.252:1889`）归档的「**smartlijingyangs.top 邮箱注册与 Agent 调用台账**」（`smartlijingyang-mail-registry-record.md`）已累积 320+ 条实时事件与 242 个预制邮箱资产（正文超 660 行）。
用户在系统默认的阅读弹窗（`reader-modal`）中查阅时，受制于模态框的固定宽高比，必须进行冗长乏味的横向与纵向反复拖拽，且无法快速洞察宏观数据（如：何时注册最活跃、各 Agent 配额消耗趋势、成功率、当前容量水位）。

**核心目标：**
1. **脱离弹窗，专页独立承载**：提供全屏独立的专用页面 `/ledger/mailbox`，在大屏与标准视口下均可全宽自由展开；首页知识库条目点击该卡片时自动路由直达全屏专页。
2. **Dashboard 宏观概览**：顶部提供 KPI 指标卡片（总邮箱资产、已分配/占用率、可用余量、验证码提取成功率、累计调用数、平均响应延迟）与趋势图表（时间序列峰值分析、Agent 消耗分布占比）。
3. **业界高级交互式台账 DataGrid**：
   - 彻底告别手拉几百行表格：支持全局瞬时过滤（搜邮箱、搜 Agent、搜验证码）、状态筛选、分页浏览（每页 20/50 条）、验证码一键复制。
   - 邮箱资产池全量视图：按 `IN_USE` / `AVAILABLE` 快速分组筛选。
4. **原始文档兼容**：保留基础设施配置表与原生 Markdown 查看/复制入口。

---

## 2. 架构设计与数据流

```
┌────────────────────────────────────────────────────────┐
│             底层持久化事件源 (SSOT)                     │
│  • /home/lichao/agent-mail-hub/data/audit_events.jsonl │
│  • /home/lichao/agent-mail-hub/data/mail_pool.json     │
│  • smartlijingyang-mail-registry-record.md             │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│        Everything Library 后端聚合层 (FastAPI)          │
│  • GET /api/ledger/mailbox/data (零延迟聚合统计与趋势)  │
│  • GET /ledger/mailbox (专属全屏 HTML 模板渲染)         │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│               前端全屏数据看板 (Tailwind + JS)          │
│  1. 顶部状态栏：实时时间、刷新按键、返回知识库导航     │
│  2. KPI 卡片区：4 大核心指标 + 容量水位进度条           │
│  3. 趋势图表区：时序调用柱状/折线图 + Agent 占比分布   │
│  4. 交互式数据表：分页/搜索/筛选/一键复制/微标状态     │
│  5. 资产池分组表：242 个邮箱槽位分配实时概览           │
└────────────────────────────────────────────────────────┘
```

---

## 3. 组件职责与实现规格

### 3.1 后端 API 聚合器 (`app/api/routes.py` 或专用模块)
- **端点**：`GET /api/ledger/mailbox/data`
- **输入**：可选 `limit`, `refresh`
- **逻辑**：
  1. 读取 `/home/lichao/agent-mail-hub/data/mail_pool.json`（若不可读则优雅降级解析 Markdown）：
     - 统计 `total_mailboxes` (242), `in_use` (如 158), `available` (如 84)。
  2. 读取 `/home/lichao/agent-mail-hub/data/audit_events.jsonl`：
     - 计算累计调用量、成功提取验证码次数、失败次数、平均轮询时延。
     - 按时间（小时/日期）聚合调用频度，生成趋势时序数组 `[{date_hour: "09-28 16:00", acquire_count: 5, code_count: 8}, ...]`。
     - 统计各 Agent 的调用占比 `{agent_id: count}`。
  3. 返回规范的 JSON 结构，给前端提供瞬时渲染支撑（加载耗时 < 30ms）。

### 3.2 独立 Web 路由与模板 (`app/web/routes.py` & `ledger_mailbox.html`)
- **路由**：`GET /ledger/mailbox`
  - 依赖统一 Session 鉴权（`require_auth_web`），未登录自动重定向到 `/login`。
  - 渲染 `ledger_mailbox.html` 专属模板。
- **模板交互设计**：
  - 采用 Tailwind CSS + 极简科技感深色/浅色自适应风格（配有 Emerald 绿色和 Slate 经典背景）。
  - **图表渲染**：引入轻量 Chart.js（或纯 CSS/SVG 响应式渲染），直观呈现每日每小时的注册与调用波动峰值。
  - **数据表格**：
    - Tab 1: **实战调用流水台账**（分页器、模糊搜索框、下拉 Agent 筛选器、验证码高亮带一键复制 toast）。
    - Tab 2: **邮箱池全量资产卡片/列表**（支持快速看谁占用了哪个邮箱）。
    - Tab 3: **底座基础设施 & 原始 SOP**（展示 NameSilo、Cloudflare 路由、Worker 端点、Markdown 正文）。

### 3.3 主页卡片交互联动 (`app/web/templates/index.html`)
- 在 `openReader(itemId)` 中加入特殊拦截判定：
  ```javascript
  if (itemId === 'smartlijingyang-mail-registry-record') {
    window.location.href = '/ledger/mailbox';
    return;
  }
  ```
- 在卡片 UI 上额外标注「📊 数据看板专页」徽标，点击即直达。

---

## 4. 边界声明 (AP-01)

- **Owns (负责实现与修改)**:
  - `/home/lichao/everything-library/app/web/routes.py`（增加 `/ledger/mailbox` 路由）
  - `/home/lichao/everything-library/app/web/templates/ledger_mailbox.html`（新增高质感全屏专页模板）
  - `/home/lichao/everything-library/app/api/routes.py`（增加 `/api/ledger/mailbox/data` 聚合接口）
  - `/home/lichao/everything-library/app/web/templates/index.html`（针对该条目增加专页直达交互）
  - `/home/lichao/everything-library/tests/test_ledger_mailbox.py`（端到端路由与聚合逻辑自动化测试）
- **Does NOT own (严格禁止跨越)**:
  - 严禁修改 `/home/lichao/agent-mail-hub/` 的核心服务与文件写入逻辑。
  - 严禁向 `layered-cognitive-agent` 仓库提交任何宿主机运维或 `everything-library` 资产代码（所有代码变更必须严格在 `~/everything-library` 内提交）。
  - 严禁破坏现有用户鉴权机制（`auth.py`）。

---

## 5. 架构不变量与测试验证 (AP-02)

1. **不变量 1：统计一致性**
   - 验证：`stats.total == stats.allocated + stats.available`，计算出的调用流水总量与 `audit_events.jsonl` 行数严格一致。
2. **不变量 2：安全性与鉴权隔离**
   - 验证：未登录访问 `/ledger/mailbox` 必须返回 303 重定向到 `/login`；已登录访问返回 200 OK。
3. **不变量 3：降级鲁棒性**
   - 验证：若 `agent-mail-hub/data/` 目录临时不可访问，接口应自动降级从 Markdown 表格中解析并返回有效数据，绝不抛 500。
4. **不变量 4：性能体验**
   - 验证：数据聚合接口响应时间 < 50ms，前端页面无需全量解析 Markdown 即可完成初屏渲染。

---

## 6. 自治与爆炸半径分级 (AP-05)

- **等级**: `AUTOPILOT`（属于只读呈现与看板增强，不产生任何破坏性或不可逆写入，自带完整 pytest 测试守护）。
