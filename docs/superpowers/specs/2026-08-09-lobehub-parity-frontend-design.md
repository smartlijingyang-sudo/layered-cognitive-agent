# Design: LCA Web 全页对齐 LobeHub（Chat 壳 + SSE 过程渲染）

**Status:** Implemented (frontend Phase 1–2 + deepen: ToolStarted / Reasoning* / historical journal replay)  
**Date:** 2026-08-09  
**Source of truth for UX:** `/home/lichao/lobehub` Conversation / ChatInput / Agent layout / DESIGN.md  
**Source of truth for data:** LCA Journal-as-Truth（ADR-0037 / 0041 / 0045 / 0044）

---

## 1. 目标

把 LCA `web/` 从「能用的简陋对话壳」提升为 **LobeHub 级 Chat 产品观感与交互**，在**不引入第二套消息真相**的前提下：

1. **全页壳层**对齐 LobeHub Agent Chat：侧栏话题列表、主对话区、底栏输入、欢迎页、主题与排版。
2. **助手一轮回复**对齐 LobeHub AssistantGroup：深度思考折叠、工具/沙箱折叠卡、过程 `ProcessFold`、最终答案外露。
3. **暂不需要的产品面砍掉**（见 §3 Out of Scope），避免搬市场、记忆、社区等整站。

成功标准（可验收）：

| # | 场景 | 期望 |
|---|---|---|
| A | 空会话 | LobeHub 式居中欢迎 + 示例问题 chips，无「工程后台」感 |
| B | 侧栏 | 新建 / 选中 / 删除会话；活跃项高亮；hover 操作；窄屏抽屉 |
| C | 用户消息 | 右对齐气泡、附件 chip、次要 meta |
| D | 流式运行中 | 思考默认展开「深度思考中…」；工具/沙箱可展开并显示 live 输出 |
| E | 运行结束 | 「共运行 N 步 (duration)」收起过程；**最终答案始终在折叠外** |
| F | 输入区 | 悬浮圆角输入卡 + 底栏动作（模式/附件）+ 圆形发送/停止 |
| G | 主题 | 明暗语义 token 对齐 LobeHub calm / content-first |
| H | 开发者 | 完整 journal 轨迹仅 developer 模式（右侧或折叠），不污染主对话 |

---

## 2. 非目标（本阶段明确不做）

LobeHub 整站能力极大；以下 **Out of Scope**，UI 不预留假入口：

- Agent 市场 / 社区 / MCP 商店 / Provider 配置页  
- 记忆（identities/preferences/experiences）全套  
- 图像/视频创作路由、Page Editor、Tasks 工作台  
- 多 Workspace / 协作权限 / 热键全家桶  
- 分享海报 / 反应 emoji / 消息分支编辑  
- 引入 `@lobehub/ui` / `@lobehub/editor` 依赖（用现有 React + Tailwind + Radix **复刻交互与视觉语义**）  
- 虚拟列表到万级消息（保持当前 stick-to-bottom；后续可加）

「暂时用不到」= **不实现**，不是「做半截按钮」。

---

## 3. 架构原则

### 3.1 双源纪律

| 层 | 职责 | 禁止 |
|---|---|---|
| **Journal SSE** | 唯一运行时真相 | 前端从 raw token「考古」语义（ADR-0045） |
| **TurnTimelineProjector** | journal → 有序 typed blocks | 在 React 组件里拼业务状态机 |
| **ChatProjector** | 用户可见 answer 主线 | 与 timeline 抢权威正文 |
| **TraceProjector** | 开发者轨 | 作为默认用户 UI |

### 3.2 取优不照搬

- **取自 LobeHub：** ProcessFold / Thinking / Tool Accordion / splitFinalAnswer / Chat 壳布局 / DESIGN token 语义  
- **保留 LCA：** 五层依赖、Journal 词表、Team 协作叙事、sandbox stream seal、contracts 生成  

### 3.3 可维护性

- 投影器 **纯函数 + 单测**  
- UI **`BLOCK_RENDERERS` 注册表**，禁止巨型 switch 膨胀  
- 样式 **语义 CSS 变量**（对齐 DESIGN.md 命名思想），组件不写死 hex  
- 单文件 < 1500 行、单方法 < 200 行（AGENTS.md）

---

## 4. 页面信息架构

对齐 LobeHub Agent Chat 的三栏心智（Portal 在 LCA 映射为可选开发者轨）：

```text
┌────────────┬──────────────────────────────┬─────────────────┐
│  SideNav   │  ChatMain                    │  DevPortal*     │
│  (会话列表) │  ┌ Header (标题/模式)        │  (developer only)│
│            │  │ Thread (消息)             │  journal / 时序  │
│  + 新建    │  │   UserBubble              │                 │
│  会话项…   │  │   AssistantTurnView       │                 │
│            │  │     ProcessFold?          │                 │
│  设置入口  │  │     FinalAnswer           │                 │
│  (精简)    │  └ Composer (底栏输入卡)      │                 │
└────────────┴──────────────────────────────┴─────────────────┘
* DevPortal：仅 developerMode；桌面显示，移动端不占默认布局。
```

与现状映射：

| 现状 | 目标 |
|---|---|
| 顶栏堆 LLM/开发者/详细度/主题 | **顶栏极简**或并入侧栏底部设置；主视觉给对话 |
| `TraceAccordion` 挂在每条助手消息下 | 主路径改为 **Turn 过程块**；完整轨迹进 DevPortal |
| Composer 功能齐但观感偏工具条 | LobeHub 式 **圆角输入卡 + ActionBar + SendArea** |
| Welcome 已有 | 加强排版/间距/chip，对齐 OpeningQuestions |

---

## 5. 设计系统（Token）

以 LobeHub `DESIGN.md` / `DESIGN.dark.md` 为语义合同，映射到 `web/src/tokens/design-tokens.css`：

| LobeHub 语义 | LCA CSS 变量（目标） |
|---|---|
| colorBgLayout | `--bg` |
| colorBgContainer | `--surface` |
| colorBgContainerSecondary | `--surface-secondary` |
| colorBgElevated | `--surface-elevated` |
| colorText / Secondary / Tertiary / Quaternary | `--text` / `--text-muted` / `--text-faint` / `--text-disabled` |
| colorBorder / Secondary | `--border` / `--border-subtle` |
| colorFill* | `--fill` / `--fill-secondary` / `--fill-hover` |
| colorPrimary（默认近 mono） | `--accent`（LCA 可保留轻微 brand 绿，但主文字区保持中性） |
| fontFamily Geist 栈 | `--font-sans` 改为接近 Geist / system 栈 |
| radius 4/6/8/12 | 统一到 XS/SM/MD/LG 刻度 |
| shadow tertiary/secondary | `--shadow-card` / `--shadow-popover` |

原则：**内容优先、大留白、颜色只表状态**。主对话区背景接近 layout，气泡与输入卡用 container 抬升。

---

## 6. 模块设计

### 6.1 Shell

**`AppLayout` 重构：**

- 左侧 `ConversationSidebar` 固定宽 ~260–280px，背景 container secondary，列表 item hover fill  
- 主区无厚重顶栏；可选 **ChatHeader**：会话标题 + 收起侧栏 + 更多菜单（主题/开发者/详细度）  
- 移动：侧栏抽屉 + 遮罩（保留）  

**`ConversationSidebar`：**

- 顶：Logo/产品名 + 「新对话」主按钮  
- 列表：标题单行 truncate、相对时间或轮次、active 左边强调或 fill  
- 底：主题切换、开发者模式、详细度（从顶栏迁入）  

### 6.2 Thread

**`ThreadView`：**

- 空：`WelcomePanel`（Opening questions）  
- 有消息：`UserBubble` + `AssistantTurnView` 交替  
- stick-to-bottom + 「回到底部」FAB（已有，样式对齐）  

**`UserBubble`：** 右对齐、较大圆角、次要 mode 标签弱化。

**`AssistantTurnView`（新建，替换主路径上的简陋 bubble 过程区）：**

```text
[运行中]
  blocks… (thinking / casting / tool / sandbox / delegation …)
  answer streaming
[结束后 + 有 process]
  ProcessFold(title=共运行 N 步 · duration)
    blocks…
  FinalAnswer
```

### 6.3 Turn Timeline Projector（核心）

**输入：** `readonly StampedEvent[]`（+ 可选 wall-clock 用于 duration）  
**输出：**

```ts
type TurnBlock =
  | { kind: "casting"; ... }
  | { kind: "thinking"; content: string; status: "streaming" | "done"; durationMs?: number }
  | { kind: "tool"; toolName: string; status: "running" | "ok" | "error"; ... }
  | { kind: "sandbox"; invocationId: string; streams: { stdout; stderr }; sealed: boolean }
  | { kind: "delegation"; ... }
  | { kind: "decision"; ... }  // 非终态过程步，可折叠摘要
  | { kind: "answer"; text: string; streaming: boolean };

interface TurnTimeline {
  process: TurnBlock[];      // 不含最终 answer
  finalAnswer: string;
  finalAnswerStreaming: boolean;
  stepCount: number;
  durationMs?: number;
  phase: RunPhase;
  status: TurnStatus-like;
  files: GeneratedFile[];
}
```

**`splitFinalAnswer`：** 移植 LobeHub `segments.ts` 语义——最后连续 answer 外露；前后过程进 fold。

**`shouldFoldProcess`：** 非 generating、有 process、有可渲染 final answer 时折叠。

**思考内容策略（优雅降级）：**

1. 若未来有 `ReasoningDelta` / reasoning 字段 → 真思维链  
2. 否则：`DecisionMade.rationale_preview` + 非终态步的中间叙述  
3. 再否则：casting/协作阶段用状态文案，不硬编假思考  

### 6.4 UI 组件（LobeHub 交互语义）

| 组件 | 对齐源 | 行为 |
|---|---|---|
| `ThinkingPanel` | `components/Thinking` | 进行中默认展开 + shiny 标题；结束后可收起；max-height 滚动 |
| `ProcessFold` | `ProcessFold.tsx` | Accordion「共运行 N 步 (duration)」 |
| `ToolCallCard` | `Messages/Tool` + Inspector | 状态点 + 标题 + 耗时；展开 args/result |
| `SandboxPanel` | sandbox tool 体验 | mono 终端区；live 自动展开；seal 后可收 |
| `DelegationCard` | LCA 自有 | 委派 ⇢/⇠，纳入 process |
| `FinalAnswer` | DisplayContent | Markdown + 流式 |
| `Composer` | ChatInput Desktop | 圆角卡、ActionBar、Send 圆钮 |
| `ChatHeader` | Agent Header 精简版 | 标题 + 设置菜单 |

文案（中文，对齐 lobe locales）：

- `深度思考中…`  
- `已深度思考` / `已深度思考（用时 X.X 秒）`  
- `共运行 {{count}} 步` / `共运行 {{count}} 步 ({{duration}})`  

### 6.5 Composer

- 结构：`Attachment 行 | Textarea | ActionBar(模式/附件按钮) + Send/Stop`  
- 视觉：大圆角、细 border、focus ring 轻、底 footnote 更淡  
- 行为：Enter 发送 / Shift+Enter 换行；busy 时 Stop；LLM 不可用禁用  
- 不做：富文本编辑器、技能拖放、fullscreen 输入（Out of Scope）

### 6.6 Journal 增强（按需，非前置大爆炸）

优先保证 UI 可落地；缺口再动 contracts：

| 优先级 | 变更 | 用途 |
|---|---|---|
| P0 | 保证 `ToolInvoked.invocation_id` 与 sandbox delta 一致写入 | 工具卡嵌沙箱流 |
| P1 | `ToolStarted`（name, args preview, invocation_id） | 运行中工具卡 |
| P2 | 更长的 args/result 截断策略（仍走 AttributePolicy） | 折叠详情可读 |
| P3 | Reasoning 事件或 LlmCall 上 reasoning 字段 | 真·深度思考 |

原则：**有缺口才加事件**；投影层对缺失字段降级，不崩。

---

## 7. 目录结构（目标）

```text
web/src/
  tokens/design-tokens.css          # 对齐 DESIGN 语义
  projectors/
    chat-projector.ts               # answer 主线（保留）
    trace-projector.ts              # dev（保留）
    turn-timeline-projector.ts      # 新增
    turn-timeline-projector.test.ts
    types.ts                        # + TurnBlock / TurnTimeline
  components/
    layout/                         # AppLayout, ChatMain, ChatHeader
    sidebar/                        # ConversationSidebar
    composer/                       # Composer, ModePicker, Attachment
    thread/
      ThreadView.tsx
      UserBubble.tsx
      AssistantTurnView.tsx         # 新增主路径
      welcome/WelcomePanel.tsx
    turn/                           # 新增：过程块渲染
      ProcessFold.tsx
      ThinkingPanel.tsx
      ToolCallCard.tsx
      SandboxPanel.tsx
      DelegationBlock.tsx
      FinalAnswer.tsx
      block-registry.tsx
    trace/                          # DevPortal only
  renderers/                        # 逐步收敛：事件卡仅 dev 轨使用
```

依赖方向：`transport → projectors → components`；components 不 import gateway。

---

## 8. 分阶段交付

### Phase 1 — 壳与视觉（无协议改动）

- Token / 字体 / 阴影 / 间距  
- AppLayout + Sidebar + ChatHeader 重排  
- Composer / Welcome / UserBubble 视觉对齐  
- Dev 控件迁出顶栏  

**验收：** 静态页面并排 LobeHub 截图，壳层「不像后台」。

### Phase 2 — Turn Timeline UI（现有 journal）

- `TurnTimelineProjector` + 单测  
- `AssistantTurnView` + Thinking / ProcessFold / Tool / Sandbox / Delegation  
- 主路径去掉「简陋 TraceAccordion」；dev 模式保留完整轨迹  

**验收：** 真实 run 过程折叠与答案外露；沙箱 live 可见。

### Phase 3 — Journal 补齐（可选同 PR 或紧随）

- ToolStarted / invocation 关联 / preview 长度  
- 若有模型 reasoning 通道再挂真思考  

**验收：** 工具卡在完成前出现；详情区可读。

### Phase 4 — 抛光

- 动效（shiny thinking、fold 过渡、reduced-motion）  
- 空态/错误态/停止生成  
- 可访问性（accordion keyboard、对比度）  

---

## 9. 测试策略

| 层 | 内容 |
|---|---|
| 投影器 | split/fold 规则、sandbox seal、answer 权威、乱序 delta |
| 组件 | Thinking 文案状态、ProcessFold 开合、Tool 状态色 |
| 回归 | 现有 chat-projector / extract-decision-text / files 测试全绿 |
| 手动 | 对照 LobeHub：空页、一轮 tool+sandbox、结束后 fold |

门禁（AGENTS.md）：`ruff` / `lint-imports` / `mypy` / `pytest`；web：`npm test` + `npm run build`。

---

## 10. 风险与决策

| 风险 | 缓解 |
|---|---|
| 无真 reasoning 流时「深度思考」空洞 | 降级 rationale/状态文案；有事件再升级 |
| 过程块过多刷屏 | 结束后默认 ProcessFold；运行中可按 kind 折叠策略 |
| 与 TraceAccordion 双 UI | 主路径只保留 TurnView；trace 仅 dev |
| 范围膨胀回 LobeHub 整站 | §2 Out of Scope 硬砍 |
| 复制 LobeHub 代码授权/耦合 | 不 copy 包；复刻交互与结构，自有实现 |

---

## 11. 决策记录（已与产品对齐）

1. **高度完全复刻体验**，架构取 LCA 优雅处（Journal 投影，不双写 message store）。  
2. **前后端可一起改**，但 journal 只在缺口处增强。  
3. **全页壳 + 对话渲染**都要对齐；暂时用不到的 LobeHub 功能不做。  

---

## 12. 下一步

1. 用户确认本 spec。  
2. 写 `docs/superpowers/plans/2026-08-09-lobehub-parity-frontend-plan.md`（可执行任务清单）。  
3. 按 Phase 1 → 2 → 3 实现；每阶段可独立验收。
