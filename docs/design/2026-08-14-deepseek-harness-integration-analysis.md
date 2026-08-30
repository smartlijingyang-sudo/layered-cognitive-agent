# DeepSeek Harness (DSH) 对 LCA 的价值与融入方案

**日期**: 2026-08-15（整合完善）
**状态**: 分析草案（Canonical 候选）
**关联**: [lobehub-integration.md](../specs/lobehub-integration.md)

---

## 定位：各守其位

| | **DSH** | **LCA（本仓库）** |
|---|---|---|
| 是什么 | DeepSeek 开源 **coding agent harness**（Cordis 插件树 + Web/CLI/headless） | 分层认知 agent **产品栈**（Gateway + Agent/Team + Journal + LobeHub） |
| 前端 | 自带轻量 Web UI（Developer Preview） | **LobeHub v2.2.13**（成熟 chat、上传、artifact、插件） |
| 强项 | agent loop、tool pipeline、session log、provider 互换、compaction、subagent | Run Live、多执行面、附件管道、Team 协作、工具卡片投影 |
| 语言 | TypeScript（+ Python SDK 子进程） | Python（+ LobeHub TS 补丁） |

**结论（2026-08-15 验证）：**

- DSH **不能**整体替换 LCA 产品体验（无通用文件上传、无 artifact/deliverable 卡片、HTTP LAN 下 `crypto.randomUUID` 等 product gap）。
- DSH **应该**作为 **runtime 教科书 + 可选 execution driver**，LobeHub 继续当唯一 product shell。
- 价值在 **抄设计、抄管线**，不抄 Web UI，不搬 TS 源码。

私有 fork（upstream 分离、LAN 部署 patch）见 `~/deepseek-harness/FORK.md` 与 `deploy/lan/`；与本仓库代码无直接依赖，仅供对照阅读与 driver 开发。

---

## 它是什么

DeepSeek Harness 基于 Cordis，核心理念是「**一切皆插件**」：model adapter、tool registry、session log、agent loop 本身都可从配置层替换，无 privileged core。

工程上包含：完整 turn/step 生命周期、guarded tool pipeline、append-only session log、多 provider LLM seam、subagent 多后端、compaction、permission preset、skill/workflow/plan、Landlock/E2B 沙箱等。

**Python 接入**：`deepseek-harness-sdk` 经 JSON-RPC stdio 驱动 DSH 子进程；LCA 已在 `lca/infrastructure/dsh/` 落地 `DshTurnDriver`（notify → `{run_id}.dsh.jsonl` + Journal 投影）。

---

## 一、与 LCA 架构的对应关系（总表）

| LCA 概念 | DSH 对应 | 成熟度差距 | DSH 入口 |
|---|---|---|---|
| `LLMAdapter` | `ctx.llm` + `LlmAdapter` | 重试、reasoning、stream idle、empty retry、discovery | `packages/llm/llm`、`llm-pi-ai`、`llm-retry` |
| `Tool` Protocol | `ctx.tools` + `ToolDefinition` | guarded pipeline、pre/post、presentCall/Result | `docs/tool-execution-pipeline.md` |
| `Sandbox` / 执行面 | `ctx.sandbox` + `ctx.fs` + `ctx.shell` | Provider 互换（local/sandbox/e2b） | `packages/fs/*`、`packages/sandbox/*` |
| Skill | `ctx.skills` + `tool-skill` | catalog 搜索 + activate 注入 | `packages/skill/*` |
| Journal | `SessionEvent` + persistence | model-visible ⟺ logged；derive 历史 | `docs/subsystems/session.md` |
| Execution Planes | Capability Seam | 同构：换 Provider 不换 Tool schema | `docs/capability-seams.md` |
| Agent Loop | `ctx.agentLoop` | waterfall：pre-step → tool pipeline → turn-stopping | `docs/architecture.md` |
| Team / 子 Agent | `ctx.subagents` | 多 provider、continuable、report | `docs/subsystems/subagent.md` |
| 工作流 | `ctx.workflowEngine` | Rhai + worker-thread | `packages/workflow/*` |
| 权限 / HIL | `permission-presets` + `ctx.approval` | preset _bundle_ sandbox+approval，session 级 pin | `packages/interaction/permission-presets` |
| 上下文压缩 | `ctx.compaction` | pressure + tool-pairing 边界 + surface replace | `packages/compaction/*` |
| 工具 UI | `presentCall` / `presentResult` | 定义级 UI hook | 各 `tool-*` + `tool_ui` 投影 |
| 产品附件/产出 | （弱）仅图片 composer | LCA 强：FileStore、artifact、LobeHub 下载 | `packages/attachment/*`（images only） |

---

## 二、可借鉴机制（分项详解）

### 2.1 Capability Seam：三角色（顶层设计，P1）

DSH 每个能力固定三角色；LCA Protocol 多为 Definition + 实现绑死。

| 角色 | DSH 例 | LCA 目标 |
|---|---|---|
| Service Definition | `ctx.fs`、`ctx.shell` | `ComputerOps`、`Sandbox` Protocol（加厚） |
| Service Provider | `fs-local` / `fs-sandbox` / `fs-e2b` | `MachineComputer` / `SandboxComputer` / 可选 `DshComputer` |
| Consumer | `tool-fs` read/write/edit | `computer_tool_set()` 从 Tool 类拆出 |

与 `execution-planes-design` 同构：**Consumer 对模型不变，Provider 随 execution_target 切换**。DSH 是该模式的参考实现。

### 2.2 Session Log 与 Journal（P1–P2）

DSH 硬规则：**model-visible ⟺ logged**；LLM 历史由 log **derive**，不单独存副本。

| 机制 | DSH | LCA 现状 | 借鉴动作 |
|---|---|---|---|
| 生命周期 | `turn/start` → `step/*` → `turn/end` | Run 级，turn/step 边界模糊 | Journal 引入 turn/step 帧或元数据 |
| 工具时序 | `tool/call` **先于** execute 落 log | 多事后投影 | pending card 可对齐 call 事件 |
| 流式 | `assistant/chunk` + `assistant/message` 双轨 | SSE 投影够用，缺 replay 语义 | 长 run 可考虑 chunk 归档 |
| 对照源 | JSONL/SQLite 单一事实源 | Journal + 可选 jsonl | **已做**：`DshTurnDriver` 双轨 `{run_id}.dsh.jsonl` + Journal |

```text
DshTurnDriver（已实现）:
  on_event → archive.append + projector.feed
  finish → Journal 终态
```

长期：Journal 事件词汇向 DSH `SessionEventMap` 靠拢，保证 fork/replay/compaction 同一套语义。

### 2.3 Tool Execution Pipeline（P1，工程差距最大）

管道（`docs/tool-execution-pipeline.md`）：

```text
tool/call → presentCall → pre-execute → guards → approval
  → execute(timeout) → tool body → fs/write-intent
  → post-execute → finalizeContent → tools/result → tool/result → presentResult
```

LCA：`tool_ui_state` / `tool_ui_builders` 管**展示**；execute 侧 approval 分散在 `ask_user`、`plane.scope` 等，**无统一 pre/post 管道**。

| DSH 包/机制 | 行为 | LCA 落点 |
|---|---|---|
| `tool-fs` | read-before-write | layer0 写/编辑工具前查「是否读过」 |
| `tool-call-timeout-policy` | cooperative timeout + 硬 kill | bash/沙箱/DSH 子进程统一 |
| `tools/post-execute` | additionalContexts FIFO 注入 | 工具链上下文不进 result 字符串 |
| `presentCall` / `presentResult` | 定义级 UI hook | 吸收进 `tool_ui_builders`，挂钩 execute 前后 |
| Code Mode `run_code` | 子调用重进完整 pipeline | 复杂多步可选模式 |

### 2.4 权限 Preset（P2）

`permission-presets`：sandbox mode + approval policy **绑成 preset**（如 `workspace-write`、`danger-full-access`），**创建 session 时 pin 进 log**，之后改 settings 不影响已开 session。

LCA：`path_needs_approval`、HIL `approval_request`、plane 分散；缺「用户选一档权限模型」的产品抽象。

**借鉴**：LobeHub 输入栏「权限档位」chip → Run 首帧写入 Journal → 映射 Onlyboxes/machine 策略表。

### 2.5 执行面与文件工具（P1）

Provider 互换示例：

```text
ctx.fs ← fs-local | fs-sandbox | fs-e2b
ctx.shell ← bash-local | sandbox-wrapped
```

| DSH 包 | 借鉴点 |
|---|---|
| `tool-fs-search` | 内置 `@vscode/ripgrep`，不依赖宿主机 `rg` |
| `spill-local` | grep/glob 超限结果落盘，模型看摘要 + locator |
| `tool-bash` | sandbox + background job |
| `tool-terminal` | **持久 PTY**（非每次 bash -c） |
| `sandbox-policy` | per-session 不可变 workspace root |

与 LCA `machine` / `sandbox` / `dsh` 三 execution_target **同构**；DSH 是 provider 切换的完整样本。

### 2.6 Compaction + Token Meter（P2，LCA 空白）

`ctx.compaction`：`compactIfNeeded(pressure|context-overflow)`、`compactNow`；**tool-pairing 边界**（压缩点不切断未闭合 tool call/result）；摘要以 `surfaceOp: replace` 写回 surface，log 全保留。

LCA：ingress `MAX_HISTORY_CHARS` 截断；**无**摘要替换 + tool 配对保护。

**最小落地**：pressure 检测 → 旧 turn 摘要 → 保证 tool call/result 不跨边界截断。

### 2.7 LLM Adapter 工程细节（P2）

| 能力 | DSH | LCA |
|---|---|---|
| 多 provider 路由 | settings 热更新 `llm-pi-ai` | `llm_resolver` + OPENAI/Anthropic face |
| 重试 | `llm-retry` normal/always | 弱 |
| Credential | ref 分层：env → yaml → project/user `.env` |  mainly `.env` |
| Discovery | catalog + custom provider | 手动 |

**借鉴**：credential ref（settings 只存引用）；provider 级 `api` 字段文档化（与 Qwen 双 face 对齐）。

### 2.8 Subagent / Team（P3）

`ctx.subagents` **多 provider 共存**：spawn-in-process、fork、acp、codex、claude-code、dsh-sdk；continuable 子 agent；`send_message` / `interrupt_agent` / `report`。

LCA Team：routing/board/pipeline 在 layer1，无「spawn 独立 coding 子进程并多轮对话」seam。

**借鉴（不替换 Team）**：FanOut 成员可选 DSH one-shot；长任务简化为「子 Run + 独立 run_id」。

### 2.9 Agent Preset（P3）

DSH preset = 每 session 选能力裁剪（工具集、prompt 段、skill 层）。Web UI 选「标准 / 极简」。

LCA：Agent YAML + execution_target；缺 per-run 轻量/重量工具面产品入口。

**借鉴**：LobeHub chip「研究型 / 编码型 / 只读型」→ tool allowlist + prompt pack → Run 元数据。

### 2.10 Skill / Workflow / Plan（P4）

| DSH | LCA |
|---|---|
| `tool-skill` activate 链路 | role/skill 概念，无统一 activate |
| `workflowEngine` + Rhai | 无声明式脚本编排 |
| `plan-mode` 落 log | 无一等 plan 对象 |

Workflow 补 Team **固定 SOP** 场景；非替代 Pipeline/FanOut。

### 2.11 工程纪律（持续）

| 实践 | DSH | LCA 可跟 |
|---|---|---|
| 生成 catalog | tool/config/persistence catalog | Journal 事件 catalog codegen |
| Snapshot 测试 | headless/ACP golden，无 key CI | 投影快照测试扩展 |
| Agent Notes | `.agents/notes/` 记 WHY | ADR + superpowers specs |
| `dsh --dump-config` | 组合树可 diff | `lca-ops` 暴露 effective config |

---

## 三、明确不从 DSH Web 借鉴的（产品边界）

| 能力 | DSH Web | LCA + LobeHub |
|---|---|---|
| 文件上传 | **仅图片**（`ui-attachment` README 写明 deferred） | 完整 file + `<file>` 解析 + FileStore |
| 生成物展示 | 工具 result card，无 artifact 下载流 | `lcaArtifacts`、`collectArtifactFiles`、下载链接 |
| 前端成熟度 | Developer Preview | 产品化 v2.2.13 |
| LAN HTTP | 非安全上下文需 UUID 回退（已 fork patch） | Gateway + 既有部署 |

**路径 C 修订**：DSH Web **不**作为 LCA 前端替代；仅作 harness 对照与 driver 源码阅读。前端永远是 LobeHub。

---

## 四、四种融入路径（由浅入深，修订版）

### 路径 A：DSH 作为 execution driver（**当前 Canonical，最低风险**）

见对比跑道设计（已归档）。

```text
chip「用 DSH」→ POST /runs {execution_target: dsh}
  → DshTurnDriver（跳过 Agent/Team 主循环）
  → Qwen 走 LLM_OPENAI_COMPAT
  → Journal SSE → LobeHub 卡片
  → {run_id}.dsh.jsonl 对照
```

**价值**：LobeHub 壳不变；白嫖 DSH tool pipeline + session；附件/artifact 仍走 LCA ingress。

**风险**：双 agent 循环语义要对齐（整题转发、不拆工具）；投影器需持续跟进 DSH 事件形状。

### 路径 B：借鉴 Capability Seam，重构 Protocol 层（P1，与 execution planes 合并）

```
ComputerOps(Protocol)
  ├─ MachineComputer / SandboxComputer / DshComputer
  └─ computer_tool_set()   # Consumer，与 Provider 解耦
```

不改五层单向依赖；只拆 Tool 里 Definition 与 Consumer。

### 路径 C：LCA 认知层挂 DSH 插件（**降级为长期探索，非推荐主路径**）

layer1 决策门作 Cordis 插件；layer0 Provider 注入 DSH。**前提**：仍经 LobeHub + Gateway，不用 DSH Web 替壳。

### 路径 D：全面对齐 DSH 架构模式（长期）

| 阶段 | 内容 | 收获 |
|---|---|---|
| 1. Session Log 化 | Journal ↔ SessionEvent；model-visible ⟺ logged | replay、fork |
| 2. Waterfall | pre-step / tool pre-post / turn-stopping | 决策门事件化 |
| 3. Subagent seam | 多 provider 子 agent | Team 增强 |
| 4. Workflow | 声明式脚本 | 固定 SOP |

---

## 五、借鉴优先级路线图

| 优先级 | 借鉴项 | DSH 入口 | LCA 落点 | 路径 |
|---|---|---|---|---|
| **P0** | DSH execution driver | SDK + `dsh/` 包 | `dsh_execute.py`、`DshTurnDriver` | A（进行中） |
| **P1** | Tool pipeline | `tool-execution-pipeline.md` | layer0 tools middleware | B |
| **P1** | read-before-write | `tool-fs` | write/edit 工具 | B |
| **P1** | grep/glob + spill | `tool-fs-search`、`spill-local` | search/glob 工具 | A/B |
| **P1** | Capability Seam 三角色 | `capability-seams.md` | `ComputerOps` + Consumer 拆分 | B |
| **P2** | Permission preset | `permission-presets` | Run 级 HIL 档位 | B |
| **P2** | Compaction | `compaction-basic` | Journal 压缩 | D.1 |
| **P2** | Credential ref 分层 | `credentials-local` | Gateway settings | B |
| **P2** | Session turn/step 语义 | `session.md` | Journal 帧 | D.1 |
| **P3** | Subagent multi-provider | `subagent.md` | Team 可选 DSH spawn | D.3 |
| **P3** | Agent preset | `agent-presets` | LobeHub chip | B |
| **P4** | Workflow / plan | `workflow/*` | 固定 SOP | D.4 |
| **—** | Cordis 插件树替换五层 | — | **不做** | — |
| **—** | DSH Web 替 LobeHub | — | **不做** | — |
| **—** | 搬运 TS 源码 | — | **不做** | — |

---

## 六、立即可用的具体收益（不变，补入口）

### Python SDK

```python
from deepseek_harness import DeepSeekHarness

with DeepSeekHarness(provider="deepseek-official", model="deepseek-v4-flash") as h:
    result = h.run("列出当前目录的所有 Python 文件并统计行数")
```

LCA 侧优先走 `DshRuntime` Protocol，而非散落 subprocess。

### 工具实现必读

- `tool-fs`：read-before-write
- `tool-fs-search`：ripgrep + spill
- `tool-bash`：sandbox + background job
- `tool-terminal`：persistent PTY

### Session 持久化

JSONL/SQLite + projection 缓存 + 标题生成 — 对照 `{run_id}.dsh.jsonl` 与 Journal 双轨设计。

### Compaction / LLM 细节

见 §2.6、§2.7。

---

## 七、不建议做的

- **不替换 LCA 五层架构** — 与 Cordis 插件树共存，不合并
- **不搬 DSH TypeScript 代码** — 抄模式，Python 重写
- **不用 DSH Web 替 LobeHub** — 附件、artifact、Team 依赖现有产品层
- **不同时开所有路径** — DSH Developer Preview，API 会变；主路径 **A**，结构债用 **B** 渐进还
- **不把 DSH 当完整 coding agent 产品** — 它是 harness；LCA 是 product

---

## 八、推荐行动（修订）

| 优先级 | 行动 | 产出 |
|---|---|---|
| **P0** | 完成 `execution_target: dsh` 端到端（LobeHub chip → gateway → projector） | 可对比跑通 |
| **P1** | 读 DSH `architecture.md`、`tool-execution-pipeline.md`、`session.md`；更新 `contracts/protocols/` 差距清单 | 差距表进 ADR |
| **P1** | 拆 `computer_tool_set()` Consumer 原型 | PR 级 refactor |
| **P2** | 实现 tool pre/post 钩子 + read-before-write 一条链 | 单工具 vertical slice |
| **P2** | Journal compaction 设计稿（tool-pairing 规则） | spec |
| **P3** | 本文档升 ADR；每落地一项在 ADR 勾掉 | 可追溯 |

---

## 九、参考链接（DSH 源码树）

| 主题 | 路径 |
|---|---|
| 架构总览 | `deepseek-harness/docs/architecture.md` |
| 工具管道 | `deepseek-harness/docs/tool-execution-pipeline.md` |
| Session | `deepseek-harness/docs/subsystems/session.md` |
| Subagent | `deepseek-harness/docs/subsystems/subagent.md` |
| Capability seams | `deepseek-harness/docs/capability-seams.md` |
| Fork 约定 | `deepseek-harness/FORK.md` |
| LAN 部署 | `deepseek-harness/deploy/lan/README.zh.md` |

LCA 已实现：

| 模块 | 路径 |
|---|---|
| DSH driver | `lca/infrastructure/dsh/driver.py` |
| 对比跑道 spec | 已归档 |
| LobeHub 集成 | `docs/specs/lobehub-integration.md` |
