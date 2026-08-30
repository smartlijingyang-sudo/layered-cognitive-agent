# Agent Loop 聚焦认知治理：最小插件化实施设计

**日期：** 2026-08-27  
**状态：** 已实施并通过全量回归测试  
**范围：** 在既有六阶段声明式 Agent Loop 内，为“连续无进展认知重入”提供一个可替换、可审计的治理策略。

## 问题与边界

当前生产路径已经将 Agent Loop 收敛为 `perceive → think → act → reflect → remember → stop` 的声明式阶段图；`GenericPlanInterpreter` 只遍历经编译的图，`PhaseExecutionTransaction` 是事实提交、效果执行与 Delta 归约的唯一事务边界，`DeclarativeRuntimeBindings` 在运行前冻结所有插件能力。该架构已避免旧式 Hook 对控制流的渗透，不应重新引入全局回调、新阶段或动态环境查找。

仍有一个价值明确且尚未独立建模的策略空位：工具级重复失败由 `ToolLoopBreakerGate` 处理，但它无法识别**跨工具或无工具的重复认知**，例如连续形成同一行动意图、没有获得新观察、反思仍要求修正，却继续回到下一轮。该问题属于 `STOP` 前的继续/收口判定，不属于新的认知原语，也不应扩展阶段图的六阶段闭集。

## 方案

引入 `control.stop.focus` 这个独立的 `GOVERN` 类型 Phase Contribution。它在 `STOP` 的标准执行器完成、但图边选择之前运行，并且只读取 `PhaseContext.state.history` 与当前 `decision`、`observation`、`reflection`。它不读取 `Cordis Context`，不修改 `AgentState`，不调用工具，也不直接挑选下一条边。

策略只关心一个可解释的信号：**连续无进展的 Turn**。一个 Turn 仅在以下条件同时成立时才被视为无进展：当前与上一轮的行动意图相同；两轮都没有成功观察；并且当前反思明确为 `NEEDS_CORRECTION` 或 `BLOCKED`。连续达到 Profile 配置的阈值后，插件返回标准 `ControlVerdict(STOP)`；Harness 负责把该判定记录为既有 `control.stopped` 事实并产生完成结果。正常、成功、意图改变、反思 `ON_TRACK` 或缺乏历史事实时均放行。

| 维度 | 设计选择 | 原因 |
|---|---|---|
| 扩展点 | `STOP` 的 `GOVERN` contribution | 这是继续/终止的天然边界，且已有聚合、事实与终态投影。 |
| 策略输入 | 已归约的 `Turn` 历史与当前阶段的只读事实 | 通过 Reducer 的单一写入路径形成可审计输入，避免工作记忆隐式约定。 |
| 策略输出 | 标准 `ControlVerdict` | 复用既有事件和 outcome 映射，不创建新的事件词表或控制协议。 |
| 配置 | `max_consecutive_stagnant_turns`，默认 3，最小 1 | 表达单一策略旋钮；Profile 可替换或移除插件。 |
| 失败语义 | `STOP`，非 `DENY` / `EXHAUSTED` | 这是受控收口而不是策略或预算错误，终态保持完成并生成可诊断事实。 |

## 与业界模式的对应

LangGraph 将持久状态、恢复与确定性/Agentic 节点组合为运行时职责；本设计保留阶段图作为拓扑，策略仅对已声明的继续路径做判定。[1] OpenAI Agents SDK 把 Agent、工具、交接、Guardrail 和 tracing 收敛为少量原语；本设计以一个独立策略模块而非新增阶段保持同样的原语克制。[2] Semantic Kernel 强调插件应封装清晰的功能单元，并声明其语义与副作用；该插件仅有只读输入和 typed verdict 输出。[3] Anthropic 的工程建议强调简单可组合的工作流/Agent 模式、环境反馈和停止条件；无进展收口就是对该停止条件的确定性补齐。[4]

## 不变量与验收

该改动不改变六阶段 `SemanticPhase` 枚举、阶段图拓扑、`LoopGuard` Protocol、Journal catalog、公共 `AgentState` schema 或运行时绑定闭合。它应在单一新插件模块中凝聚判定逻辑；Bundle 只负责显式装配；测试覆盖放行、单次无进展、达到阈值、成功观察重置、意图改变重置以及插件注册。测试还应验证该模块不对 state/history 进行写入。

## 参考资料

[1]: https://docs.langchain.com/oss/python/langgraph/overview "LangGraph overview"
[2]: https://openai.github.io/openai-agents-python/ "OpenAI Agents SDK"
[3]: https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/ "Plugins in Semantic Kernel"
[4]: https://www.anthropic.com/engineering/building-effective-agents "Building Effective AI Agents"
