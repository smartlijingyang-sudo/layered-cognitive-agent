# LCA 前端产品化 · 第二轮走查：对齐 LobeHub 体验的收尾补丁

### 从「产品化框架已完成」到「细节手感对齐一线对话产品」

| | |
|---|---|
| 文档性质 | `docs/proposals/0001-frontend-productization.md` 的续篇 |
| 范围 | `web/` 的流式渲染细节与运行时性能；**不**改 `lca/` 认知框架本体，**不**改五层分层，**不**引入重量级依赖 |
| 走查依据 | 对当前代码快照中 `web/src/**`、`gateway/**` 的实读结果，逐条标注证据文件 |
| 前提 | 假定 `0001` 提案的 Phase 0–3 已经落地——第 1 节先逐项核实，第 2 节是本次新发现的问题 |

---

## 0. 结论先行

**`0001` 提案里的条目基本都已经做完了**——设计令牌、Tailwind v4、Zustand、多轮对话、IndexedDB 持久化、10 项协作模式契约生成、真实 token 级流式（`StepTextDelta`）、Markdown + 代码复制、取消生成、后端 SQLite 会话持久化、CI 接入 `web-quality`、内联折叠轨迹条 + `RunInsight` 头条摘要 + Mermaid 时序图，均可在代码中找到对应实现。

**本轮收尾**：5 处「做了但有代价」或「做了但没收尾」的细节，决定「像 LobeHub」还是「像调试页」的最后 10% 手感。前 4 项（§2.1–§2.3、§2.6）已落地为零依赖补丁；§2.5（持久化注释）见下文状态；§2.4（语法高亮）已由 ADR-0043 正式拍板，执行方案见 `docs/proposals/0003-markdown-files-charts-lobehub-reference.md`。

---

## 1. `0001` 条目核实（摘要）

| `0001` 条目 | 状态 | 证据 |
|---|---|---|
| 设计令牌 + 浅/深主题 | ✅ | `web/src/tokens/design-tokens.css` |
| 组件/domain/api 分层 | ✅ | `web/src/components/`、`domain/`、`api/` |
| Conversation + IndexedDB | ✅ | `domain/conversation-store.ts`、`store/app-store.ts` |
| Zustand | ✅ | `store/app-store.ts` |
| 10 项协作模式契约 | ✅ | `contracts/modes.generated.ts` |
| Markdown + 代码复制 | ✅（高亮待 §2.4） | `components/shared/MarkdownContent.tsx` |
| 轨迹条 + Insight + Mermaid | ✅ | `components/trace/TraceAccordion.tsx` |
| 取消生成 | ✅ | `gateway/app.py::cancel_run` |
| 后端 SQLite 会话 | ✅（前端读路径见 §2.5） | `gateway/conversation_store.py` |
| 真实 token 流式 | ✅ | `projectors/chat-projector.ts` |
| CI web-quality | ✅ | `.github/workflows/ci.yml` |

---

## 2. 问题与落地状态

### 2.1 【高】流式期间全量 IndexedDB 写 — ✅ 已修复

**问题**：每个 `StampedEvent` 都触发 `updateActiveTurn` → 全量 `saveConversations`。

**修复**：`patchActiveTurn`（仅内存）+ `shouldPersistTurnOnEvent`（语义边界落盘：`DecisionMade` 用户可见动作、终态事件）；运行结束仍 `updateActiveTurn` flush。

**证据**：`web/src/store/app-store.ts`、`web/src/lib/persist-turn.ts`、`web/src/shell/App.tsx`。

### 2.2 【中】自动跟随滚动 — ✅ 已修复

**修复**：`useStickToBottom` + 底部锚点 + 「回到底部」按钮；新 turn 时 `releaseStick`。

**证据**：`web/src/lib/use-stick-to-bottom.ts`、`web/src/components/thread/ThreadView.tsx`。

### 2.3 【高】流式期间不过 Markdown — ✅ 已修复

**修复**：`AssistantBubble` 在 `running` 态也通过 `useProgressiveReveal` → `MarkdownContent` 渲染；真实 delta 即时全显，假流式仍按句动画。

**证据**：`web/src/components/thread/AssistantBubble.tsx`、`web/src/components/shared/ProgressiveReveal.tsx`。

### 2.4 【中】代码块语法高亮 — ⏳ 待独立 PR

**建议**：`shiki/core` 按需语言或 `react-syntax-highlighter` + `PrismLight`，`React.lazy` 懒加载。不加完整版 shiki 默认包。

### 2.5 【低】双持久化路径注释 — ✅ 已澄清

**修复**：`gateway/conversation_store.py`、`gateway/app.py`、`web/src/domain/conversation-store.ts` 注释标明当前读路径为 IndexedDB，`/conversations` 为跨设备预留。

### 2.6 ADR-0041 状态 — ✅ 已更新为 Accepted

**证据**：`docs/adr/0041-prompt-reasoner-stream-text-delta.md`。

---

## 3. 明确不建议做的事

- 不引入 `framer-motion` 等动效库
- 不为 2.1 引入 Redux-Persist 类方案
- 不为 2.5 立刻做跨设备同步/鉴权
- 不为语法高亮引入完整 shiki 默认打包

---

## 4. 优先级与工作量

| # | 问题 | 优先级 | 状态 |
|---|---|---|---|
| 2.3 | 流式 Markdown | 高 | ✅ |
| 2.1 | IndexedDB 写降频 | 高 | ✅ |
| 2.2 | 自动跟随滚动 | 中 | ✅ |
| 2.6 | ADR-0041 | 中 | ✅ |
| 2.4 | 语法高亮 | 中 | 待 PR |
| 2.5 | 持久化注释 | 低 | ✅ |

---

## 5. 与 LobeHub 对照（摘要）

| LobeHub | LCA 现状 |
|---|---|
| Zustand 流式高频状态 | 已引入；2.1 解耦持久化后符合「轻量状态 + 语义边界落盘」 |
| SSE + 增量 Markdown | 2.3 补齐渲染层最后一环 |
| 贴底跟随 | 2.2 补齐 |
