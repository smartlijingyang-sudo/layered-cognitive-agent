# Agent Loop 外部架构核实笔记

**日期：**2026-08-27

**用途：**为 LCA 的 Agent Loop 主流能力补齐提供外部设计依据；实现仍以仓库的闭集、Journal、Reducer 与双平面不变量为准。

## 已核实的官方资料

| 来源 | 可采纳事实 | 对 LCA 的约束性落点 |
|---|---|---|
| OpenAI Agents SDK 概览 | SDK 将循环、重复工具调用、分支、交接、会话、追踪、护栏与可恢复审批区分为独立能力；当应用自有自定义循环时，应用必须拥有工具路由、循环和分支。 | LCA 应将这些能力表达为运行时依赖、策略或插件贡献，而不是把控制逻辑回塞入 Gateway 或观察者。 |
| LangGraph Interrupts 文档 | Interrupt 用于暂停执行、等待外部输入并在后续恢复；该语义需要持久化状态作为恢复边界。 | 暂停/恢复属于核心运行时与 checkpoint/journal 的闭合契约，不能依赖进程内 runnable 引用。 |
| DeepSeek Harness 官方介绍 | 模型、工具、技能、会话、沙箱、存储、循环、调度和 UI 均可作为插件替换或重组；内核负责插件挂载、卸载和依赖；所有模型可见内容进入追加式会话日志，恢复、分叉、搜索和重放操作同一事件流。 | LCA 应保持“内核无业务、profile/bundle 组合行为”的边界；新增运行期功能应以可声明、可装配、可撤销的贡献者或 provider 落地。 |
| Semantic Kernel Plugins 文档 | 插件应以功能为中心组织，减少暴露给模型的函数面，并以清晰的函数契约支持组合。 | LCA 插件应聚合单一策略或运行期职责，不创建笼统的跨阶段超级插件；计划与能力声明应限制可见执行面。 |

## 审计结论

本次检查确认，会话层已经具备合作式取消、持久化审批暂停与事实驱动恢复；这些能力不应在核心解释器中重复实现。高价值缺口位于**运行级 wall-clock 预算**与**阶段级 retry/timeout/backoff 策略**之间：原有单阶段策略不会自动受到剩余运行时限约束。

因此，本次只补齐 trusted runtime 的 deadline 闭合。阶段策略仍由独立的 `phase.execution_policy.resilient` 插件经 Profile/Bundle 选择；事务内核在每次尝试和退避前读取已冻结 Budget，以确保策略不能突破 run 的最大 wall-clock。实现不引入新阶段、新事件词表、观察器控制旁路或平行恢复路径。

## References

[1]: https://developers.openai.com/api/docs/guides/agents "OpenAI Agents SDK"
[2]: https://docs.langchain.com/oss/python/langgraph/interrupts "LangGraph Interrupts"
[3]: https://deepseek.com/harness/en/ "DeepSeek Harness developer preview"
[4]: https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/ "Plugins in Semantic Kernel"
