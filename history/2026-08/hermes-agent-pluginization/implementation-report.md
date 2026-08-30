# Hermes Agent 对齐：LCA 插件化补强实施报告

**完成日期：** 2026-08-27
**状态：** 已实施并通过完整测试套件
**范围：** 吸收 Hermes Agent 混合工具批次调度的产品能力，并按 LCA 既有的 Body 策略插件路径实现。

## 结论

Hermes 的 `AIAgent` 将 Provider 适配、对话历史、压缩、预算、工具执行、回调、持久化和子代理编排集中在一条循环中。其工具层会把多工具调用划分为可并行安全段与顺序屏障段：安全段并发，交互式、未知或有副作用调用保序。[1] LCA 已有更严格的闭集循环、Body 执行窄门和 Profile 驱动的工具批处理策略；本次不复制 Hermes 的集中式循环或自由 Hook，而是把该调度思想编译为 **Act/Body 内的可替换策略**。本次提交已变基到最新 `main`：其中已合入的[阶段生命周期投影方案](../../../docs/design/2026-08-27-hermes-agent-loop-plugin-integration.md)负责 Hermes callback 面的被动可观测性映射；本变更与之互补，专注于工具调度的安全与时延。

> 本次变更没有新增认知阶段、ActionType、Journal 词表或 State 写入路径。它只在既有 `USE_TOOL` Body 边界选择调用的重叠程度，全部实际副作用仍逐一经过 `SafeExecutor`。

| Hermes 能力/链路 | LCA 中的正确归属 | 本次处理 |
|---|---|---|
| 多工具调用按安全性分为并行段和顺序段 | Act 群的 `ToolBatchExecutionPolicy` | 新增可选的分段计划 SPI 与 `SegmentedSafeToolBatchExecutionPolicy`。 |
| 工具调用的权限、审批、重试、幂等、审计 | `SafeExecutor` / Execution Envelope | 不改变；每个工具仍逐一通过既有窄门。 |
| 原始调用顺序的结果回填 | `UseToolOperation` → `Observation` → tool history | 分段执行后按原始索引顺序聚合结果。 |
| Hook 影响运行 | 观察与治理必须不能绕过双平面 | 不新增 Hook；策略只接收不可变的 `ToolBatchEntry`。 |
| 生命周期与能力选择 | Profile → Plugin Provider → action handler | 使用已有 `lca-tool-batch-execution-policy` Provider；无需修改循环或 Gateway。 |

## 实现设计

### 分段安全调度

新策略把一个已通过 wire gate、且已完成工具查找的批次按模型声明的顺序切为最大连续片段。连续的 `is_idempotent=True` 工具构成一个 `parallel` 段；每个 `is_idempotent=False` 工具构成单工具 `sequential` 屏障。各段严格串行推进，段内由 `asyncio.gather` 并行执行。因此，`read-a → read-b → write → search → stat` 的调度为：`[read-a, read-b]` 并行，`[write]` 顺序，再以 `[search, stat]` 并行。

策略仅看到 `call_id`、`tool_name` 和 `is_idempotent`；它看不到可变参数、具体工具对象、权限或外部系统。`UseToolOperation` 在任一 `SafeExecutor` 调用之前验证计划：片段必须从索引 0 开始、连续、非空、不越界，且恰好覆盖整个原始批次。非法插件计划会被拒绝，且不会产生任何工具副作用。

### 兼容与装配

| 层级 | 修改 | 兼容性 |
|---|---|---|
| `contracts` | 增加 `ToolBatchExecutionSegment`、可选 `ToolBatchSegmentPlanningPolicy` 和计划验证函数。 | 原有 `ToolBatchExecutionPolicy.select_mode()` 保持不变。 |
| `layer1_cognitive` | 增加 `SegmentedSafeToolBatchExecutionPolicy`，并让 `UseToolOperation` 消费可选分段计划。 | `safe`、`parallel`、`sequential` 仍会被自动包装为一个完整批次片段。 |
| `plugins` | 现有 Provider 新增 `segmented_safe` 配置值。 | 没有新增平行插件 schema 或循环 Hook。 |
| `bundles` | `web-app.yaml` 选择 `mode: segmented_safe`。 | Profile 仍可显式选择旧的 `safe`、`parallel` 或 `sequential` 行为。 |

该设计遵守 [ADR-0056](../../../docs/adr/0056-plugin-group-contribution.md)：循环贡献开放但循环闭集不变，插件从既有服务和契约进入，而不创建查找用的平行钥匙或由中心编排者维护名单。

## 变更清单

| 文件 | 变更 |
|---|---|
| `lca/contracts/protocols/tool_batch_execution.py` | 新增分段计划数据模型、可选策略 Protocol 与严格计划验证。 |
| `lca/layer1_cognitive/body/tool_batch_execution.py` | 新增纯策略 `SegmentedSafeToolBatchExecutionPolicy`。 |
| `lca/layer1_cognitive/body/action_handlers.py` | 在 `UseToolOperation` 中选择、验证并逐段执行计划，保持结果顺序和 `SafeExecutor` 边界。 |
| `lca/plugins/providers/tool_batch_execution_policy.py` | 注册 `segmented_safe` Profile 配置模式。 |
| `bundles/web-app.yaml` | 在默认 Web Bundle 启用分段安全策略。 |
| `tests/layer1_cognitive/body/test_tool_batch_execution.py` | 覆盖分段生成、混合并发/顺序边界、结果顺序和非法计划的执行前拒绝。 |
| `tests/fixtures/plan_ref_golden.txt` | 更新默认 Profile 的能力树计划引用。 |

## 验证记录

| 命令 | 结果 |
|---|---|
| `uv run ruff check --fix <changed paths>` | 通过。 |
| `uv run ruff format <changed paths>` | 通过；1 个文件格式化。 |
| `git diff --check` | 通过。 |
| `uv run pytest --no-cov tests/layer1_cognitive/body/test_tool_batch_execution.py -q` | **12 passed**。 |
| `uv run pytest --no-cov tests/layer1_cognitive/body/test_tool_batch_execution.py tests/test_plugin_alignment.py tests/test_plugin_wiring_e2e.py tests/test_plugin_tree_single_owner.py -q` | **74 passed**。 |
| `uv run lint-imports` | 通过；5 项依赖边界均保持。 |
| `uv run python scripts/check_plugin_typing.py` | 通过；251 个插件文件类型标注合规。 |
| `uv run python scripts/check_assembly_purity.py` | 通过；`spawn.py` 纯装配边界保持。 |
| `uv run pytest --no-cov` | **3452 passed，21 skipped，16 deselected**（已在最新 `main` 基线上重跑）。 |
| `uv run mypy lca` | 未通过：基线已有 **286 errors / 200 files**，包括与本次无关的插件装饰器、可观测性和既有委派返回类型问题；未将其误报为本次通过。 |
| 文档和其余脚本门禁 | 链接检查通过（107 文件）。`verify_doc_budgets.py` 因未改动的 `docs/adr/README.md` 超预算 31 词失败；严格文档分层、插件能力、裸 `Any`、裸字符串门禁也分别报告已有违规项，均不触及本次文件。 |

完整测试第一次运行仅因默认 Profile 的 `plan_ref` 金丝雀值随 Bundle 配置变更而失败；已将该受版本控制的期望快照更新为新引用，重跑后全套通过。实施期间远程 `main` 新增了 Hermes callback 的阶段生命周期投影实现；本分支已同步至该基线，能力树快照测试与全套测试均在同步后再次通过。

## 未做事项

本次没有把 Hermes 的 Provider 故障切换、会话租约、请求期 Context Engine、压缩策略或后台子代理结果回注直接移植进 LCA。它们应分别落入现有 Think/Perceive、Session Spine、Memory 和 Collaboration seams，并需单独验证其 Journal、Reducer、权限与恢复语义。将这些横切能力塞进 `CognitiveRuntime._loop` 或新增自由控制 Hook 会违反 LCA 的循环闭集和双平面约束。

## 参考资料

[1] [Hermes Agent — Agent Loop Internals](https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop)
[2] [Hermes Agent — Build a Hermes Plugin](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins)
[3] [Hermes Agent — Architecture](https://hermes-agent.nousresearch.com/docs/developer-guide/architecture)
