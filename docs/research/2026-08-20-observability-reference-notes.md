# 可观测性重构外部参考笔记

日期：2026-08-20

## DeepSeek Harness 官方表述

DeepSeek Harness 将模型、工具、技能、会话、沙箱、存储、循环、调度与 UI 都建模为可替换、可组合的插件；插件通过服务与事件协作。其核心运行可追溯性来自一个 append-only session log：系统提示词、推理、工具调用及结果、子代理调度、上下文注入均记录于同一事件流，轨迹检查、恢复、分叉、搜索、重放都在该流上工作。[1]

对 LCA 的含义是：可重建 agent 行为的事实应维持为单一 append-only 事实流；插件化应体现在采集、投影和展示可组合，而不能把新的 debug 文件误变为第二个事实源。

## OpenTelemetry 官方语义

OpenTelemetry 将 trace 描述为请求穿过应用的路径，由 spans 表示工作单元。span 具有时间边界、属性、事件、状态与上下文关系；上下文传播用于将跨边界工作关联到同一 trace。[2]

对 LCA 的含义是：OTel 适合成为跨进程/跨服务的互操作投影，而非替换 LCA 的语义化 Agent 事实流。LCA 的 run_id、trace_id、父因果关系和插件身份应在可投影的统一事件封套中保留。

## 初步架构判据

| 判据 | 结论 |
|---|---|
| 事实来源 | Journal 保持唯一可重放、可归约的事实流。 |
| 调试轨迹 | Trace 只可消费事实流，并可接纳非事实诊断事件；必须明确 event class 和 retention，避免误作恢复依据。 |
| 插件模型 | 采集器、投影器、渲染器均以插件/订阅器形式组合，运行内核只保留最小 event envelope 与 append/subscribe 生命周期原语。 |
| 跨系统关联 | run_id、trace_id、causation_id、correlation_id、plugin_id 与 operation 必须在所有记录面一致。 |
| 隐私与成本 | 内容采集必须由策略控制，采用预览、字段级脱敏、预算与采样，而不能由各调用点各自裁剪。 |

## 参考

[1]: https://deepseek.com/harness/en/ "DeepSeek Harness developer preview: Everything is a plugin"
[2]: https://opentelemetry.io/docs/concepts/signals/traces/ "OpenTelemetry: Traces"

## Langfuse 官方数据模型

Langfuse 将 trace 定义为一个请求或操作的逻辑分组，并以 trace_id 关联其所有 observations；observation 则表示 LLM、工具或检索等单步工作，可按应用结构嵌套，并包括 generation 和 event 等 LLM 专用类型。Langfuse 构建于 OpenTelemetry 之上。[3]

对 LCA 的含义是：外部可观测后端可从内部统一封套投影 `run/trace -> operation/observation` 层次，但不应要求业务代码直接耦合某一供应商术语。LCA 应把 agent、插件、交互和传输操作归一为一个稳定的 `ObservationEvent` 语义，再由投影器进行后端专用映射。

[3]: https://langfuse.com/docs/observability/data-model "Langfuse: Core Concepts"

## LCA 现状诊断（代码审阅）

LCA 已有较强的事实流基础：`RunStore.append()` 以词表验证、冻结/深拷贝隔离、`RunScope` 盖章、写入期脱敏、原子提交与故障隔离订阅器构成单一写入仲裁。Journal 已承担重放、归约、SSE、JSONL、OTel 和洞察投影；这应继续是行为事实的唯一来源。

| 发现 | 证据 | 重构决策 |
|---|---|---|
| 诊断盲区仍存在 | `structlog` 在 Hook、网关、运行时和插件路径中记录运行内信息，但不随 run 落盘、无法按 `run_id` 浏览，也不能与 Journal/OTel 关联。 | 保留 `structlog` 仅作进程运维与异常降级；将用户关心的 agent、插件、交互、传输诊断归一到 run-scoped diagnostic event。 |
| 旧 Hook 日志机制是重复旁路 | `default_logging_hook()` 仅把 `hook_triggered` 写到 stderr；实际 hook 运行时又并联 Journal hook。 | 删除 `default_logging_hook` 和 `_safe_repr`；由 `CordisHookRegistry.trigger()` 在唯一触发边界自动发射诊断事件，Journal hook 保持唯一事实发射。 |
| 现有 Journal 不应吸收全部 DEBUG 噪音 | Journal 词表被 CI 强制为一事件一发射点，并承载 replay/reducer/SSE。 | 诊断流不新增 Journal 事实类型，也不参与 replay；以独立、只读的 run-scoped sink 保留。 |
| 现有 Hub 有两套不对称扇出 | OTel spans 从 `Hub` 发射，Journal 从 `RunStore` 订阅；诊断想加入时不能安全复用任一方。 | 在 Hub 内增加最小的 `observe()` / `subscribe()` 诊断通道。它与 Journal 共享 run context、属性策略、生命周期和故障隔离，但不共享事实语义。 |
| 数据传输已有事实与 span，却缺少可读的细节统一视图 | `transport/invocation.py` 已记录委派事实并创建 request/response spans；工具和 LLM 也存在 Journal 与 span 各自投影。 | 在 LLM、工具、传输等现有自动边界以同一诊断封套补充 request/response 元数据、耗时、状态与因果引用，原始内容只能通过统一策略以 preview 形式记录。 |
| 插件行为缺少 run 内可见性 | `AuditedPluginContext` 已收集 provide/require/register/emit，但结果仅用于 Manifest 守卫，未成为运行诊断。 | 在启动期建立插件清单与声明交互摘要，并在 run 开始时写一条 `plugin.inventory` 诊断记录；运行期 `inject`、hook、关键能力调用由统一自动边界补充。 |
| 生命周期要求严格 | 网关已规定 `hub.release()` 先关闭 Journal/live readers，再后台 dispose exporter。 | 诊断 sink 按 Journal reader 随 `release()` 关闭；外部后端仍仅在 `dispose()` 关闭。 |

### 拟采用的最小原语

1. `DiagnosticEvent`：结构化、不可变、带 schema 版本的非事实诊断封套。
2. `DiagnosticSink`：仅含 `on_event()`、`flush()`、`close()` 的只读可替换接收器。
3. `observe(...)`：业务与插件的唯一显式诊断发射面；未绑定时 no-op，字段统一经 `AttributePolicy`。
4. `observed(...)`：异步/同步函数边界的零样板计时、成功/异常采集装饰器或上下文管理器。
5. `DiagnosticJsonlSink` 与 `DiagnosticConsoleRenderer`：文件与 CLI 投影；不是新的 replay/状态来源。

清理原则是删除 `default_logging_hook` 这类仅 stderr、无 run 关联、不可查询的业务日志旁路；保留 `structlog` 于 Hub、导出器、网关等运维失败与服务健康日志。实现将补足 CI 守卫，禁止包外绕过 `observe()` 或在业务层新建自定义诊断写文件。
