# Agent Loop 业界架构调研笔记

**日期：** 2026-08-27  
**范围：** 仅记录本次 Agent Loop 与插件化改进直接相关的可验证设计模式。

| 来源 | 核验到的模式 | 对 LCA 的启示 |
|---|---|---|
| LangGraph 官方概览 | 将有状态、长运行 Agent 的编排与模型、工具等组件分离；同一图中混合确定性节点和 LLM 节点；明确把持久化、恢复、人机协同与观测作为运行时能力。 | 保持 LCA 六阶段语义闭集；让阶段图负责拓扑，让可替换 Provider 负责执行语义；所有状态恢复应基于已冻结的计划与 checkpoint，而非运行期环境查找。 |
| OpenAI Agents SDK 官方文档 | 用少量原语组织 Agent、工具、交接、Guardrail 和 tracing；内置 loop 持续运行至终止条件，同时允许应用保留自定义循环与分支控制。 | 避免为每个治理需求新增循环步骤。将单一“认知深度/重入治理”收敛为一个显式策略 seam，产出可审计的判定，而不使用可修改状态的泛化 Hook。 |
| Semantic Kernel 官方插件文档 | 插件封装一组相关函数，并以语义化输入、输出和副作用描述支撑自动编排；插件可注入必要服务，也可从原生代码、OpenAPI 或 MCP 导入。 | LCA 的运行时插件应以一个**清晰策略职责**为单位，声明输入、输出和治理影响；系统能力通过已冻结的依赖注入，避免插件在执行期访问环境式上下文。 |
| Anthropic《Building Effective AI Agents》 | 区分代码预定义路径的 workflow 与由模型动态指挥工具使用的 agent；强调成功实现采用简单、可组合模式，并以环境反馈和停止条件保持可控。 | 将“何时允许重入认知回路”的判断做成计划显式、纯函数、可替换的策略；避免把多种反思、重试、评审需求各自扩张为新阶段或分散分支。 |

## 初步结论

LCA 的当前声明式运行时已经具备正确的基础：`CompiledRunPlan` 负责声明拓扑，`DeclarativeRuntimeBindings` 在启动前冻结所有执行能力，`GenericPlanInterpreter` 只负责图遍历，`PhaseExecutionTransaction` 将事实、效果和状态归约分离。后续补齐应遵从这一骨架，优先添加**一个围绕计划内重入与认知深度的纯策略插件**，而不是新增认知阶段、平行事件模型或运行期动态能力查找。

## 参考资料

[1]: https://docs.langchain.com/oss/python/langgraph/overview "LangGraph overview"
[2]: https://openai.github.io/openai-agents-python/ "OpenAI Agents SDK"
[3]: https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/ "Plugins in Semantic Kernel"
[4]: https://www.anthropic.com/engineering/building-effective-agents "Building Effective AI Agents"
