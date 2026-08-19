# 认知原语插件宪法 — 双平面、闭集、业界概念编译

**日期**: 2026-08-19
**状态**: Draft（对话三段已认可：双平面、六条闭集、存在面；本文是唯一实现依据）
**关联**:
- ADR-0001 五层单向、ADR-0002 认知闭环、ADR-0004 Protocol-First、ADR-0008 定位、ADR-0030/0034 团队、ADR-0037 Journal-as-Truth
- [2026-08-16-plugin-tree-runtime-design.md](./2026-08-16-plugin-tree-runtime-design.md)（装配：profile/bundle 仍有效）
- [2026-08-19-cordis-migration-design.md](./2026-08-19-cordis-migration-design.md)（运行时是 cordis；本文约束 *挂什么*，不换内核）
- `docs/specs/harness-spine-spec.md`（Session/Inbox/LiveAgent 保留；**认知控制不再走 waterfall**）
- 对照：`~/deepseek-harness` 的能力 seam 留下，事件挂钩不当认知扩展口

---

## 0. 一句话

业界 agent 能力全部 **编译** 进一套封闭认知原语；插件只换实现、不在循环上开洞。DSH 的 I/O seam（手）留下；DSH 的 `agent/pre-step` 挂钩式认知（脑）禁止再长。循环永远是 `perceive → think → act → reflect → remember → stop`。

---

## 1. 问题与非问题

**问题**：把「一切都是插件」当成认知架构，会得到 DSH 那种产品：装配图干净，单个插件是硬编码功能，交互靠 13 个 `pre-step` 监听器。LCA 已经有对的契约（`Brain` / `Body` / `Decision` / `Team`），同时已经长出 DSH 感染（`COGNITIVE_PHASES`、`agent.after_act` 上的 `loop_intervention`、融合蓝图把 waterfall 当北极星、`loop_cognitive` 空壳）。

**非问题**：手怎么换（LLM、沙箱、文件系统）——那套 Definition / Provider / Consumer 是对的。Session / Journal / LiveAgent / profile 树也是对的。

**成功标准**（三条，必须有测试）：

1. **总流程**：一张数据流，`State → Decision → Observation → Reflection → State'`，没有「还有 N 个认知挂钩」。
2. **单点**：打开一个脑插件，函数签名就是全部接口。
3. **替换**：YAML 改 `brain:` / `sensors:` / `gates:`，循环文件零改动。

---

## 2. 宪法（闭集默认拒绝修改）

改下列任一集合必须单独 ADR，默认否决。

| 闭集 | 成员 | 实现位置 |
|---|---|---|
| 两平面 | 脑（认知）/ 手（世界 I/O） | 插件 YAML 分组；架构测试按包路径与事件名检查 |
| 六步 | perceive → think → act → reflect → remember → stop | `CognitiveRuntime._loop`；`loop:` 插件可整体替换，不可在六步旁加第七步 |
| 六行动 | `respond` `use_tool` `delegate` `handoff` `stop` `ask_human` | `ActionType` |
| 四数据 | `AgentState` `Decision` `Observation` `Reflection` | `lca.contracts.models.core` |
| 四记忆 | working / episodic / semantic / procedural | `MemoryLayer`；共享仅 semantic+procedural |
| 团队 | `members + (lead XOR coordination)` | ADR-0030/0034 |

**永远开放**：Brain / Reasoner / Critic / Body / Memory / Sensor / Skill / Tool / Plane / Transport / DecisionGate / StopRule / TeamStrategy / Synthesizer / LLMAdapter / JournalProjector。

新 ActionType、新循环阶段、新的 `agent.before_*` 认知事件：默认否决。换循环 = 换整个 `loop:` 插件。

---

## 3. 两平面

### 3.1 脑

实现某个认知 Protocol，经构造函数注入，运行期不 `ctx.on('agent.*')` 改 Decision/State。

组合绑定（profile / AgentSpec，名字示意）：

```yaml
loop: cognitive
brain: modular
reasoner: prompt
critic: simple
body: tool-dispatch
memory: journaled
stop: budget-and-verdict
sensors: [inbox-facts, workspace-instructions, clock]
gates: [workspace-vocab, repeat-tool, progress-loop]
```

读这份 YAML 必须能说出这个主体怎么看、怎么想、怎么做。

### 3.2 手

保持 DSH 三角色：Service Definition + Provider + Consumer。`llm` / `tools` / `sandbox` / `workspace` / `session` / `transport` / `credentials`。

手平面允许 *工具执行管道* 上的策略（超时、权限、沙箱包装）——那是 Body/`SafeExecutor` 内部，不是认知挂钩。禁止手插件监听 `before_think` / `after_act` 来改 Decision。

### 3.3 运行时形状（单向）

```text
Inbox / 用户 / 队友回报 / 工具结果
        │
        ▼
   Journal（真源）
        │
        ▼
   Perceive: Sensors + Memory.perceive     只读世界 → 只写 State
        │
        ▼
   Think: Brain → Decision → DecisionGate
        │
        ▼
   Act: Body → 手（Tool / Plane / Transport / Human）
        │
        ▼
   Observation → journal
        │
        ▼
   Reflect → Remember → Stop
```

写世界只许 Act。Perceive 不得调 Body。

---

## 4. 生命周期：存在 / 做事 / 一轮

```text
Agent（存在） ⊃ Run（接一个任务） ⊃ Turn（六步一轮）
```

不新造对外类型。沿用：

- `LiveAgent` + `AgentHandle` + `AgentLoopFactory`（`lca/contracts/harness/agent.py`）
- `SessionHeader` / `SessionEvent` / journal
- 子代理：另一个 Agent，另一个 Session；`parent_session` + `delegation_depth` 是谱系，不继承父工具可见性

团队不是超级 Agent。Lead 的 `team_awareness` 进入 `AgentState`，下一轮 Perceive 看见队友回报。

`create` / `resume` / `dispose` 语义保持 harness spec：setup 失败不发布；resume 从 journal 重建事实、按当前 profile 再绑脑与手。

---

## 5. Inbox：三种投递，零认知旁路

保留 `followup` / `steer` / `inject`。Loop 插件可以有工程边角（wake latch 等），**不得成为 Brain/Sensor/Gate 的 API**。

| 方法 | 语义 | Journal | Perceive 看到 | 唤醒 |
|---|---|---|---|---|
| `followup` | 新任务或下一句 | `message.accepted.v1` + `inbox.spliced.v1` 目标 next-run | 写入本轮任务/用户事实 | 是 |
| `steer` | 当前工作插话 | 同上，目标 next-turn | `working_memory` 待处理用户输入 | 当前 Turn 边界后 |
| `inject` | 背景，不吵 | `context.injected.v1` | `retrieved_context` | 否 |

禁止第四种投递。禁止 Sensor/Gate `inbox.splice`。禁止插件把假用户消息写入历史充当「提醒」。

`ask_human` 的回答走已有 `resume(snapshot, input)` → `Observation(source=human_answer)`，不是新 Inbox 种类。

Turn 开始时：Inbox 批次已在 journal → 摊到 `AgentState` 待感知槽 → Perceive 只读 State+Journal → Think 只读 Perceive 之后的 State。

---

## 6. Sensor 与 Perceive

### 6.1 Protocol

新契约，放在 `lca/contracts/protocols/cognition.py`（与 Brain 同层，不是 harness 事件）：

```python
@runtime_checkable
class Sensor(Protocol):
    """世界 → State。只看，不做。"""

    async def sense(self, state: AgentState) -> AgentState: ...
```

`MemorySystem.perceive` 保持：检索 + 多层记忆视图。压缩是 Perceive 的实现细节（Memory 内或独立 Sensor），对外仍是 Perceive。

### 6.2 PerceiveHub

L2 循环不再直接只调 `memory.perceive`。它调一个组合器（默认实现可放 L1，由 loop 注入）：

```text
async def perceive(state):
    for sensor in sensors:          # YAML 顺序，稳定
        state = await sensor.sense(state)
    return await memory.perceive(state)
```

约束：

- 只准丰富 `retrieved_context` / `working_memory` / `activated_skills` 索引。
- 不可产出 Decision、不可调 Body、不可 splice Inbox。
- 模型可见内容必须先有 SessionEvent（或 content_ref 指向已有事件）。
- 单个 Sensor 失败：写 `visibility=audit` 事件，State 带缺口继续。是否因「关键感官缺失」停机，由 StopRule 决定。

第一批 Sensor（实现可分期，契约本期就定）：

| id | 职责 | 取代 |
|---|---|---|
| `inbox-facts` | 本轮 Inbox 批次摊开到 State | driver 里 claim 的认知部分 |
| `workspace-instructions` | AGENTS.md / 角色约定文件 | DSH agent-instructions |
| `clock` | 时间 / 时区 | time-context |
| `skill-catalog` | 可激活技能摘要 | 全量技能塞 prompt |
| `retrieval` | semantic 检索 | RAG 当特殊循环 |
| `compaction` | 压力下收缩模型可见历史 | compaction 挂 pre-step |

Skill **不是** Sensor。Sensor 只让模型知道有哪些；激活仍是 Think / Gate.`try_shortcut` / 用户 slash。

### 6.3 控制口 vs 观察口

| 口 | 谁 | 可否改 Decision/State |
|---|---|---|
| 控制 | Sensor、Brain、Gate、Stop、Degradation、Body | 仅其 Protocol 规定的方向 |
| 观察 | journal projector、`on_start` / `on_complete` / `on_error` | **否**；架构测试锁返回类型 |

`HookEvent.PRE_THINK` 与 `COGNITIVE_PHASES` 的 `agent.before_*` / `after_*` 是控制口伪装成观察口，按第 12 节拆除。工具管道上的 pre-execute（手）不在此列。

---

## 7. 扩展法

加能力只许按序：

1. 实现已有 Protocol
2. YAML 组合已有原语
3. 新 Sensor（世界 → State）
4. 新 Tool（Decision → 世界）
5. 新硬规则（Gate / Stop / SandboxPolicy / Budget）
6. 新 SessionEvent（新的模型可见事实）
7. 新 Protocol → 必须 ADR。新 ActionType、新循环阶段默认否决

机械门禁（本期就要有测试骨架，第 12 节落地）：

- `_loop` AST 语句数上限保持（已有）。
- 禁止新增 `agent.before_*` / `agent.after_*` 认知监听器（allowlist 冻结现存量，只减不增）。
- 观察口回调不得返回改写后的 `Decision` / `AgentState`。
- `docs/glossary.md` 或本文件第 8 节的概念编译表：新的公开产品名必须能指到一个原语行，否则不能合并。

---

## 8. 业界概念编译表

新论文 / 新产品往本表加行，不加循环阶段。本表是扩展入口。

### 8.1 单主体怎么想

| 业界 | 落点 |
|---|---|
| ReAct / function calling | 默认 Brain；`use_tool` |
| CoT | `Decision.rationale` + Reasoner 模板 |
| Plan-and-Execute / ReWOO | Brain=`plan`；Gate 在计划未闭合前可禁 `use_tool` |
| Reflexion / Self-Refine | Critic；Memory 写 episodic/semantic |
| Constitutional | Gate（硬）+ Critic（软）+ Role（建议） |
| ToT / GoT / LATS | **Brain 内部搜索**；每步仍一个 Decision。ToT 不是 Team |
| CodeAct | `use_tool` + 代码解释器 Tool |
| SWE / 编码 agent | 手：fs/shell/lsp；Skill：仓库惯例；Gate：禁写密钥；Plane：sandbox |
| Computer Use / GUI | 手：screenshot/click；Plane：device |
| Browser / 研究 | 手：web/search；或 `retrieval` Sensor |
| RAG | `retrieval` Sensor 或 `Memory.query(SEMANTIC)` |
| Router / 小模型分流 | SkillRouter 或 Gate.`try_shortcut` |
| Mixture of Agents | Team FanOut + Synthesizer |
| LangGraph | Team `Graph` **或** Brain 内部图 **或** 确定性 Brain。禁止第四个图运行时 |
| OpenAI Agents / Claude Code / DSH loop | 手 + 默认 ReAct Brain；产品功能按本表搬 |
| Workflow / cron | L4 往 Inbox `followup`。调度不是认知原语 |
| Voice / 实时 | Transport + LLM 流式；数据仍是四种 |
| 多模态 | `Observation` 已有 image/audio |
| ACP / A2A / MCP | Transport 或 Tool Provider |
| Eval | JournalProjector + score |

MAP 五模块（分解/预测/评估/冲突/协调）是 ModularBrain **内部零件**，不是 L2 新阶段。

### 8.2 多主体

| 业界 | 落点 |
|---|---|
| Supervisor / PM | `TeamLead.routing` |
| 咨询委员会 | `consult` / `board` |
| 流水线 | `Pipeline` |
| 并行汇总 | `FanOut` + Synthesizer |
| 对话式多智能体 | `PeerRelay` / `PeerSwarm` |
| 辩论 | `Debate` |
| DAG | `Graph` |
| 子代理 | `DELEGATE` + 子 AgentSpec + 独立 Session |
| 交接 | `HANDOFF` |
| 共享知识 | SharedMemory，仅 semantic/procedural |

### 8.3 记忆、技能、环境

| 业界 | 落点 |
|---|---|
| scratchpad | `WORKING` |
| 轨迹 | `EPISODIC` + journal |
| 事实 | `SEMANTIC` |
| SOP / SKILL.md | `PROCEDURAL` + `activated_skills` |
| Compaction | Perceive（Memory 或 `compaction` Sensor） |
| AGENTS.md / 时间 | Sensor |
| 沙箱 / 本机 / 设备 | Plane |
| 审批 | Body 侧或 `ask_human` |
| 目标 / TODO | working memory 或 Tool；不开新循环 |

---

## 9. Agent 问题 → 原语

| 问题 | 负责者 |
|---|---|
| 上下文撑爆 | Memory.perceive / compaction Sensor |
| 同一工具死循环 | DecisionGate（已有 `ToolLoopBreakerGate`；补「成功仍重复」） |
| 跨工具无进展 | 已有 `ProgressLoopDetector` |
| 词表外行动 | DegradationPolicy；Body 见越界 = 契约违例 |
| 工具失败 | `Observation.success=false` → Reflect → 下轮 Think |
| 问人 | `ask_human` + resume |
| 危险操作 | SandboxPolicy / 审批 / Gate |
| 长任务迷路 | episodic + 计划进 working + Reflection |
| 超预算 | Budget + StopRule |
| 中断恢复 | StateStore + Journal + Inbox |
| 提示词膨胀 | Skill 按需激活；Perceive 检索 |
| LLM 不稳 | Adapter 重试（手）；Critic（脑） |
| 不可复现 | Journal-as-Truth |
| 对齐 | Gate + Critic + Role，三层不混 |
| 环境不一致 | Plane |
| 归因 | journal 盖 `plugin_id` / profile digest（观察口） |

出现「加个 pre-step」时先查本表。找得到行就不许加挂钩。

---

## 10. 有意不做成原语

loop 插件或手平面内部可以有，**没有认知名字**：

- wakeup latch、empty-enter、max-tokens sticky
- waterfall 顺序、`prepend: true`
- 工具并行池（Body/`use_tool` 内部）
- LLM 重试、provider 默认值
- 会话标题、exporter

---

## 11. 对现状的修订（避免两套教义）

| 文件 / 机制 | 修订 |
|---|---|
| ADR-0002「新特性只能 Hook」 | **控制面作废**。控制走 Protocol。观察口 Hook 保留且只读 |
| `COGNITIVE_PHASES` / `HookEvent.PRE_*` | 冻结，只减不增；第 12 期拆除控制用途 |
| harness-spine waterfall | 仅手平面工具管道可保留；认知阶段 middleware 淘汰 |
| 融合蓝图「plugin-everything」 | 只对装配与手成立；认知 = 原语实现，不是事件挂件 |
| `lca/plugins/loop_cognitive.py` | 必须变成真正的 loop provider，薄封装 `CognitiveRuntime` |
| `lca/plugins/guards/loop_intervention.py` + `loop_intervention_mw.py` + `_detect_and_inject_loop_warning` | **删除**。与已有 Gate 重复；缺口（成功仍重复）并入 Gate |
| `skill.catalog.published` 的 `source: "pre_step"` | 改为 `perceive` / `sensor`，不得再叫 pre_step |

已有、必须当宪法执行：六步、四数据、六行动、CoALA、Team XOR、Skill vs Role、Plane、Journal、`Decision.rationale`、可替换 loop factory。

---

## 12. 第一期实现范围（下一份 plan 只覆盖这些）

第一期证明宪法可执行，不实现全部 Sensor、不重写 Inbox 工程边角。

### 12.1 契约

- `Sensor` Protocol + 默认 `PerceiveHub`（sensors 元组 + Memory）。
- `CognitiveRuntime._loop`：perceive 改走 Hub；**不得新增** `_emit`。
- 观察口：现有 `_emit` 若仍调用，返回值忽略（不得把 middleware 改写写回 State）。本期可先加测试锁「新代码不得依赖 `_emit` 改 State」；拆除 `_emit` 控制路径在 12.4。

### 12.2 挂钩 → 原语样板（重复工具）

现状三处在做循环检测：

- `ToolLoopBreakerGate`：同一工具连续 **失败** → 强制 respond
- `ProgressLoopDetector`：连续无进展 → warning / 强制 respond
- `after_act` middleware + runtime 内联：同一工具连续调用（**含成功**）→ `working_memory["loop_warning"]`

第一期：把「成功仍重复」收进新的或扩展的 `DecisionGate`（建议 `RepeatToolCallGate`，链进 `build_workspace_agent_gate`）。行为：

- 连续相同 `tool_name`+规范化参数 ≥ 警告阈值：写入 `working_memory["loop_warning"]`，**返回原 Decision**（下一轮 Perceive/Think 看见，不伪造 user message）
- ≥ 打断阈值：强制 `respond`，与 `ToolLoopBreakerGate` 同形

然后删除：

- `lca/plugins/guards/loop_intervention.py`
- `lca/layer2_runtime/loop_intervention_mw.py` 及其 `install_*`
- `CognitiveRuntime._detect_and_inject_loop_warning` 与 `_LOOP_CONSECUTIVE_THRESHOLD` 内联
- bundle 里对应 plugin 行

测试从 `agent.after_act` 断言改为对 Gate 的 `enforce()` 断言；保留「连续三次同工具出现 loop_warning」的行为断言。

### 12.3 一个 Sensor 样板

实现 `clock` Sensor（无 FS、无 Inbox 耦合）：`sense` 把 ISO 时间写入 `working_memory["clock"]` 或 `retrieved_context` 一条结构化记录；若模型可见，先 `session.record` 一条 audit/model 事件。

YAML：`sensors` 可配。默认 web profile 可先只挂 `clock`，证明组合口活着。

`inbox-facts` / `workspace-instructions` / `compaction` 列为第二期，契约在第 6 节已闭合，不在本期编码。

### 12.4 冻结瀑布

架构测试（新建或并入 `tests/test_architecture_self_consistency.py`）：

1. `COGNITIVE_PHASES` 名称集合冻结为今日快照；只允许删除。
2. `lca/plugins/**` 不得新增 `ctx.events.on("agent.before_*"| "agent.after_*")`（现有 loop_intervention 删除后，此集合应为空，或仅观察口白名单）。
3. `_loop` 仍 ≤ 现有语句上限。
4. 概念编译：`lca/plugins/` 每个 `@plugin(name=...)` 必须在本 spec 第 3/6/8 节或 glossary 能映射到 {脑 Protocol | 手 seam | 观察口}；新增无映射名则失败。实现可用手写 allowlist 表 `tests/fixtures/plugin_primitive_map.yaml`，与插件名双向校验。

### 12.5 `loop_cognitive`

`lca/plugins/loop_cognitive.py` 去掉 `NotImplementedError`。工厂用已注入的 Brain/Body/Memory/StopRule/PerceiveHub 构造 `CognitiveRuntime`，注册到 `agent_loop` seam。不在工厂里加事件监听。

兼容：现有 `AgentComposer` 路径可继续调 `CognitiveRuntime` 直接构造，直到组合根只走 `ctx`；本期至少让 plugin 路径与 composer 路径行为一致（同一套 Gate + 无 after_act 干预）。

### 12.6 错误与边界

- Sensor 抛错：捕获、journal audit、继续。
- Gate 把 `use_tool` 改成 `respond`：走已有 Degradation/Action 路径，journal 记录 `degraded_from`（Decision 已有该字段）。
- 无 Sensor 列表：Hub 退化为只调 `memory.perceive`（与今日行为兼容）。
- 重复工具 Gate 的参数规范化：JSON 键排序后的 canonical string；预览截断不得用于比较（与 DSH reminder 同一教训）。

### 12.7 验证（blast radius）

```
uv run ruff check --fix lca/contracts/protocols/cognition.py lca/layer1_cognitive lca/layer2_runtime lca/plugins lca/plugins/guards tests
uv run ruff format <同上>
uv run pytest --no-cov tests/test_architecture_self_consistency.py tests/harness/test_phase_c_middleware.py tests/harness/test_runtime_middleware_integration.py tests/test_decision_gates*.py -q
```

若 Gate 测试文件名不同，以 `rg RepeatTool|loop_intervention|ToolLoopBreaker` 为准补齐。签名变了再 `uv run mypy lca/layer1_cognitive lca/layer2_runtime`。准备提交时升全量。

---

## 13. 第二期及以后（接口已定，不在第一份 plan）

| 期 | 内容 |
|---|---|
| 2 | `inbox-facts` Sensor；followup/steer/inject 只经 Perceive 进入 Think |
| 3 | `workspace-instructions`；compaction 迁入 Memory/Sensor；其余 guard 迁 Gate/Stop |
| 4 | 拆除 `_emit` 控制路径与 `COGNITIVE_PHASES`；观察口仅 journal + on_complete/error |
| 5 | 概念编译表 CI 对公开产品名全量；plan Brain、retrieval Sensor 等按需加实现 |

每期仍遵守第 7 节扩展法。不得在二期把 waterfall「暂时」加回来。

---

## 14. 测试设计

| 用例 | 证明 |
|---|---|
| Hub 无 sensor = 只 memory.perceive | 兼容 |
| clock sensor 写入可预测时间（测试注入时钟） | Sensor 口 |
| clock 失败不抛出循环 | 感官缺口 |
| RepeatToolCallGate 三次同参 use_tool → loop_warning | 挂钩行为迁入 Gate |
| 达打断阈值 → action_type respond 且 degraded_from 或 rationale 固定 | 硬规则 |
| 删除后 `rg agent.after_act` 在 plugins/ 无控制监听 | 冻结 |
| YAML 换 sensors 顺序，clock 与假 sensor 的调用顺序 = 列表顺序 | 组合 |
| 观察口 mock 改 State 不被 `_loop` 采纳（若本期仍调用 _emit） | 控制/观察分离 |

不在本期做：真实 LLM、DSH 对照、全部 Sensor、Inbox wake 边角的属性测试。

---

## 15. 非目标

- 不 port DSH 包、不引入 compaction-basic / plan-mode / hooks-claude-code
- 不改五层 import 图、不把 `ctx` 做成 L1–L3 Service Locator
- 不把 ToT/Graph 做成第二种默认循环
- 不把 MAP 抬成 L2 阶段
- 不在本期改 LobeHub UI
- 不把「调度 / 标题 / telemetry exporter」升格为认知原语

---

## 16. 验收

第一期合并时必须同时成立：

1. 本文件第 2 节闭集在代码中可指出唯一家园。
2. `loop_intervention` 的三条代码路径删除；重复工具行为由 Gate 覆盖，测试绿。
3. `Sensor` + PerceiveHub 存在；至少一个非 Memory 的 Sensor 经 YAML/工厂注入。
4. 架构测试冻结认知 `before_*`/`after_*` 监听器增长。
5. `loop_cognitive` 可构造 `CognitiveRuntime`，不再 `NotImplementedError`。
6. 文档：ADR-0002 补一段「控制面修订见本 spec」；glossary 增加 Sensor / PerceiveHub / 两平面；本编译表为本期权威。
)
