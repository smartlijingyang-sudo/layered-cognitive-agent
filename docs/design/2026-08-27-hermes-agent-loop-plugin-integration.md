# Hermes Agent 对标：以 LCA 插件架构补齐 Agent Loop 进度与韧性链路

| 字段 | 内容 |
|---|---|
| 日期 | 2026-08-27 |
| 状态 | 已实现并验证 |
| 范围 | Hermes Agent 核心能力、Agent Loop 链路，以及 LCA 的插件化对齐实现 |
| 相关约束 | 认知原语宪法 v3、ADR-0002、Harness Spine Spec |

## 摘要

Hermes Agent 的核心价值并不只是一次模型调用后的工具执行，而是将**上下文治理、可取消模型调用、工具调度、预算、降级、持久化以及实时回调**置于稳定的循环内。其每次回合在模型响应与工具结果之间迭代；工具调用会根据数量及交互属性按并发或串行方式运行，并向调用载体暴露思考、工具、步骤与状态信号。[1]

LCA 已经拥有更严格的基础：认知闭集固定为 `perceive → think → act → reflect → remember → stop`，世界副作用被收束于 Act/Body，状态仅可经 Reducer 变更，且声明式解释器将图遍历、阶段事务和终态投影分离。因而本次不复制 Hermes 的可改写 Hook 模式，也不新增第七阶段或第二套事件词表；而是沿既有 **Protocol → Registry → Provider → Profile → frozen binding** 链路补齐一个此前缺失的能力：对每个实际阶段访问发布安全、被动、可插拔的进度生命周期事件。

> **设计结论：** Hermes 的实时 callback 面应在 LCA 中编译为被动的生命周期投影插件，而不应成为改变 `AgentState`、`Decision`、`Journal` 或副作用执行顺序的控制 Hook。

## Hermes Agent 的关键能力与执行循环

Hermes 的 `AIAgent` 负责提示词与工具 schema 装配、跨 API 格式的消息适配、支持取消的模型请求、工具调用执行、上下文压缩、重试/备用模型，以及会话记忆持久化。官方文档给出的常规循环是：接收用户消息后构建或复用 system prompt；预检查上下文压力；转换 provider 消息；注入临时预算提示；调用模型；如返回工具调用则执行并写回结果后重新进入模型调用，如返回文本则持久化并结束本回合。[1]

| Hermes 环节 | 作用 | LCA 对应落点 | 本次处理 |
|---|---|---|---|
| 提示词/上下文准备 | 缓存 prompt、压缩与临时预算提示 | PerceiveHub、Context Lifecycle、Brain/PromptRenderer | 保持现有分层，不复制到循环外。 |
| 模型调用与重试/降级 | 可取消请求、失败后尝试 fallback provider | Reasoner、LLMAdapter failover 与其策略 | 作为 Think 群内的 L0 adapter 韧性能力，不升格为 loop 阶段。 |
| 多工具执行 | 单调用直接执行，多调用并发；交互式工具保持串行；按请求顺序写回 | Body、SafeExecutor、`ToolBatchExecutionPolicy` | 现有 safe/parallel/sequential policy 已覆盖，不重复造插件。 |
| 上下文压缩与会话持久化 | 避免超窗前丢失记忆，支持恢复 | MemoryPolicy、StateStore、Journal、Checkpoint | 维持现有责任边界。 |
| 回调面 | tool progress、thinking、reasoning、clarify、step、stream delta、status | PhaseObserver、RuntimeLifecyclePublisher、Gateway/SSE 投影 | 补齐为 phase 生命周期事件。 |

Hermes 的插件以 manifest 与 `register(ctx)` 组成，可注册工具、钩子、命令、平台、模型、记忆、上下文压缩或审批传输，并通过不同来源的发现优先级实现覆盖。项目本地插件默认需要显式信任后才加载，这一点体现了扩展机制必须同时具备**可替换性与供应链边界**。[2] LCA 现有的 Profile 解析、Plugin Manifest、Registry 与冻结运行绑定提供了同一目标的更强约束版本。

## LCA 当前 Agent Loop 的真实链路

LCA 的 `CognitiveRuntime` 仅持有 fresh/resume 边界、取消处理和终态生命周期投影。一次可运行的 turn 由 `DeclarativeRuntimeBindings` 冻结所有 profile 选择的依赖，继而通过 `DeclarativeRuntimeDriver`、`DeclarativeExecution` 和 `GenericPlanInterpreter` 解释已编译的阶段图。解释器只负责遍历与边选择；`PhaseExecutionTransaction` 才负责阶段输入治理、executor 调用、事实/证据记录、效果网关和 Delta 归约；`RunOutcomeProjector` 负责审批暂停、失败和完成的终态表达。

```text
CognitiveRuntime.run / resume
  → DeclarativeRuntimeBindings（冻结 Profile 选择的依赖）
  → DeclarativeRuntimeDriver
  → DeclarativeExecution
  → GenericPlanInterpreter（遍历 + 选边）
  → PhaseExecutionTransaction（执行 + fact/effect/delta）
  → RunOutcomeProjector（completed / approval / failed）
```

这一拆分满足宪法的四条关键纪律：循环阶段不扩张；解释器不在阶段内部执行副作用；Reducer 是状态变更的唯一入口；Journal 与投影不反向决定下一条边。既有 `ToolBatchExecutionPolicy` 已消化了 Hermes 多工具调度中最核心的安全差异，因此本次新增功能应只解决**阶段级实时可观测性**，不能把回调变为流程控制。

## 补齐方案：被动 Phase Lifecycle Publication

既有 `RuntimeLifecyclePublisher` 仅在 `started`、`resumed` 与最终 `completed/partial/input_required/failed/canceled` 等运行边界工作。既有 `PhaseObserver` 虽可在阶段前后以只读上下文包裹执行，但对外缺少统一、可消费且不包含结果内容的 `started/completed/failed` 数据契约。本次将 phase 进度扩展为原有生命周期枚举内的三个新事件：`phase_started`、`phase_completed` 与 `phase_failed`。

| 事件 | 发射时机 | 可见载荷 | 明确排除 |
|---|---|---|---|
| `phase_started` | 已验证当前 node、调用阶段事务之前 | trace、plan、状态、step、预算、node、semantic phase | task、state、artifact、prompt、工具参数、模型输出。 |
| `phase_completed` | 阶段事务正常返回之后、解释器选边之前 | 上述载荷与归一化 `result_kind` | executor payload、错误详情、审批内容。 |
| `phase_failed` | 阶段事务抛出未被阶段策略归一化的异常时 | 上述安全标识 | 异常文本、堆栈及任何内部对象。 |

受 retry policy 管控且被转为 `PhaseResult(result_kind="phase_error")` 的业务失败，故意表现为 `phase_completed`，令订阅者以 `result_kind` 区分受控失败与编排异常；只有未归一化事务异常才发出 `phase_failed`。审批暂停沿现有终态投影处理，进度事件不携带任何审批数据。

```text
Profile / Bundle
  → RuntimeLifecycleSubscriberRegistry
  → CompositeRuntimeLifecyclePublisher（按优先级冻结贡献）
  → DeclarativeRuntimeBindings.lifecycle_publisher
  → DeclarativeInterpreterFactory.create(..., lifecycle_publisher=...)
  → GenericPlanInterpreter
       ├─ phase_started
       ├─ PhaseExecutionTransaction
       └─ phase_completed / phase_failed
  → 日志、SSE、审计或诊断订阅插件
```

该流向将 Hermes 的“callback surface”映射为 LCA 的**被动投影面**。订阅者只接收 frozen、carrier-safe dataclass，且 publisher 在 profile boot 后被冻结；它们不会取得 `AgentState`、restricted phase context、Journal、Reducer、EffectGateway 或工具结果，因此不能形成绕过执行治理的旁路。订阅者故障仍复用既有 `fail_open/fail_closed` 策略，优先级与重复 ID 校验也保持不变。

## 已实现变更

| 文件 | 变更 | 架构效果 |
|---|---|---|
| `lca/contracts/protocols/runtime_lifecycle.py` | 增加 phase 事件闭集以及 `semantic_phase`、`result_kind` 安全字段。 | 复用单一 lifecycle 协议，不引入平行 schema。 |
| `lca/contracts/protocols/runtime_composition.py` | 将 `RuntimeLifecyclePublisher` 加入 `DeclarativeInterpreterFactory.create` 的显式依赖。 | 自定义解释器工厂也能获得同一冻结发布器。 |
| `lca/runtime/runtime_bindings.py` | 从 immutable binding 将 publisher 传入新解释器。 | fresh/resume 共享一致的运行时闭包。 |
| `lca/plugins/providers/declarative_runtime_seams.py` | 默认解释器工厂把 publisher 接线到 `GenericPlanInterpreter`。 | 默认 Profile 无需新硬编码即可启用。 |
| `lca/harness/declarative/interpreter.py` | 在每次 phase transaction 前后发布 started/completed/failed 事件。 | 事件发生在稳定编排边界，发布逻辑不改状态也不选边。 |
| `tests/declarative/test_phase_lifecycle_publication.py` | 新增正常、故障与安全载荷契约测试。 | 防止进度事件变为内容泄露或错误的控制面。 |
| `lca/infrastructure/llm_adapter/failover.py` | 提供候选内 `RetryingLLMAdapter`、有序 `FailoverLLMAdapter` 与不可变候选对象。 | 重试和 provider 切换均限制在 L0，不暴露给 Brain、Gateway 或声明式图。 |
| `lca/plugins/seam_definitions/llm_resolver.py` | Profile `RetryConfig` / `FallbackConfig` 构造候选并注册单一 resilient chat adapter。 | 每个候选先受控重试，备用选择仍由配置声明且凭据只经 resolver plugin 读取。 |
| `tests/test_llm_failover.py` | 覆盖有序重试后切换、不可重试隔离、流式不拼接与 Profile 组装。 | 防止 retry/failover 造成重复输出或隐藏的 provider 状态修改。 |

## 验收与后续扩展

本实现测试了六个正常语义阶段的严格 `started → completed` 顺序、事件标识与预算一致性、归一化 `result_kind`、未归一化故障的 `started → failed` 配对、以及 dataclass 不暴露敏感字段。运行绑定测试还确认发布器以显式参数进入可替换解释器工厂。全量套件随后验证了 Profile、插件树、声明式恢复、网关和跨层约束未发生回归。

Provider 韧性链已按上述约束完成：`complete()` 对每个 Profile 候选先执行有界重试，仍失败时才依次尝试下一个候选；`stream()` 只会在尚未产出任意事件时重试或切换，避免混合一次或两个 provider 的输出。重试耗尽后保留候选的原始错误，所有候选均不可用时最终错误继续由调用方的既有失败处理消费。下一步若需要让前端或外部平台消费更富语义的“thinking/tool progress/stream delta”，应优先扩展现有 Journal 投影或增加独立**订阅插件**，而不是让 Gateway 直连具体 Brain、Body 或循环实现。

## 二次审计：剩余能力与本轮范围

完成 phase 生命周期投影后，对当前 `main` 重新按 Hermes 的 Agent Loop 能力清单审计。工具进度并非空白：`SimpleSafeExecutor` 已在受控权限、校验、重试与审批路径中发射 `ToolStarted`、`ToolInvoked`、`ToolDenied` Journal 事实及运行诊断，Gateway 的 live tail 已将这些 Journal 投影为 SSE。模型推理文本和输出增量也已由 `TelemetryLLMAdapter` 处理为结构化流事件；会话持久化、审批暂停/恢复、checkpoint 与预算停止同样已有单一职责实现。因此，不应为 Hermes 的 callback 名称再新增平行事件总线或直接把回调耦合到 Gateway。

本轮已补齐的核心链路是**候选内有界重试与有序 LLM provider failover**。Profile 以结构化 `RetryConfig` 声明每个候选的最大尝试次数及指数退避，以 `FallbackConfig` 声明候选模型、可选 endpoint、可选 API style 和可选凭据；LLM resolver plugin 在唯一的凭据解析边界构造 `LLMFailoverCandidate`，并将每个候选包装为 `RetryingLLMAdapter`，随后在存在两个及以上候选时注册单一 `FailoverLLMAdapter`。调用方仍只依赖 `LLMAdapter`，不读取第二套环境变量、不创建隐式 provider，也不改变 Registry 的 active 选择。

| Hermes 能力 | LCA 当前归属 | 结论 |
|---|---|---|
| Tool progress 与工具并发/串行 | SafeExecutor、Tool Journal、ToolBatchExecutionPolicy、Journal SSE | 已覆盖；保持现有事实与投影路径。 |
| Thinking / reasoning / stream delta | TelemetryLLMAdapter、LLMStreamEvent、Journal SSE | 已覆盖；保持流事件单一来源。 |
| 人工审批、暂停和恢复 | Approval、Checkpoint、ResumeInput、Driver | 已覆盖；不新增 callback 控制面。 |
| 上下文/记忆持久化与压缩 | `SemanticCompactionPolicy`、`Memory.perceive`、Context Journal | **本轮补齐 extractive shadow/enforce 语义压缩。** |
| 迭代与运行预算 | Budget、StopRule、声明式图保护 | 已覆盖；fallback 不改变 budget 归约语义。 |
| Provider retry / fallback | ProductionLLMResolver 与 LLM provider registry | **本轮补齐。** |


## 语义 Context Compaction 设计及验收契约

Hermes 会在上下文压力下保护系统头部和近期尾部、压缩中段并用摘要替换其表面历史。[1] LCA 不将该逻辑改造成新的 Agent Loop 阶段或独立 Sensor；它保留在现有 `Memory.perceive` 中，由 Profile 选择的 `memory.compaction_policy` capability 承载，符合认知原语宪法的“只有 CompactionPolicy 可压缩、原始 Journal 永不删除”约束。

本次实现的 `SemanticCompactionPolicy` 先以确定性 extractive 摘要建立可审计的安全边界。它识别 `metadata.compaction_anchor=true` 的不可切割记录，先按现有 recency policy 保留精确记录；针对其余来源，生成含 `source_record_ids`、`provenance="memory.compaction"` 的 `UNTRUSTED_HISTORY` summary record。摘要在 PromptReasoner 中自然进入“不可信历史证据”数据通道，不能覆盖当前任务、系统策略或工具权限。

| 模式 | 行为 | 安全语义 |
|---|---|---|
| `shadow`（默认） | 生成候选摘要与覆盖/尺寸报告，但将原有精确 Top-K 视图交给 Reasoner。 | 先观察候选质量和收益，不改变模型 surface。 |
| `enforce` | 为摘要保留一个上下文槽位，以来源完整的 summary 替换低优先级记录。 | 仅在 summary 小于其覆盖来源时提交；锚点超过预算时 fail closed，返回完整上下文。 |

`ContextCompacted` 仅记载模式、是否实际替换、原因、来源数量、summary id 及长度比率，不复制摘要正文或原始内容。策略本身不写 Memory Store、不改 `AgentState`，而是作为既有 `perceive()` 的纯输入视图转换返回新 state 值。后续若要接入模型生成的摘要，应替换摘要生成器而非改动 Loop：仍须保留同一 provenance、锚点、收益检查与 shadow-first 门禁。

## Provider 重试与回退设计及验收契约

Retry 与 failover 都不是 Gateway 策略，也不是新的 run mode。它们是位于 L0、实现既有 `LLMAdapter` 协议的组合装饰器：每个候选先由 `RetryingLLMAdapter` 按其不可变 `LLMRetryPolicy` 处理可恢复的基础设施/提供方错误，`FailoverLLMAdapter(LLMFailoverCandidate, ...)` 仅在候选的有界重试耗尽后才切换至下一个 Profile 候选。上游 Brain、Reasoner、Telemetry 和 Gateway 继续只依赖 `LLMAdapter`，无须知道发生了重试或 provider 切换。

| 维度 | 约束 |
|---|---|
| 配置 | `lca-llm-resolver` 的 Profile Config 使用 `retry: RetryConfig` 与 `fallbacks: tuple[FallbackConfig, ...]`；重试项声明最大尝试次数和有界指数退避，候选的 endpoint、API style 与凭据可继承 primary。 |
| 构造 | Resolver plugin 是唯一的凭据读取和候选构造边界；它把 primary 与 `fallback-1...n` 编译为不可变 `LLMFailoverCandidate`，并为每一个候选装配同一不可变重试策略。 |
| 顺序 | 每个候选先按 Profile 的 `max_attempts` 尝试，重试耗尽后才进入下一个候选；首个成功结果立即返回，候选名在构造时保证非空且唯一。 |
| 失败分类 | 仅重试或切换于 `TimeoutError`、`ConnectionError`、`OSError`、`LLMUnavailableError` 或带 HTTP `status_code` 的 401/403/408/409/425/429/5xx；编程错误、参数校验错误和取消不重试也不切换。 |
| 流式安全 | 在首个 `LLMStreamEvent` 发出前允许重试或切换；一旦输出过事件，后续异常原样抛出，避免重放同一请求或把两家 provider 的 token 拼接到同一响应。 |
| 可观测性 | 不额外复制 prompt、token、凭据或 response 内容；现有 TelemetryLLMAdapter 仍保持调用级观测单一来源。 |
| 失败语义 | 所有候选失败时抛出最后一个原始异常；避免包装为不兼容的新错误类型。 |

| 验收项 | 测试 |
|---|---|
| 有界重试后切换 | primary 的可重试失败后先在同一候选内重试；耗尽后调用第一个备用 adapter，成功即不触达后续 adapter。 |
| 选择限制 | 不可重试异常不重试也不切换；取消不被捕获。 |
| 流式完整性 | 无事件的失败可重试或转备用；已发送事件的失败不重试也不切换。 |
| Profile 组装 | resolver plugin 根据 `RetryConfig` / `FallbackConfig` 构造 primary 与候选 adapter，仅在实际需要时装配重试与回退 wrapper。 |
| 兼容性 | 没有 fallback 时仍注册原始 primary adapter，现有 resolver 与调用方无需变更。 |

## 参考资料

[1]: https://hermes-agent.nousresearch.com/docs/developer-guide/agent-loop "Hermes Agent — Agent Loop Internals"
[2]: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins "Hermes Agent — Plugins"
