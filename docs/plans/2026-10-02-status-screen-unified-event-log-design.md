# Status Screen 统一事件日志与增量可观测性架构设计

**日期**：2026-10-02  
**自主等级**：`DRAFT` (跨前后端事件流与可观测性扩展，需完整单测断言守卫)  
**状态**：Approved by User  

---

## 1. 背景与核心动机 (Context & Motivation)

Status Screen（点头像打开的右侧状态抽屉）是 Agent 行为的可观测性面板。原有的抽屉面板存在以下架构与体验缺陷：
1. **数据散碎与非同源**：抽屉内各模块散碎调用业务接口或依赖静态 Mock 数据，缺乏统一的数据模型；
2. **缺乏增量推送机制**：状态更新依赖轮询或重刷，没有利用已建立的 WebSocket 流式信道；
3. **技术黑话与开发符号暴露**：动作标题直接展示底层工具或模块名（如 `executing hatch_gws_cli`），缺乏给人读的意图人话规则；
4. **定时任务（Upcoming）未与 ADR-0268 闭环**：未复用 `cron.list` 投影与 run 历史，编辑缺乏聊天引导，易产生调度歧义；
5. **缺少运行期取消能力**：运行中的动作无法在前端感知并在后端真实中断。

本设计旨在确立：**Status Screen 不直接散碎调业务接口，而是统一读取单轨事件日志的结构化投影**。Activity、Approvals、Upcoming、Identity 均源自同一事实源，前端通过 WebSocket 增量原地 Patch 单行，实现零抖动、高内聚、高可观测的认知面板。

---

## 2. 严格系统边界 (Mandatory Boundaries, AP-01)

### 2.1 Owns (在范围内)
1. **统一事件日志投影层 (`ActivityProjector`)**：
   - 基于 LCA 单轨事实源（`Session.append` / Spine 事实流），纯函数投影出结构化 `ActivityItem` 记录；
   - 严禁设立平行写入的数据库或独立持久化事实源。
2. **动作人话规则引擎 (`ActivityIntentNamer`)**：
   - 在动作发起时（`phase.tool.call.start` / `step.tool_call.record`），直接根据工具名和参数判定意图并锁定人话标题；
   - 覆盖邮件搜索/发送、文件检索、代码执行、子任务委派、网页自动化与定时 Worker。
3. **WebSocket 增量推送契约 (`activity_updated`)**：
   - 扩展 `EventTranslator`，在动作起点发射 `running` 状态，动作结束发射 `completed` / `failed` 状态（携带耗时与结果摘要）；
   - 支持向会话 WebSocket（`/v1/runs/{run_id}/ws`）安全推流。
4. **状态快照与动作取消 REST API**：
   - 暴露 `GET /lca-api/v1/assistants/{id}/status-snapshot`，打包返回 `activities`、`approvals`、`upcoming` 与 `identity`；
   - 暴露 `POST /lca-api/v1/runs/{run_id}/cancel`，通过 `RunPort.cancel` 真实终止任务/进程树，并将日志置为 `cancelled`。
5. **前端抽屉 (`AssistantStatusDrawer.tsx`) 数据流重构**：
   - 面板展开时拉取快照初始化；
   - 监听 WS `activity_updated` 事件，基于 `id` 原地 patch 单行，不全量重刷；
   - Upcoming 深度对接 ADR-0268 `cron.list`，Edit 注入聊天草稿，拦截删除系统保护任务；
   - Running 行 hover 显示 Stop 按钮，支持快速中断。
6. **前端补丁同步与全套不变量回归测试**。

### 2.2 Does NOT Own (严格负向边界，禁止触碰)
1. **严禁破坏 LCA 单轨事实源不变量（C1~C4）**：事件日志投影必须是只读派生视图，严禁让业务执行体跨层直接写平行存储；
2. **严禁修改任何非 LCA 资产或宿主机运维代码**：整机拓扑、运维脚本与 SOP 必须严格归属于外部参考库 `~/everything-library`；
3. **严禁篡改 LobeHub 原生会话核心状态机**：仅通过声明式组件补丁介入右侧面板，不侵入未授权的会话生命周期代码。

---

## 3. 核心数据契约与架构设计

### 3.1 统一动作记录契约 (`ActivityItem`)
遵循 ADR-0195 Typed Contract 规范（Pydantic `extra="forbid"`）：
```python
class ActivityStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class ActivityCategory(str, Enum):
    COMMAND = "command"        # Shell / 进程命令执行
    SUBAGENT = "subagent"      # Subagent 派生与执行
    BROWSER = "browser"        # Browser task 网页操作
    CRON = "cron"              # 定时任务 worker 运行
    TOOL = "tool"              # 普通及连接器工具调用

class ActivityItem(BaseModel):
    id: str                         # 动作唯一 ID (invocation_id / subagent_id / run_id)
    run_id: str
    assistant_id: str
    category: ActivityCategory
    title: str                      # 人话标题（从 intent 来，动作起点即确定）
    summary: str                    # 命令/任务摘要（用于单行快速识别）
    status: ActivityStatus          # running | completed | failed | cancelled
    start_time: str                 # ISO-8601
    end_time: str | None = None
    duration_ms: int | None = None
    icon: str                       # 对应的图标语义 (terminal | browser | robot | clock | tool)
    params: dict[str, Any]          # 脱敏参数详情
    result_summary: str | None = None  # 执行输出/汇报摘要
    is_system: bool = False
```

### 3.2 Activity 标题人话规则引擎 (`ActivityIntentNamer`)
在动作启动时立即根据 Intent 确定标题，绝不展示底层内部调用名：
- **邮件/办公连接器 (`hatch_gws_cli` / `composioConnect`)**：
  - `GMAIL_FETCH_EMAILS` / `GMAIL_LIST_THREADS` → `正在搜索 Gmail 邮件`
  - `GMAIL_SEND_EMAIL` → `正在发送邮件到 {recipient}`
  - `GOOGLE_DRIVE_*` → `正在访问 Google Drive 文档`
  - `GITHUB_*` → `正在检索 GitHub 仓库`
- **Shell / 进程执行 (`run_shell` / `box_run_command`)**：
  - `title = "Running command"`，`summary = "{cmd[:36]}..."`
- **网页自动化 (`browser.spawn_task`)**：
  - `title = "Browsing {target_domain}"`，`summary = "{task_goal}"`
- **Subagent 委派 (`subagent.spawn`)**：
  - `title = "协同任务：{subagent_role}"`，`summary = "{task_prompt[:40]}"`
- **定时任务 Worker (`cron.run`)**：
  - `title = "定时运行：{cron_job.title}"`
- **缺省兜底**：优先读取参数中的自然语言描述 `args.description`，否则格式化为优雅的动宾操作短语。

---

## 4. 通信机制与流式时序

### 4.1 WebSocket 增量推送时序
复用 `/v1/runs/{run_id}/ws` 通道，由 `EventTranslator` 在收到内部事件时无缝翻译发出：
1. **动作开始**：收到 `phase.tool.call.start` 或 `step.tool_call.record`：
   - 提取 `ActivityItem`（`status: "running"`）；
   - 发射 `{ type: "activity_updated", data: { ... } }`；
   - 前端接收后，在时间线顶部（倒序）插入单行，显示转圈态。
2. **动作完成**：收到 `body.tool.execute.end`：
   - 提取执行结果与耗时 `duration_ms`；
   - 发射 `{ type: "activity_updated", data: { id, status: "completed"|"failed", durationMs, ... } }`；
   - 前端根据 `id` 原地查找并更新状态图标为绿色对勾或红色叉。
3. **中途取消**：用户触发 Stop：
   - 后端调用 `RunPort.cancel(run_id)` 杀死进程/任务；
   - 发射 `{ type: "activity_updated", data: { id, status: "cancelled", ... } }`；
   - 前端原地置为已取消态。

### 4.2 前端原地 Patch 状态机
前端 `AssistantStatusDrawer.tsx` 严格采用增量 patch 状态更新：
```ts
const handleActivityUpdated = useCallback((patch: ActivityItem) => {
  setActivities(prev => {
    const index = prev.findIndex(item => item.id === patch.id);
    if (index >= 0) {
      const updated = [...prev];
      updated[index] = { ...updated[index], ...patch };
      return updated;
    }
    return [patch, ...prev];
  });
}, []);
```

### 4.3 状态快照 API (`GET /lca-api/v1/assistants/{id}/status-snapshot`)
打开抽屉时调用，返回完整结构体以防 WS 断线漏事件：
```json
{
  "assistant_id": "architect",
  "activities": [...],
  "approvals": [...],
  "upcoming": [...],
  "identity": {
    "name": "架构小助",
    "avatar_theme": "dino",
    "files": [...]
  }
}
```

---

## 5. Upcoming、Approvals 与 Identity 协同规范

1. **Upcoming 任务视图**：
   - 严格对接 ADR-0268 `cron.list` 投影与 run 历史；
   - **编辑走聊天草稿**：点击 Edit 按钮自动调用 `handleTriggerChatEdit('把每天 9 点的晨报改到 8 点')`，将草稿消息填入聊天富文本输入框并聚焦，由模型追问确认并调用 `cron.update`；
   - **系统任务防删**：对 `is_system === true` 的任务，前端禁用或拦截删除，提示 `系统任务不可删除`，后端同步强校验拦截。
2. **Approvals 审批队列**：
   - 对接 `ApprovalPolicyEngine`，展示待决审批列表，提供 Allow / Deny 交互回注。
3. **Identity 身份中心**：
   - 保持 2 列网格卡片布局，支持直接点击弹窗编辑 `IDENTITY.md`、`SOUL.md`、`MEMORY.md`。

---

## 6. 测试不变量矩阵 (Invariants in Tests, AP-02)

| 编号 | 不变量名称 | 验证方式与预期断言 |
|---|---|---|
| **INV-01** | 单轨事实与投影纯函数性 | `ActivityProjector` 从 Session/Spine 事件流投影，多次重放结果严格一致，严禁创建平行事实持久化存储 |
| **INV-02** | 动作起点锁定人话标题 | 动作在进入 `running` 状态时，`title` 必须命中人话规则字典，断言绝不出现裸内部命令（如 `hatch_gws_cli`） |
| **INV-03** | 增量 Patch 幂等性 | 针对同一 `id` 无论收到多少次重复事件，时间线行数恒定不变，状态严格按 `running` -> `completed`/`failed`/`cancelled` 流转 |
| **INV-04** | 真实 Stop 取消与日志闭环 | 对 `running` 动作发出取消命令，底层必须真正终止对应进程或异步 Task，记录落地为 `cancelled`，有据可查 |
| **INV-05** | Upcoming 聊天草稿与系统防删 | 验证 Edit 正确构造自然语言聊天草稿；删除 `is_system` 任务必遭类型化拦截 |
| **INV-06** | 快照降级与最终一致性 | 离线状态打开抽屉拉取 Snapshot API，数据与后端单轨真值 100% 吻合 |
