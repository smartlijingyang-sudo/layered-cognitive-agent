# Message-Based Turn Projection — LobeHub 完美对齐设计

## 1. 背景与动机

### 问题

1. **格式丢失**：`normalizeChatMarkdown()` 激进归一化破坏 LLM 输出的 markdown 结构，导致最终回答渲染为纯文本（`=====` 分隔线、`·` 子列表等无法被 ReactMarkdown 识别）
2. **信息隐藏**：`ProcessFold` 折叠所有过程信息，用户看不到工具调用、思考等中间步骤的独立展示
3. **与业界脱节**：LobeHub / ChatGPT / Claude 均采用消息流式展示，每步独立可见

### 目标

完美对齐 LobeHub 的消息渲染模式：
- 每条推理步骤（思考、工具调用、委派）是独立的可视化消息
- 最终回答始终在过程消息之外，markdown 完美渲染
- 流式体验逐字出现，带光标动画
- 过程消息可折叠，但不隐藏

---

## 2. 架构决策

### 2.1 数据模型：混合 Turn + Message

**选择**：保留 `Turn` 作为顶层容器（对应用户问题），内部投影为 `Message[]`。

**理由**：
- Turn 对应用户问题，天然分隔不同 run
- Message 对应 LLM 响应步骤，对齐 LobeHub 消息流
- 团队模式友好（多个 agent 的消息在一个 Turn 内）
- 保留 journal-as-truth 架构（ADR-0037），只改投影层

### 2.2 Markdown 处理：完全信任 LLM

**选择**：删除 `normalizeChatMarkdown()`，仅保留 `sanitizeAssistantDisplayText()` 去除 decision JSON 外壳。通过 prompt 约束确保 LLM 输出标准 markdown。

**理由**：
- LobeHub / ChatGPT / Claude 都信任 LLM 输出
- 归一化层是 bug 来源，不是价值来源
- 职责清晰：prompt 负责格式，渲染器负责展示

### 2.3 组件策略：复用现有渲染组件

**选择**：现有 `ThinkingPanel` / `ToolCallCard` / `WorkflowCollapse` / `SandboxPanel` / `ProcessFold` 已经很 LobeHub，不改视觉，只改数据源从 `Block` 变为 `Message`。

**理由**：
- 现有组件已经实现了 LobeHub 风格的折叠、动画、特化渲染
- 重写是浪费，适配是正道
- 降低迁移风险

---

## 3. 数据模型

### 3.1 Message 类型系统

```typescript
type MessageKind =
  | "casting"        // 智能选角（团队模式）
  | "thinking"       // 思考过程（按 agent 分离）
  | "tool_call"      // 工具调用
  | "sandbox"        // 沙箱执行
  | "delegation"     // 委派（扁平化）
  | "synthesis"      // 综合收口
  | "answer"         // 最终回答（markdown）
  | "error"          // 错误
  | "insight";       // 洞察

interface Message {
  readonly id: string;
  readonly kind: MessageKind;
  readonly agentRole?: string;
  readonly content: string;
  readonly streaming: boolean;
  readonly status: "running" | "done" | "error";
  readonly startedAt: number;
  readonly completedAt?: number;
  readonly metadata?: MessageMetadata;
}

interface MessageMetadata {
  // tool_call
  readonly toolName?: string;
  readonly argumentsPreview?: string;
  readonly resultPreview?: string;
  readonly latencyMs?: number;
  readonly ok?: boolean;
  readonly error?: string;
  readonly invocationId?: string;

  // thinking
  readonly durationMs?: number;

  // casting
  readonly governanceKind?: string;
  readonly leadRole?: string;
  readonly selectedRoles?: readonly string[];
  readonly rationale?: string;
  readonly objectivePreview?: string;

  // delegation
  readonly calleeRole?: string;
  readonly subtaskPreview?: string;
  readonly delegationId?: string;
  readonly fromRole?: string;

  // sandbox
  readonly stdout?: string;
  readonly stderr?: string;
  readonly sealed?: boolean;

  // error
  readonly errorMessage?: string;

  // insight
  readonly insightKind?: string;
  readonly summary?: string;
  readonly detail?: string;

  // synthesis
  readonly method?: string;
  readonly candidateCount?: number;
}
```

### 3.2 Turn 容器

```typescript
interface Turn {
  readonly id: string;
  readonly runId: string;
  readonly question: string;
  readonly mode: "solo" | "team";
  readonly messages: readonly Message[];    // 按排序规则排列
  readonly status: "running" | "completed" | "failed";
  readonly startedAt: number;
  readonly completedAt?: number;
  readonly teamId?: string;
  readonly errorMessage?: string;
}
```

### 3.3 消息排序规则

```typescript
function sortMessages(messages: readonly Message[]): readonly Message[] {
  return [...messages].sort((a, b) => {
    // 运行中的消息始终在已完成的之后
    const aRunning = a.status === "running" ? 1 : 0;
    const bRunning = b.status === "running" ? 1 : 0;
    if (aRunning !== bRunning) return aRunning - bRunning;

    // 已完成的按 completedAt 排序（先完成的先显示）
    if (a.completedAt && b.completedAt) {
      return a.completedAt - b.completedAt;
    }

    // 运行中的按 startedAt 排序
    return a.startedAt - b.startedAt;
  });
}
```

### 3.4 投影器接口

```typescript
interface MessageProjector {
  start(question: string, mode: "solo" | "team"): void;
  onEvent(stamped: StampedEvent): Turn;
  snapshot(): Turn;
}
```

---

## 4. 投影管线

### 4.1 事件 → 消息映射

| Journal Event | Message Kind | 行为 |
|---------------|-------------|------|
| `CastingStarted` | `casting` | 创建 casting 消息 (status: running) |
| `CastingCompleted` | `casting` | 更新 casting 消息 (status: done, metadata 填充) |
| `CastingFailed` | `error` | 创建 error 消息 |
| `ReasoningDelta` | `thinking` | 按 (runId, agentRole) 查找/创建，追加 text_delta |
| `ReasoningCompleted` | `thinking` | 标记 streaming=false, 填充 durationMs |
| `ToolStarted` | `tool_call` | 创建 tool_call 消息 (status: running) |
| `ToolInvoked` | `tool_call` | 更新 tool_call 消息 (status: done/error, 填充 result) |
| `SandboxOutputDelta` | `sandbox` | 按 (runId, invocationId, stream) 查找/创建，追加 delta |
| `DelegationIssued` | `delegation` | 创建 delegation 消息 (status: running) |
| `DelegationCompleted` | `delegation` | 更新 delegation 消息 (status: done, 填充 result) |
| `StepTextDelta` | `answer` | 按 (runId, step) 查找/创建，追加 text_delta |
| `DecisionMade` (respond) | `answer` | 标记 streaming=false, canonical response_text 优先 |
| `SynthesisCompleted` | `synthesis` | 创建 synthesis 消息 |
| `RunInsight` | `insight` | 创建 insight 消息 |

### 4.2 消息去重与合并

- **thinking**：按 `(runId, agentRole)` 键去重，同一 agent 的多个 ReasoningDelta 合并到同一条消息
- **tool_call**：按 `invocationId` 去重，ToolStarted 创建 → ToolInvoked 更新
- **sandbox**：按 `(runId, invocationId, stream)` 去重
- **delegation**：按 `delegationId` 去重
- **answer**：按 `(runId, step)` 去重，DecisionMade.response_text 优先于 StepTextDelta 缓冲

### 4.3 流式状态管理

```typescript
// 内部状态（不暴露给 UI）
interface InternalMessage extends Message {
  buffer: string;          // 累积的文本缓冲
  deltaSeq: number;        // 最后一个 delta 的 seq
}

// 流式追加示例
case "ReasoningDelta": {
  const key = `thinking:${runId}:${role}`;
  const msg = internalMessages.get(key) ?? createThinkingMessage(runId, role);
  msg.buffer += e.text_delta;
  msg.content = msg.buffer;
  msg.streaming = true;
  msg.deltaSeq = e.seq;
  return buildTurn(internalMessages);
}

case "ReasoningCompleted": {
  const key = `thinking:${runId}:${role}`;
  const msg = internalMessages.get(key);
  if (msg) {
    msg.streaming = false;
    msg.completedAt = ts;
    msg.metadata = { ...msg.metadata, durationMs: e.duration_ms };
  }
  return buildTurn(internalMessages);
}
```

---

## 5. 渲染组件

### 5.1 组件复用策略

现有渲染组件已经很 LobeHub，不改视觉，只改数据源：

| 现有组件 | 数据源（旧） | 数据源（新） | 改动范围 |
|---------|------------|------------|---------|
| `ThinkingPanel` | `ThinkingBlock` | `Message` (kind=thinking) | 接口适配 + agentRole 标签 |
| `ToolCallCard` | `ToolBlock` | `Message` (kind=tool_call) | 接口适配，metadata 映射 |
| `WorkflowCollapse` | `ToolBlock[]` | `Message[]` (kind=tool_call) | 接口适配 |
| `SandboxPanel` | `SandboxBlock` | `Message` (kind=sandbox) | 接口适配 |
| `ProcessFold` | `ReactNode children` | `Message[]` → `MessageRenderer[]` | 内部渲染切换 |
| `MarkdownContent` | `string` | `string` | 删除 normalizeChatMarkdown 调用 |
| `StatusBlock` | `variant` | `variant` | 不变 |
| `CodeHighlight` | `code, language` | `code, language` | 不变 |
| `AnsiOutput` | `text` | `text` | 不变 |

### 5.2 新增组件

```
web/src/components/thread/MessageList.tsx           // 消息列表（排序 + 分组）
web/src/components/thread/MessageRenderer.tsx       // 消息分发渲染器
web/src/components/thread/messages/
  ├── CastingMessage.tsx        // 选角消息（复用 CastingCard 逻辑）
  ├── DelegationMessage.tsx     // 委派消息（复用 DelegationCard 逻辑）
  ├── SynthesisMessage.tsx      // 综合消息
  ├── AnswerMessage.tsx         // 最终回答（包装 MarkdownContent）
  ├── ErrorMessage.tsx          // 错误消息
  └── InsightMessage.tsx        // 洞察消息（复用 InsightCard 逻辑）
```

**不需要新建的**（复用现有组件）：
- `ThinkingMessage` → 直接用 `ThinkingPanel`（适配接口）
- `ToolCallMessage` → 直接用 `ToolCallCard`（适配接口）
- `SandboxMessage` → 直接用 `SandboxPanel`（适配接口）

### 5.3 MessageRenderer 分发

```typescript
function MessageRenderer({ message }: { message: Message }) {
  switch (message.kind) {
    case "casting":
      return <CastingMessage message={message} />;
    case "thinking":
      return <ThinkingPanel block={toThinkingBlock(message)} />;
    case "tool_call":
      return <ToolCallCard block={toToolBlock(message)} sandbox={findSandbox(message)} />;
    case "sandbox":
      return <SandboxPanel block={toSandboxBlock(message)} />;
    case "delegation":
      return <DelegationMessage message={message} />;
    case "synthesis":
      return <SynthesisMessage message={message} />;
    case "answer":
      return <AnswerMessage message={message} />;
    case "error":
      return <ErrorMessage message={message} />;
    case "insight":
      return <InsightMessage message={message} />;
    default:
      return null;
  }
}
```

**适配器函数**（`toThinkingBlock` / `toToolBlock` / `toSandboxBlock`）将 `Message` 映射回现有组件期望的 `Block` 接口，实现零改动复用。

### 5.4 MessageList 布局

```tsx
function MessageList({ turn }: { turn: Turn }) {
  const processMessages = turn.messages.filter(
    (m) => m.kind !== "answer" && m.kind !== "insight"
  );
  const answerMessages = turn.messages.filter((m) => m.kind === "answer");
  const insightMessages = turn.messages.filter((m) => m.kind === "insight");
  const isDone = turn.status !== "running";

  return (
    <div className="grid gap-2.5">
      {/* 过程消息：完成后折叠 */}
      {processMessages.length > 0 && isDone ? (
        <ProcessFold stepCount={processMessages.length} durationText={...}>
          {processMessages.map((m) => (
            <MessageRenderer key={m.id} message={m} />
          ))}
        </ProcessFold>
      ) : (
        processMessages.map((m) => (
          <MessageRenderer key={m.id} message={m} />
        ))
      )}

      {/* 最终回答：始终在外部 */}
      {answerMessages.map((m) => (
        <MessageRenderer key={m.id} message={m} />
      ))}

      {/* 洞察：回答之后 */}
      {insightMessages.map((m) => (
        <MessageRenderer key={m.id} message={m} />
      ))}
    </div>
  );
}
```

### 5.5 各消息类型的 UI 细节

#### ThinkingMessage（复用 ThinkingPanel）

```
运行中：
┌──────────────────────────────────────────────────┐
│ 🧠 深度思考中…                           ▼       │  ← shiny 动画 + StatusBlock(neural)
│ ┌──────────────────────────────────────────────┐ │
│ │ 让我分析一下...（markdown 渲染）             │ │  ← MarkdownContent streaming=true
│ │ ▋                                           │ │  ← 闪烁光标
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘

完成后（折叠）：
┌──────────────────────────────────────────────────┐
│ 🧠 已深度思考（用时 3.2 秒）               ▼       │  ← muted 文字
└──────────────────────────────────────────────────┘

团队模式（按 agent 分离）：
┌──────────────────────────────────────────────────┐
│ 🧠 历史学家 · 深度思考中…                  ▼       │  ← agentRole 标签
│ ┌──────────────────────────────────────────────┐ │
│ │ 从历史角度分析...                            │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

#### ToolCallMessage（复用 ToolCallCard）

```
命令类工具：
┌──────────────────────────────────────────────────┐
│ 🔄 shell_execute · ls -la                120ms  ▼ │
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
│ 命令                                              │
│ ┌──────────────────────────────────────────────┐ │
│ │ $ ls -la              ← CodeHighlight (shiki) │ │
│ └──────────────────────────────────────────────┘ │
│ 输出                                              │
│ ┌──────────────────────────────────────────────┐ │
│ │ total 48              ← AnsiOutput            │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘

技能类工具：
┌──────────────────────────────────────────────────┐
│ 🔄 activate_skill · [📦 brainstorming]            │  ← Chip 组件
│ ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
│ ┌──────────────────────────────────────────────┐ │
│ │ brainstorming                      技能指南   │ │
│ │──────────────────────────────────────────────│ │
│ │ # Brainstorming Ideas  ← MarkdownContent      │ │
│ └──────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

#### WorkflowCollapse（多工具分组，复用现有组件）

```
流式中：
┌──────────────────────────────────────────────────┐
│ 🔄 正在搜索知识库...                     (5s)   ▼ │  ← shiny 旋转标题 + 计时器
└──────────────────────────────────────────────────┘

完成后（折叠）：
┌──────────────────────────────────────────────────┐
│ ✓ 3 次调用：搜索知识库, 读取文档, 分析    2.3s   ▼ │
└──────────────────────────────────────────────────┘

完成后（半展开 / 全展开）：
  与现有行为一致（三级展开 collapsed / semi / full）
```

#### ProcessFold（整体折叠）

```
折叠：「共运行 5 步 (12.3s)」
展开：内部渲染所有过程消息
```

---

## 6. Markdown 处理

### 6.1 删除的代码

```
web/src/lib/normalize-chat-markdown.ts          // ❌ 整个文件删除
web/src/lib/normalize-chat-markdown.test.ts     // ❌ 整个文件删除
```

### 6.2 保留的代码

```
web/src/lib/extract-decision-text.ts
  ├── sanitizeAssistantDisplayText()   // ✅ 保留（去除 decision JSON 外壳）
  ├── extractUserFacingAnswer()        // ✅ 保留（从 decision JSON 提取 response_text）
  └── extractJsonBlock()              // ✅ 保留
```

### 6.3 MarkdownContent 修改

```typescript
// 修改前
const sanitized = sanitizeAssistantDisplayText(text, streaming);
const normalized = normalizeChatMarkdown(sanitized, streaming ? "streaming" : "final");
// → ReactMarkdown renders `normalized`

// 修改后
const sanitized = sanitizeAssistantDisplayText(text, streaming);
// → ReactMarkdown renders `sanitized` directly
```

### 6.4 Prompt 约束

在 `lca/layer1_cognitive/brain/prompts/react_prompt.md` 末尾增加：

```markdown
## 输出格式

你的最终回答必须使用标准 Markdown 格式：
- 标题用 `#` / `##` / `###`，不要用 `===` 或纯文字
- 列表用 `-` 或 `1.`，不要用 `·` 或 `•`
- 加粗用 `**文字**`，不要用全角或其他符号
- 引用用 `>` 前缀
- 代码用 ``` 围栏
- 表格用 `| col | col |` 语法
```

---

## 7. 流式策略

### 7.1 消息级流式

每条消息独立追踪流式状态：

| 消息类型 | 流式方式 | 光标/动画 |
|----------|---------|----------|
| thinking | 逐字追加，实时渲染 markdown | `▋` 闪烁光标 + 自动滚动 |
| answer | 逐字追加，实时渲染 markdown | `▋` 闪烁光标 |
| tool_call | 不流式 — ToolStarted 显示 running，ToolInvoked 显示结果 | StatusBlock(neural) spinner |
| delegation | 不流式 — DelegationIssued 显示 running，DelegationCompleted 显示结果 | StatusBlock(neural) |
| sandbox | stdout/stderr 逐行追加 | 无光标，等宽字体，自动滚动 |
| casting | 不流式 — CastingCompleted 一次性显示 | StatusBlock(neural) |

### 7.2 排序策略

- 已完成的消息按 `completedAt` 排序（先完成的先显示）
- 运行中的消息按 `startedAt` 排序，放在末尾
- 确保用户看到的时间线是因果一致的

---

## 8. 迁移计划

### Phase 1：数据层（MessageProjector）

**新增文件**：
```
web/src/projectors/message-types.ts
web/src/projectors/message-projector.ts
web/src/projectors/message-projector.test.ts
docs/adr/0053-message-based-turn-projection.md
```

**并行运行**：`MessageProjector` 与 `ChatProjector` / `TurnTimelineProjector` 同时消费事件，暂不切换 UI。

**完成标准**：MessageProjector 正确归约所有 journal 事件类型，单元测试全通过。

### Phase 2：渲染层（MessageRenderer）

**新增文件**：
```
web/src/components/thread/MessageList.tsx
web/src/components/thread/MessageRenderer.tsx
web/src/components/thread/messages/CastingMessage.tsx
web/src/components/thread/messages/DelegationMessage.tsx
web/src/components/thread/messages/SynthesisMessage.tsx
web/src/components/thread/messages/AnswerMessage.tsx
web/src/components/thread/messages/ErrorMessage.tsx
web/src/components/thread/messages/InsightMessage.tsx
```

**修改文件**：
```
web/src/components/turn/ThinkingPanel.tsx      // 增加 agentRole 标签
web/src/components/shared/MarkdownContent.tsx   // 删除 normalizeChatMarkdown 调用
web/src/shell/App.tsx                           // feature flag 切换
web/src/shell/app.css                           // 新增样式（如有）
lca/layer1_cognitive/brain/prompts/react_prompt.md  // markdown 格式约束
```

**Feature flag**：`useFeatureFlag("message-renderer")` 控制新旧渲染切换。

**完成标准**：新渲染层在 feature flag 下完美运行，视觉对齐 LobeHub。

### Phase 3：清理

**删除文件**：
```
web/src/lib/normalize-chat-markdown.ts
web/src/lib/normalize-chat-markdown.test.ts
web/src/projectors/chat-projector.ts
web/src/projectors/turn-timeline-projector.ts
web/src/components/turn/AssistantTurnView.tsx
web/src/components/turn/block-registry.tsx
```

**简化 App.tsx**：只保留 `MessageProjector`。

**完成标准**：旧代码完全删除，无回归，所有测试通过。

---

## 9. 测试策略

| 层级 | 测试内容 | 工具 |
|------|---------|------|
| 单元测试 | MessageProjector 归约逻辑（每种事件类型） | Vitest |
| 单元测试 | 消息排序逻辑 | Vitest |
| 组件测试 | 各 MessageRenderer 渲染正确 | Vitest + Testing Library |
| 集成测试 | Journal 回放 → Message[] → 渲染快照 | Vitest + 现有 journal fixtures |
| 流式测试 | thinking/answer 逐字出现 | Testing Library + fake timers |
| 适配器测试 | Message → Block 适配器函数 | Vitest |

---

## 10. 文件变更总览

| 操作 | 文件 | Phase |
|------|------|-------|
| **新增** | `web/src/projectors/message-types.ts` | 1 |
| **新增** | `web/src/projectors/message-projector.ts` | 1 |
| **新增** | `web/src/projectors/message-projector.test.ts` | 1 |
| **新增** | `docs/adr/0053-message-based-turn-projection.md` | 1 |
| **新增** | `web/src/components/thread/MessageList.tsx` | 2 |
| **新增** | `web/src/components/thread/MessageRenderer.tsx` | 2 |
| **新增** | `web/src/components/thread/messages/*.tsx` (6 个) | 2 |
| **修改** | `web/src/components/turn/ThinkingPanel.tsx` | 2 |
| **修改** | `web/src/components/shared/MarkdownContent.tsx` | 2 |
| **修改** | `web/src/shell/App.tsx` | 1+2 |
| **修改** | `web/src/shell/app.css` | 2 |
| **修改** | `lca/layer1_cognitive/brain/prompts/react_prompt.md` | 2 |
| **删除** | `web/src/lib/normalize-chat-markdown.ts` | 3 |
| **删除** | `web/src/lib/normalize-chat-markdown.test.ts` | 3 |
| **删除** | `web/src/projectors/chat-projector.ts` | 3 |
| **删除** | `web/src/projectors/turn-timeline-projector.ts` | 3 |
| **删除** | `web/src/components/turn/AssistantTurnView.tsx` | 3 |
| **删除** | `web/src/components/turn/block-registry.tsx` | 3 |

---

## 11. 相关 ADR

- **ADR-0037** Journal-as-Truth — journal 仍是底层真相，本设计只改投影层
- **ADR-0041** 轨迹投影 — 投影模式不变，投影目标从 TurnTimeline 变为 Message[]
- **ADR-0045** Decision 形状归一 — response_text 仍是 answer 的权威源
