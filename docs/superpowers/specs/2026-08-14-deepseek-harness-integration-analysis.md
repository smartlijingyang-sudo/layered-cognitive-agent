# DeepSeek Harness (DSH) 对 LCA 的价值与融入方案

**日期**: 2026-08-14
**状态**: 分析草案

---

## 它是什么

DeepSeek Harness 是 DeepSeek AI 开源的 **agent harness**（智能体运行框架），基于 Cordis 插件系统，核心理念是「一切皆插件」。它是 TypeScript 生态中一个工程成熟度极高的项目，包含完整的 agent 循环、工具管线、会话持久化、子 agent 编排、沙箱隔离、技能系统、工作流引擎等。同时提供了一个 **Python SDK**（`deepseek-harness-sdk`），可以通过 JSON-RPC stdio 以子进程方式驱动 DSH 运行时。

---

## 一、与 LCA 现有架构的对应关系

| LCA 概念 | DSH 对应概念 | 成熟度差距 |
|---|---|---|
| `LLMAdapter` Protocol | `ctx.llm` seam + `LlmAdapter` 抽象类 | DSH 更完整：多 provider 路由、可配置重试策略、reasoning effort、stream chunk 协议、provider 发现 |
| `Tool` Protocol | `ctx.tools` + `ToolDefinition` | DSH 更完整：guarded execution pipeline、pre/post policy、并发控制、tool schema 自动注入 prompt |
| `Sandbox` Protocol | `ctx.sandbox` + `ctx.fs` + `ctx.shell` + E2B | DSH 更完整：capability seam 三角色（Definition/Provider/Consumer）、sandbox policy、filesystem observation policy |
| Skill 系统 | `ctx.skills` + `skill-filesystem` + `tool-skill` | 概念相似，DSH 的 skill catalog 搜索 + activate 链路更完整 |
| Journal / 可观测性 | `SessionEvent` 日志 + `session/persistence` | DSH 的 append-only session log 是模型历史的唯一事实源，有 replay 保证 |
| Execution Planes | Capability Seam 架构 | LCA 正在做的 machine/sandbox 切分，DSH 已经有成熟方案（fs-local / fs-sandbox / fs-e2b 共享同一 `ctx.fs`） |
| Agent Loop | `ctx.agentLoop` + turn/step 生命周期 | DSH 有完整的 waterfall 事件拦截链（pre-step → request → stream → pre-execute → execute → post-execute → turn-stopping） |
| 子 Agent | `ctx.subagents` seam | DSH 远超 LCA：多 provider 共存（spawn/fork/acp/codex/claude-code）、continuable 子 agent、activation 生命周期 |
| 工作流 | `ctx.workflowEngine` | LCA 目前没有，DSH 有 worker-thread provider + Rhai 脚本引擎 |

---

## 二、四种融入路径（由浅入深）

### 路径 A：DSH 作为 LCA 的「高级工具后端」（最低成本）

**做什么**：通过 Python SDK 把 DSH 当子进程启动，用它的工具能力（bash、filesystem、terminal、grep/glob、web_search/web_fetch）补全 LCA 的工具短板。

```python
# LCA 的 Tool adapter 委托给 DSH
class DshBackedTool:
    """把 DSH 的某个工具桥接为 LCA 的 Tool Protocol。"""
    async def execute(self, args):
        with DeepSeekHarness() as harness:
            result = harness.run(...)  # 通过 DSH 的完整工具管线执行
```

**价值**：
- LCA 立即获得 ripgrep-backed `glob`/`grep`、persistent PTY terminal、read-before-write 文件系统策略、sandbox policy 等
- 不改 LCA 内部架构，只增加一个 Tool 适配层
- DSH 的 E2B 沙箱可以作为 LCA `Sandbox` Protocol 的一个新实现

**风险**：两个独立 agent 循环各管各的，上下文不共享。

### 路径 B：借鉴 Capability Seam 模式，重构 LCA 的 Protocol 层

**做什么**：DSH 最精华的设计是 **Capability Seam**（能力缝）——每个能力三角色完整：

- **Service Definition**：声明接口（如 `ctx.fs`）
- **Service Provider**：实现接口（如 `fs-local`, `fs-sandbox`, `fs-e2b`）
- **Consumer**：模型面向的工具（如 `tool-fs` 的 `read`/`write`/`edit`）

LCA 目前的 Protocol 只有 Definition + Provider 两个角色，Consumer（Tool）和 Provider 是硬绑的。

**具体落地**：

```
当前 LCA:
  Tool = name + description + parameters + execute()  # 定义和消费一体

借鉴 DSH 后:
  ComputerOps(Protocol)       # Service Definition
  MachineComputer             # Service Provider（sidecar 传输）
  SandboxComputer             # Service Provider（沙箱传输）
  computer_tool_set()         # Consumer（组装模型面向的工具集）
```

这与你当前 `execution-planes-design.md` 的方向一致——DSH 验证了这条路径是可行的，并提供了参考实现。

### 路径 C：DSH 作为 LCA 的「前端 agent harness」（推荐探索）

**做什么**：让 LCA 的 layer1_cognitive（认知层）作为 DSH 的一个 **Cordis 插件** 挂载，利用 DSH 成熟的 agent loop、工具管线、会话管理，同时保留 LCA 的认知决策能力。

```
DSH (agent loop + tools + session + subagent)
  └── LCA Plugin (ctx 上注册)
        ├── layer1 的 brain 决策门（terminal_respond 等）
        ├── layer0 的 Sandbox / Computer 能力作为 DSH Provider
        └── Journal 作为 DSH session telemetry backend
```

**价值**：
- 直接获得 DSH 的 agent loop（waterfall 拦截链、compaction、retry、subagent 编排）
- LCA 的认知层变成可插拔的决策门，专注于「什么时候停下来」「怎么拆解任务」
- DSH 的 Web UI 可以成为 LCA 的前端（替代或补充 LobeHub）
- Python SDK 允许 LCA 的 Python 代码作为 DSH 的 Python runtime 存在

### 路径 D：全面对齐 DSH 的架构模式（长期演进）

这是最彻底的方案，分阶段演进：

| 阶段 | 做什么 | 收获 |
|---|---|---|
| **1. Session Log 化** | 把 LCA 的 Journal 对齐 DSH 的 append-only `SessionEvent` 模式，保证「model-visible ⟺ logged」 | 可复现、可 replay、可 fork session |
| **2. Waterfall 事件链** | 在 agent loop 中引入 pre-step / request / stream / tool-execute 等 waterfall 拦截点 | 认知决策门变成事件监听器，而非硬编码分支 |
| **3. Subagent Seam** | 引入 `ctx.subagents` 级别的多 provider 子 agent 系统 | LCA 的 Team 协作机制获得 spawn/fork/acp 多种后端 |
| **4. Workflow Engine** | 引入 DSH 的工作流引擎概念 | 多 agent 编排变成声明式脚本，而非代码级硬编排 |

---

## 三、立即可用的具体收益

不管选哪条路径，以下东西**现在就能用**：

### 1. Python SDK 子进程模式

`pip install deepseek-harness-sdk`，5 行代码获得完整的 agent + 工具链：

```python
from deepseek_harness import DeepSeekHarness

with DeepSeekHarness(provider="deepseek-official", model="deepseek-v4-flash") as h:
    result = h.run("列出当前目录的所有 Python 文件并统计行数")
```

### 2. 工具实现对标

DSH 的工具实现模式可以直接参考：

- `tool-fs`：read-before-write 策略（写文件前必须先读，防止覆盖）
- `tool-fs-search`：ripgrep + spill store（大结果集自动溢出到文件）
- `tool-bash`：sandbox + background job（沙箱策略 + 后台任务管理）
- `tool-terminal`：persistent PTY session（持久终端会话）

### 3. Session 持久化方案

DSH 的 JSONL / SQLite 双后端 + projection 缓存 + 标题生成，比 LCA 目前的 Journal 更接近生产可用。

### 4. Compaction（上下文压缩）

DSH 有完整的 `ctx.compaction` seam：pressure 检测 → tool-result pruning → summary 生成，LCA 目前缺失这个能力。

### 5. LLM Adapter 的工程细节

- 重试策略（normal/always 两种模式）
- reasoning effort 选择
- stream idle timeout
- empty response retry
- provider model discovery

这些在 LCA 的 `LLMAdapter` 里都是空白。

---

## 四、不建议做的

- **不要替换 LCA 的分层架构** — LCA 的 `contracts → layer0 → layer1 → layer2 → layer3` 单向依赖是好的设计，DSH 的 Cordis 插件树是另一种组织方式，两者可以共存
- **不要搬运 DSH 的 TypeScript 代码** — 两个项目语言不同，价值在于架构模式和设计决策，不在于直接复用代码
- **不要同时启动所有路径** — DSH 还在 developer preview，API 会 breaking change，建议先以路径 A 或 B 做最小验证

---

## 五、推荐行动

| 优先级 | 行动 | 时间 |
|---|---|---|
| **P0** | 安装 `deepseek-harness-sdk`，跑通 Python SDK 的 headless 模式，体会它的 agent loop 和工具链 | 半天 |
| **P1** | 读 DSH 的 `capability-seams.md` + `subagent.md` + `llm-streaming.md`，与 LCA 的 `contracts/protocols/` 逐条对比，找到最大差距 | 1-2 天 |
| **P2** | 选一个具体点（比如 Tool guarded execution pipeline 或 Compaction seam），在 LCA 中实现对应设计 | 1 周 |
| **P3** | 写一个 ADR，记录从 DSH 学到的设计决策以及在 LCA 中的落地方案 | 持续 |
