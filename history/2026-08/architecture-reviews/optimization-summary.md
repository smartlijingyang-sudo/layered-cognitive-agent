# Layered Cognitive Agent 架构优化总结

**目标分支：** `main`

**最终远程提交：** [`fdb20c46`](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/fdb20c46)

**状态：** 已推送，工作区与 `origin/main` 一致。

## 先建立背景：这个系统在解决什么问题

LCA 的声明式运行路径可以把一次 Agent 运行理解为“先把配置编译为计划，再按阶段图执行计划”。其中有四类信息必须彼此清晰分离：**插件声明**说明可装配什么，**阶段图**说明按什么顺序走，**执行 wire shape**说明阶段之间传递什么数据，**终态投影**说明完成、暂停或失败时如何留下可恢复的事实。

本轮优化的重点不是改变 Agent 的认知步骤或业务行为，而是让这些概念各自有更明确的落点。这样开发者面对“计划编译失败”“审批暂停”“阶段恢复”中的任一问题时，不必在一个大文件或一个大类中猜测规则来自哪里。

| 优化层面 | 改动后的主要位置 | 对初学者的直接好处 |
|---|---|---|
| 声明式契约 | `declarative_common.py`、`declarative_plugin.py`、`declarative_graph.py`、`declarative_execution.py` | 能先按问题类型找文件，而不是在单个大契约文件中来回跳转。 |
| 终态处理 | `outcome_projection.py`、`approval_pause.py`、`outcome_failure.py` | 能区分“成功如何展示”“审批如何暂停”“失败如何记录”。 |
| 类型边界 | `PhaseRunCursor`、`DeclarativeRunOutcome`、`PhaseContext` | 函数签名直接告诉你允许传什么，而不是用 `Any` 留给调用方猜。 |
| Team seam 替换 | 默认通信与共享内存实现 | 类定义直接声明自己实现的 Protocol，替换点更容易发现。 |

## 已推送的提交与为什么这样拆分

| 提交 | 单项优化 | 为什么要改 | 带来的好处 |
|---|---|---|---|
| [`d3dae65c`](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/d3dae65c) | `refactor(contracts): 按职责拆分声明式计划契约` | 原来的 `declarative_phase_graph.py` 同时存放插件 schema、阶段图、执行游标、结果和 Protocol。阅读一个概念会误触多个无关概念。 | 将共享词汇、插件声明、图与计划数据、执行协议拆开；旧导入路径仍以兼容门面保留，因此调用方不需要为文件整理承担行为风险。 |
| [`d0e600fe`](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/d0e600fe) | `refactor(types): 收紧声明式执行契约边界` | 状态、预算、停止决定、事实等跨层数据使用宽泛 `Any`，错误只能在运行晚期暴露。 | 使用 `AgentState`、`Budget`、`StopDecision`、`RunFact`、`JournalCommitter` 等现有类型；真正开放的扩展载荷使用 `object`，让边界清楚但不强行假设业务载荷。 |
| [`0e0e0aab`](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/0e0e0aab) | `fix(team-seam): 显式声明默认实现的协议继承` | 两个默认 Team seam 类虽然方法形状正确，但没有在签名中声明实现的 Protocol，架构门禁会失败。 | 通信装配器与共享内存解析器现在显式继承其 Protocol；阅读类定义即可知道替换契约，静态检查也能更早发现偏离。 |
| [`fdb20c46`](https://github.com/smartlijingyang-sudo/layered-cognitive-agent/commit/fdb20c46) | `refactor(outcomes): 拆分失败终态投影职责` | `outcome_projection.py` 超过仓库 200 行上限，并同时处理成功、审批暂停、失败三种不同规则。 | 将验证/执行失败收口到 `outcome_failure.py`；成功呈现留在 `outcome_projection.py`，审批暂停复用已独立的 `approval_pause.py`。最终主模块为 **193 行**，符合门禁。 |

> 在同步远程 `main` 时，上游已经合入“统一终态结果投影”和“隔离审批暂停投影”两项等价方向的改动。因此没有保留重复的本地终态模块，而是基于上游的单一实现完成类型边界与失败投影拆分。这避免了两套终态规则并存。

## 一次声明式运行现在如何阅读

下面的顺序可以作为理解代码的入口，而不是必须记住的调用栈。

1. `PluginSpec` 等插件声明放在 `declarative_plugin.py`。它回答“某插件提供什么能力、需要什么能力、属于什么阶段”。
2. 编译器把这些声明和 Profile 组合为阶段图与已编译计划；阶段图的节点、边、控制项放在 `declarative_graph.py`。
3. `PhaseInput`、`PhaseResult`、`PhaseRunCursor`、`DeclarativeRunOutcome` 放在 `declarative_execution.py`。它们是阶段之间稳定传递的数据形状。
4. 图解释器按节点执行。成功完成由 `outcome_projection.py` 形成最终解释结果；审批暂停由 `approval_pause.py` 形成可恢复 cursor；普通失败由 `outcome_failure.py` 写入 `run.failed` 事实。
5. Team 组合若需要替换通信或共享内存后端，可以从 `TeamCommunicationAssemblerProtocol` 与 `TeamSharedMemoryResolverProtocol` 找到对应 seam，再替换明确声明该 Protocol 的默认实现。

这种布局的核心原则是：**图遍历不应该知道失败事实如何写入；失败投影也不应该知道下一条图边如何选择。** 每个 module 因此可以更深——对外接口小，但把本领域复杂度关在内部。

## 验证记录

| 检查 | 结果 | 说明 |
|---|---|---|
| `uv run pytest` | **2961 passed，19 skipped，16 deselected，2 warnings** | 在最终待推送版本运行，全量通过；跳过项为仓库已有的环境依赖或明确标记的场景。 |
| `uv run lint-imports` | **通过** | 保持 contracts、harness、各运行层之间的分层依赖约束。 |
| `uv run python scripts/check_protocol_impl.py` | **通过** | 所有 Protocol 实现均显式继承。 |
| `uv run pytest --no-cov tests/test_code_conventions.py -q` | **5 passed** | 文件行数门禁通过，`outcome_projection.py` 为 193 行。 |
| 隔离 `mypy` 检查 | **通过** | 对声明式执行契约、阶段上下文、治理结果和终态投影的直接类型检查无新增错误。 |

完整 `mypy lca` 仍报告仓库既有的跨模块错误；完整 `ruff check .` 也会在 `vendor/cordis` 的 vendored 代码中报告既有规则问题。这两项均不来自本次变更：本次触及模块的隔离静态检查、分层检查和最终全量测试均已通过。

## 结论

本轮改动把“**声明是什么**”“**图怎么走**”“**阶段之间传什么**”“**运行为什么结束**”分到各自明确的 module。对后续开发而言，最直接的收益不是代码行数减少，而是修改前更容易判断影响范围：改插件声明通常不碰终态规则；增加审批事实不需要修改成功路径；替换 Team 后端能从 Protocol 签名直接找到 seam。

这正是架构优化的目标：将复杂度集中在真正拥有它的地方，让大多数调用方只面对更小、更稳定的 interface。
