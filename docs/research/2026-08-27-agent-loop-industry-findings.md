# Agent Loop 业界实践核验记录

日期：2026-08-27

## 核验来源与关键事实

LangGraph 的中断模型在触发点持久化图状态，并以稳定线程标识定位后续恢复；恢复会从含中断调用的节点起点重新执行，因此中断前副作用必须幂等。其事件流同时暴露中断载荷、是否中断以及过程中的状态投影。该模式说明：可恢复 Agent Loop 的核心不是单纯保存状态，而是以稳定的暂停标识绑定持久化快照、结构化恢复命令与可观察进度。[1]

OpenAI Agents SDK 明确将 Runner、流式执行、工具执行/批准/错误行为、会话与记忆、追踪、guardrail、交接等配置分开；其执行循环在模型调用、工具调用或交接和终态输出之间反复推进。该模式说明：运行控制（尤其事件投影及在循环各点进行的策略决策）应拥有独立且可替换的能力边界，避免将控制逻辑混进单个模型或工具实现。[2]

## 对 LCA 的对照

LCA 已有持久 checkpoint、`phase_cursor`、resume input adapter、effect idempotency、journal 及 structured approval request。这些已覆盖“挂起后恢复”的基础正确性。

目前 `DeclarativeExecution.execute()` 仅把 `GraphInterpreter` 的结果交给最终投影，循环内的高层进度事件只通过 Journal 与 phase observer 的窄观察面获得；`PhaseObserver` 受设计限制而不得产生控制决策。针对长耗时交互、UI/SSE 投影、审批与恢复编排，缺少一个显式、可组合、只产生事件且无法篡改事务的 **生命周期事件流**。相比把事件回调塞入 runtime 或令 observer 兼任控制，该能力应以独立 contribution registry + composite publisher 进入不可变 runtime binding：实现多插件扩展、稳定排序、故障策略与零状态控制旁路。

设计边界：事件发布方仅接收值对象事件，不能看到可写 `AgentState`、Journal、Reducer、Effect Gateway 或 capability scope；运行时在 `run/resume` 的生命周期边界发布 started / resumed / completed / input_required / failed / cancelled 等事件。发布故障默认 fail-open，严格 profile 可显式 fail-closed。事件可安全承载 `trace_id`、`plan_ref`、`phase_cursor`、状态类别、步骤与预算摘要，供 transport、遥测或审计插件消费。

## References

[1]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph Interrupts documentation"
[2]: https://openai.github.io/openai-agents-python/running_agents/ "OpenAI Agents SDK — Running agents"
