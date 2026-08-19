# 认知原语插件宪法 — 双平面、闭集、业界概念编译

**日期**: 2026-08-19
**状态**: ✅ Approved（spec 评审三轮后通过）
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
3. **替换**：换 Sensor/Gate/Brain 实现不改 `_loop`。长期可变成 YAML 字段；本期靠插件树 + Composer 注入。

---

## 2. 宪法（闭集默认拒绝修改）

改下列任一集合必须单独 ADR，默认否决。

| 闭集 | 成员 | 实现位置 |
|---|---|---|
| 两平面 | 脑（认知）/ 手（世界 I/O） | 插件 YAML 分组；架构测试按包路径与事件名检查 |
| 六步 | perceive → think → act → reflect → remember → stop | `CognitiveRuntime._loop`。ADR-0002 的 `observe` = `Body.act` 的返回值，不是独立 Protocol；`update` = `remember` = `Memory.update`。`_loop` 不另调 `observe()`。`loop:` 插件可整体替换，不可在六步旁加第七步 |
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

长期组合形态（第二期及以后可长成 AgentSpec 字段；**本期不新增 profile 顶层 `sensors:` / `gates:` schema**）：

```yaml
# 示意，不是本期要解析的配置面
loop: cognitive
brain: modular
sensors: [inbox-facts, workspace-instructions, clock]
gates: [workspace-vocab, repeat-tool, progress-loop]
```

本期装配仍走 cordis 插件树：Sensor 插件往 `ctx` 上的传感器列表 `provide/append`；Gate 仍由 `build_workspace_agent_gate()` 闭合进 Brain。读 bundle 条目必须能说出这个主体怎么看、怎么想、怎么做。

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
   Act: Body.act → Observation（ADR-0002 所称 observe）
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

`MemorySystem.perceive` 保持：检索 + 多层记忆视图。**压缩只属于 Memory.perceive 内部**（第三期把产品级 compaction 迁入此处）。不设 `compaction` Sensor，避免和检索抢顺序。

### 6.2 PerceiveHub

新 Protocol，与 Sensor 同文件：

```python
@runtime_checkable
class PerceiveHub(Protocol):
    """组合 Sensor 再委托 Memory.perceive。不拥有 Memory.update。"""

    async def perceive(self, state: AgentState) -> AgentState: ...
```

默认实现：`lca/layer1_cognitive/perceive_hub.py` 的 `SequentialPerceiveHub`，显式继承 `PerceiveHub`。

```text
async def perceive(state):
    for sensor in self.sensors:
        incoming = state
        try:
            state = await sensor.sense(incoming)
        except Exception:
            log.warning(...); state = incoming
    return await self.memory.perceive(state)
```

`CognitiveRuntime` 仍持有 `memory` 供 `update`（remember）。另持有 `perceive_hub`。若 `perceive_hub is None`，退化为 `memory.perceive`（无 Sensor，与今日兼容）。

约束：

- Sensor **只许**写 `working_memory` 与 `activated_skills` 索引。**`retrieved_context` 只由 `Memory.perceive` 赋值**（现网 `SimpleMemorySystem.perceive` 整表覆盖；Sensor 先写会被抹掉）。检索不是 Sensor，是 `Memory.query(SEMANTIC)`。
- 不可产出 Decision、不可调 Body、不可 splice Inbox。
- 模型可见内容必须先有 SessionEvent。本期 `clock` 默认 **不可见**，不写 journal，也 **不得**接到 `PromptReasoner` 的 `current_date`（Reasoner 继续用自己的时钟，避免双时钟 + 无事件的模型可见时间）。
- 单个 Sensor 失败：Hub 丢弃该次 `sense` 的返回值，**沿用进入该 Sensor 之前的 state**（`sense` 若原地 mutation 再抛，视为该 Sensor 违例；实现须在内部拼好再 return，或 Hub 传入 `copy`——本期 Clock 单键赋值且在 return 前完成，Clock 自身保证不半写）。structlog warning。循环继续。
- Sensor **禁止** `ctx.inject` 当 Service Locator。时钟经构造参数 `now: Callable[[], datetime] | None` 注入。

第一批 Sensor（实现可分期，契约本期就定）：

| id | 职责 | 取代 |
|---|---|---|
| `inbox-facts` | Inbox 批次摊到 `working_memory` | driver 里 claim 的认知部分 |
| `workspace-instructions` | AGENTS.md 摊到 `working_memory` | DSH agent-instructions |
| `clock` | UTC 时间写入 `working_memory["clock"]` | time-context |
| `skill-catalog` | 可激活技能摘要写入 `working_memory` | 全量技能塞 prompt |

检索（RAG）= `Memory.query(SEMANTIC)`，不是 Sensor。压缩 = `Memory.perceive` 内部。
Skill **不是** Sensor。Sensor 只让模型知道有哪些；激活仍是 Think / Gate.`try_shortcut` / 用户 slash。压缩见 6.1，不在本表。

### 6.3 控制口 vs 观察口

| 口 | 谁 | 可否改 Decision/State |
|---|---|---|
| 控制 | Sensor、Brain、Gate、Stop、Degradation、Body | 仅其 Protocol 规定的方向 |
| 观察 | journal projector、`on_start` / `on_complete` / `on_error` | **否** |

`DecisionGate.enforce(state, decision) -> Decision` 主方向是改 Decision。**已有例外**（`ProgressLoopDetector`）：可写且仅写 `state.working_memory["loop_warning"]`，供下一轮 Think 看见。本期 `RepeatToolCallGate` 沿用同一例外、同一键；链上后写者覆盖。不得经 Gate 改 `history` / Inbox。

`HookEvent.PRE_THINK` 与 `COGNITIVE_PHASES` 的 `agent.before_*` / `after_*` 是控制口伪装成观察口。**拆除 `_emit` 控制路径是第 13 节第四期**，本期只冻结增长并删掉 `after_act` 上的循环检测。工具管道上的 pre-execute（手）不在此列。

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

- `_loop` AST 语句数：新建 `tests/test_architecture_conformance.py`，上限 = 实现时用 ast 量得的当前值，本期只许下降（删内联 loop warning）。仓库里没有 ADR-0002 所说的旧门禁，不要假定它还在。
- 禁止新增 `agent.pre_step` / `agent.before_*` / `agent.after_*` 认知监听器（allowlist 冻结现存量，只减不增；今日仅 `step_budget@pre_step`）。
- 观察口不得把改写后的 State 写回循环：本期忽略 `_emit` 返回值，并删除原地 mutation 的控制 middleware。
- `@plugin` 名 ↔ 第 8 节编译表的 CI 第五期再上。

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
| RAG | `Memory.query(SEMANTIC)` |
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
| Compaction | `Memory.perceive` 内部（第三期迁入；不是独立 Sensor） |
| AGENTS.md / 时间 | Sensor |
| 沙箱 / 本机 / 设备 | Plane |
| 审批 | Body 侧或 `ask_human` |
| 目标 / TODO | working memory 或 Tool；不开新循环 |

---

## 9. Agent 问题 → 原语

| 问题 | 负责者 |
|---|---|
| 上下文撑爆 | Memory.perceive（内部压缩） |
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

| 文件 / 机制 | 修订 | 落地期 |
|---|---|---|
| ADR-0002「新特性只能 Hook」 | **控制面作废**。控制走 Protocol。观察口 Hook 保留且只读。补别名表：`observe`=`act` 返回值，`update`=`remember` | 1（文档） |
| ADR-0002 步名 | 与第 2 节六步对齐，不另开 ADR | 1（文档） |
| `COGNITIVE_PHASES` / `HookEvent.PRE_*` | 冻结，只减不增 | 1 冻结；**4 拆除 `_emit`** |
| harness-spine waterfall | 仅手平面工具管道可保留；认知阶段 middleware 淘汰 | 1 删 after_act 循环检测；4 拆其余 |
| 融合蓝图「plugin-everything」 | 只对装配与手成立；认知 = 原语实现 | 全文 |
| `loop_cognitive.py` | 导出 `build_cognitive_runtime(...)` 供 Composer 调用。`LiveAgent` 工厂仍属第二期，本期不必实现 `AgentHandle` | 1 runtime 建造；2 LiveAgent |
| `loop_intervention` 三处 + Composer `install_loop_intervention` | **删除**。成功仍重复 → `RepeatToolCallGate` | 1 |
| `skill.catalog.published` 的 `source: "pre_step"` | 改为 `perceive` / `sensor` | 2（与 skill-catalog Sensor） |

已有、必须当宪法执行：六步、四数据、六行动、CoALA、Team XOR、Skill vs Role、Plane、Journal、`Decision.rationale`。

---

## 12. 第一期实现范围（下一份 plan 只覆盖这些）

第一期证明宪法可执行：契约口 + 一个 Gate 迁徙 + 一个 Sensor + 冻结挂钩。不实现 Inbox Sensor、不接 LiveAgent、不拆 `_emit`。

### 12.1 `_emit` 与 PerceiveHub

本期 `_loop` **继续调用** `_emit`，**不把返回值赋回** `state`（`await self._emit(...);` 忽略返回）。不删除 `_emit`、不改 `COGNITIVE_PHASES` 集合（除了不再被 loop_intervention 使用）。

仅此不够：今日 `loop_intervention_mw` 是原地写 `state.working_memory`。所以本期必须 **卸掉该 middleware**（12.2），不能只忽略返回值。

perceive 改为：

```text
state = await self.perceive_hub.perceive(state)   # 或 memory.perceive 若 hub is None
```

不得新增 `_emit` 调用点。`_emit` 拆除是第 13 节第四期。

### 12.2 RepeatToolCallGate（挂钩迁徙，warning-only）

对照现网 after_act 行为，**机械迁移，不升级产品**：

| 项 | 现网 `_detect_and_inject_loop_warning` / middleware | 本期 Gate |
|---|---|---|
| 触发时机 | `Body.act` **之后** | `ModularBrain.think` 末尾 `enforce`（**下一轮** Think 才能看见警告——见下） |
| 计数 | 只数 `state.history`，**不含** 当前尚未 append 的 turn | 只数 `state.history`，同样不含当前候选 |
| 匹配 | **仅** `tool_name`（middleware 的 `recent_tools` 路径甚至更粗） | **仅** `tool_name`（与现网一致）。canonical args **不**进入本期比较，避免行为膨胀 |
| 阈值 | `consecutive >= 3` 写 warning | 同 3 |
| 强制 respond | **无** | **无**。打断阈值不在本期 |

现网 after_act 在 `history.append` **之前**计数，故第 3 次 act 结束时 history 仍只有 2 条、不告警；第 4 次 act 后写入，模型在第 5 次 think 看见。Gate 在 think 末尾数 history：history 已有 3 条同名时，第 4 次 think 的 `enforce` 写入，模型在 **同一次** 请求里还看不见（警告给下一轮）。

**不要用改阈值去「对齐现网」**。测试只锁 Gate 契约：`history` 连续 3 条同名 `use_tool` 后，下一次同名候选 `enforce` 写入 `loop_warning`。不在 `_loop` 的 act 后再调 Gate。

实现：`lca/layer1_cognitive/brain/decision_gates/repeat_tool_call.py` 的 `class RepeatToolCallGate(DecisionGate)`。`Sensor` / `PerceiveHub` / `DecisionGate` 从 `lca.contracts.protocols` re-export。

链位置：`build_workspace_agent_gate()` 中 **先于** `ToolLoopBreakerGate`：

```text
RepeatToolCallGate, ToolLoopBreakerGate, ProgressLoopDetector, ...
```

`working_memory["loop_warning"]` 同一键；后写覆盖。Repeat 只警告不改 Decision；Breaker / Progress 仍可强制 respond。强制 respond **不**走 `DegradationPolicy`，**不**填 `degraded_from`（与现有两个 Gate 一致）：新 `Decision` + 固定 `rationale`。

canonical args（预留、本期不用）：若未来比较参数，`json.dumps(args, sort_keys=True, default=None)` 失败则 **视为不可比、不计数**，`enforce` 不得抛。

删除清单：

- `lca/plugins/guards/loop_intervention.py`
- `lca/layer2_runtime/loop_intervention_mw.py`（含 `install_loop_intervention`）
- `CognitiveRuntime._detect_and_inject_loop_warning` 与 `_LOOP_CONSECUTIVE_THRESHOLD`
- `AgentComposer._build_middleware_registry` 里的 `install_loop_intervention` 调用
- `bundles/*.yaml` 中 `lca-guard-loop-intervention` 行（若有）

`tests/harness/test_phase_c_middleware.py` / `test_runtime_middleware_integration.py` 中依赖 `install_loop_intervention` / `after_act` 写 `loop_warning` 的用例：**改写为 RepeatToolCallGate.enforce**，或删除 middleware 断言。禁止保留对已删 API 的 import。

### 12.3 Clock Sensor

实现：

- `lca/layer1_cognitive/sensors/clock.py` — `class ClockSensor(Sensor)`
- `lca/plugins/sensors/clock.py` — `@plugin(name="lca-sensor-clock")` 薄包装

行为：

- 构造：`ClockSensor(now: Callable[[], datetime] | None = None)`。默认 `datetime.now(UTC)`。测试注入固定时刻。
- `sense`：`state.working_memory["clock"] = now().strftime("%Y-%m-%dT%H:%M:%SZ")` 后 return state。
- **不可见**：不 `session.record`，不进 `retrieved_context`，不改 PromptReasoner。
- 抛错：Hub 回滚到进入该 Sensor 前的 state（Clock 单赋值，失败则键不存在）。

装配（脑平面行为插件，进 `bundles/web-app.yaml`，**不要**放 `bundles/base.yaml`）：

```text
# Composer 今日是 _ScopeAsCapabilityContext.get(key) -> T | None
sensors = scope.get("sensors") or ()
# 若已是 cordis.Context：ctx.inject("sensors", default=())
# 缺键必须是空，禁止 KeyError
if sensors:
    hub = SequentialPerceiveHub(sensors=tuple(sensors), memory=memory)
else:
    hub = None   # Runtime 走 memory.perceive
runtime = build_cognitive_runtime(..., perceive_hub=hub)
```

plugin `setup`：`existing = ctx.inject("sensors", default=[]); ctx.provide("sensors", list(existing) + [ClockSensor()])`。

`inbox-facts` / `workspace-instructions` 第二期。压缩第三期进 Memory。

### 12.4 冻结瀑布

架构测试写入 `tests/test_architecture_self_consistency.py`（仓库若无此文件则新建）以及 `tests/test_architecture_conformance.py`：

1. `COGNITIVE_PHASES` 名称集合冻结为提交时快照；只允许删除。
2. 认知控制监听 **allowlist**（只减不增）：今日允许 `lca-guard-step-budget` 听 `agent.pre_step`。禁止新增任何 `agent.pre_step` / `agent.before_*` / `agent.after_*` 监听。`loop_intervention` 删除后 `after_act` 控制监听必须为零。
3. `_loop` AST 语句数：新建 `tests/test_architecture_conformance.py`，常量 = 实现时测量值，本期只许因删除 `_detect_and_inject_loop_warning` 下降。
4. **不做**全量 `@plugin`↔原语映射 CI（第五期）。

`step_budget` 迁 StopRule 是第三期；本期只把它锁在 allowlist。

### 12.5 Composer 与 `loop_cognitive`

行为主路径仍是 `AgentComposer` → `CognitiveRuntime(...)`。本期改 Composer：注入 `PerceiveHub`，去掉 `install_loop_intervention`。`RepeatToolCallGate` **只**经 `build_workspace_agent_gate()` 进入 solo Brain，**不要**再塞进 `compose(decision_gate=...)`（那是 lead 槽，solo 会绕过）。

`lca/plugins/loop_cognitive.py`：

- 导出 `build_cognitive_runtime(brain, body, memory, hooks, state_store, stop_rule, perceive_hub=None, middleware_registry=None) -> CognitiveRuntime`。Composer 调用它，避免两处构造分叉。
- `build_cognitive_live_agent` **仍可** `NotImplementedError`，或改成明确异常 `LiveAgent wiring is phase 2`。验收不要求 `AgentHandle`。
- 不在 plugin 里注册 `agent.*` 监听。

### 12.6 错误与边界

- Sensor 抛错：Hub 捕获，键缺失，循环继续。不强制 journal（clock 不可见）。
- RepeatToolCallGate 不改 `action_type`。
- `perceive_hub is None`（无 sensors 或 inject 缺键）：只 `memory.perceive`。
- 非 JSON 可序列化的 tool arguments：本期不比较参数。

### 12.7 验证（blast radius）

```
uv run ruff check --fix lca/contracts/protocols/cognition.py lca/layer1_cognitive lca/layer2_runtime lca/layer4_app/composer.py lca/plugins tests
uv run ruff format <同上>
uv run pytest --no-cov tests/test_architecture_self_consistency.py tests/harness/test_phase_c_middleware.py tests/harness/test_runtime_middleware_integration.py -q
uv run pytest --no-cov -q -k "RepeatTool or loop_warning or PerceiveHub or ClockSensor or ToolLoopBreaker"
```

Gate 测试以 `rg` 命中文件为准。签名变了再 `uv run mypy lca/layer1_cognitive lca/layer2_runtime`。准备提交时升全量。

---

## 13. 第二期及以后（接口已定，不在第一份 plan）

| 期 | 内容 |
|---|---|
| 2 | `inbox-facts` Sensor；followup/steer/inject 只经 Perceive 进入 Think；`loop_cognitive` 实现 `LiveAgent`/`AgentHandle`；`skill.catalog` 的 `source` 改名 |
| 3 | `workspace-instructions`；compaction 迁入 `Memory.perceive`；`step_budget` 迁 StopRule |
| 4 | 拆除 `_emit` 与认知 `COGNITIVE_PHASES` 控制用途；观察口仅 journal + on_complete/error |
| 5 | `@plugin` 名 ↔ 原语 allowlist CI；plan Brain 按需 |

每期仍遵守第 7 节扩展法。不得在二期把 waterfall「暂时」加回来。RepeatToolCallGate 的打断阈值若要做，单开一期并写数字，不混进第一期。

---

## 14. 测试设计

| 用例 | 证明 |
|---|---|
| Hub 无 sensor = 只 memory.perceive | 兼容 |
| clock + 注入 `now` → `working_memory["clock"]` 为固定 UTC 串 | Sensor 口 |
| clock `now` 抛错 → 无 `"clock"` 键且 `_loop` 不失败 | 感官缺口 |
| history 三条同名 use_tool 后，第四次候选 enforce 出现 `loop_warning` | Gate 时序（接受 off-by-one） |
| history 两条同名 → enforce 不写 warning | 阈值 3 |
| RepeatToolCallGate 不把 use_tool 改成 respond | warning-only |
| Composer 不再 import `install_loop_intervention` | 删除清单 |
| plugins/ 无 `agent.after_act` 控制监听 | 冻结 |
| Hub 内 sensor 元组顺序 = 构造顺序 | 组合 |
| 假 Sensor **先抛后写**：后续 Sensor 与 Memory 仍跑，state 无该 Sensor 的键 | Hub 回滚（mutate-then-raise 视为 Sensor 违例，本期不测） |
| `_loop` 仍调用 `_emit` 但不把返回值赋给 state | 本期边界 |

不在本期做：真实 LLM、强制 respond 新阈值、Inbox wake、compaction、LiveAgent。

---

## 15. 非目标

- 不 port DSH 包、不引入 compaction-basic / plan-mode / hooks-claude-code
- 不改五层 import 图、不把 `ctx` 做成 L1–L3 Service Locator
- 不把 ToT/Graph 做成第二种默认循环
- 不把 MAP 抬成 L2 阶段
- 不在本期改 LobeHub UI
- 不把「调度 / 标题 / telemetry exporter」升格为认知原语
- 本期不实现 `AgentLoopFactory.create -> AgentHandle`

---

## 16. 验收

第一期合并时必须同时成立：

1. 第 2 节闭集在代码中可指出唯一家园；ADR-0002 有控制面 + 步名别名补段。
2. `loop_intervention` 四条路径删除（plugin、mw、runtime 内联、Composer install）；RepeatToolCallGate 覆盖「同名工具 ≥3 次 → loop_warning」；测试绿。
3. `Sensor` + `PerceiveHub` Protocol 存在；`ClockSensor` 经 Composer/Hub 注入；无顶层 `sensors:` schema。
4. 架构测试：`COGNITIVE_PHASES` 冻结；认知监听 allowlist 含 `step_budget@pre_step`，`after_act` 控制监听为零。
5. Composer 经 `build_cognitive_runtime` 构造 `CognitiveRuntime`；LiveAgent 工厂不在本期验收。
6. glossary 增加 Sensor / PerceiveHub / 两平面；本编译表为本期权威。
)
