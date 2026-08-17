"""架构一致性元测试 —— 确保 L0-L3 每个具体类都显式声明了 Protocol 基类。

不再逐个手动列举实现类，而是扫描 L0-L3 所有模块，枚举每一个具体类，
断言它要么显式声明了 contracts.protocols 里的某个 Protocol 作为基类，
要么在 EXEMPT 白名单中注明了 ADR 依据。

"默认拒绝"——新类不声明协议就直接挂在 CI 上，不依赖任何人"记得"。
"""

from __future__ import annotations

import ast
import importlib
import inspect
import pkgutil
import unittest
from pathlib import Path

# ── 豁免清单 ──────────────────────────────────────────────────────────
# 键: 类的全限定名 (qualname)
# 值: 豁免理由（必须引用 ADR 编号）
#
# 豁免标准：
#   1. DI 注册表 / 路由基础设施——它们是协议接线机制本身，不是被接线的组件
#   2. 内部数据结构——不跨越模块边界、不需要运行时多态
#   3. 异常类型——错误信号，不是可插拔组件
EXEMPT: dict[str, str] = {
    "lca.layer0_infra.ops.upstream_mirror.PackageInventory": (
        "upstream 镜像校验的纯数据值对象 (Upstream Mirror)"
    ),
    "lca.layer0_infra.ops.upstream_mirror.UpstreamTree": (
        "upstream 镜像校验的纯数据值对象 (Upstream Mirror)"
    ),
    "lca.layer0_infra.ops.upstream_mirror.LocalMirror": (
        "upstream 镜像校验的纯数据值对象 (Upstream Mirror)"
    ),
    "lca.layer0_infra.ops.upstream_mirror.MirrorDiff": (
        "upstream 镜像校验的纯数据值对象 (Upstream Mirror)"
    ),
    "lca.layer0_infra.computer.background.BackgroundCommandRecord": (
        "后台命令追踪值对象，run-scoped 内部状态 (Computer Use)"
    ),
    "lca.layer0_infra.computer.background.BackgroundCommandRegistry": (
        "后台命令 run-scoped 注册表，非跨层契约 (Computer Use)"
    ),
    "lca.layer0_infra.computer.op_result.ComputerOpResult": (
        "Computer 操作结果值对象，MachineComputer / SandboxComputer 共享 (Computer Use)"
    ),
    "lca.layer0_infra.computer.sandbox_computer.SandboxComputer": (
        "沙箱产品环境适配器，PlaneRef + Sandbox + guest 脚本 (Execution Planes)"
    ),
    "lca.layer0_infra.computer.sandbox_computer._SandboxComputerBase": (
        "SandboxComputer 文件操作基类，模块内部组合 (Computer Use)"
    ),
    "lca.layer0_infra.computer.runtime.ComputerRuntime": (
        "SandboxComputer 向后兼容别名 (Computer Use)"
    ),
    "lca.layer0_infra.computer.runtime_exec.ComputerRuntimeExecMixin": (
        "SandboxComputer shell/execute 混入，模块内部组合 (Computer Use)"
    ),
    "lca.layer0_infra.tools.lca_computer.executor.LcaComputerExecutor": (
        "manifest 驱动的 computer 执行器，内部路由 (Execution Alignment)"
    ),
    "lca.layer0_infra.tools.lca_computer.executor.LcaSandboxExecutor": (
        "manifest 驱动的 sandbox 执行器，内部路由 (Execution Alignment)"
    ),
    "lca.layer0_infra.tools.lca_computer.types.ApiName": (
        "camelCase API 名称枚举，纯数据声明 (Execution Alignment)"
    ),
    "lca.layer0_infra.tools.calculator.CalculatorExecutor": (
        "manifest 驱动的计算器执行器 (Execution Alignment)"
    ),
    "lca.layer0_infra.tools.weather.WeatherExecutor": (
        "manifest 驱动的天气执行器 (Execution Alignment)"
    ),
    "lca.layer0_infra.tools.web_search.WebSearchExecutor": (
        "manifest 驱动的搜索执行器 (Execution Alignment)"
    ),
    "lca.layer0_infra.tools.write_file.WriteFileExecutor": (
        "manifest 驱动的写文件执行器 (Execution Alignment)"
    ),
    "lca.layer0_infra.tools.ask_user.AskUserExecutor": (
        "manifest 驱动的 HIL 执行器 (Execution Alignment)"
    ),
    "lca.layer0_infra.plane.execution_target.ExecutionTarget": (
        "执行目标枚举，纯数据声明 (Execution Alignment)"
    ),
    "lca.layer0_infra.plane.execution_target.ExecutionPlan": (
        "执行计划值对象，纯数据声明 (Execution Alignment)"
    ),
    "lca.layer0_infra.device_gateway.client.GatewayHttpClient": (
        "device-gateway HTTP 客户端，对标 LobeHub GatewayHttpClient"
    ),
    "lca.layer0_infra.device_gateway.client.DeviceToolCallResult": (
        "device-gateway 工具调用结果值对象"
    ),
    "lca.layer1_cognitive.body.action_catalog.ActionSpec": (
        "纯数据声明（action_type 元数据），非可插拔行为实现；见 ActionCatalog PR-4"
    ),
    "lca.layer0_infra.component_registry.ComponentRegistry": (
        "DI 注册表本身，非可插拔组件 (ADR-0005)"
    ),
    "lca.layer0_infra.component_registry.RegistryKeyError": ("异常类型，非可插拔组件 "),
    "lca.layer0_infra.transport.transport_registry.TransportNotFoundError": (
        "异常类型，非可插拔组件 "
    ),
    "lca.layer1_cognitive.body.action_registry.ActionRegistry": (
        "ActionRegistryProtocol 实现，Protocol 在 contracts.protocols.action (ADR-0015/0016)"
    ),
    "lca.layer1_cognitive.body.action_handlers.RespondOperation": (
        "Action 策略实现，Protocol 定义在 contracts.protocols.action"
    ),
    "lca.layer1_cognitive.body.action_handlers.UseToolOperation": (
        "Action 策略实现，Protocol 定义在 contracts.protocols.action"
    ),
    "lca.layer1_cognitive.body.action_handlers.DelegateOperation": (
        "Action 策略实现，Protocol 定义在 contracts.protocols.action"
    ),
    "lca.layer1_cognitive.body.action_handlers.HandoffOperation": (
        "Action 策略实现，Protocol 定义在 contracts.protocols.action"
    ),
    "lca.layer1_cognitive.member_status.in_memory.InMemoryMemberStatus": (
        "MemberStatus 实现，数据契约定义在 contracts.models.team.member_status (ADR-0015)"
    ),
    "lca.layer3_agent.orchestration_strategies.graph.strategy.GraphExecutionState": (
        "BFS 执行状态 dataclass，纯内部数据结构，非可插拔组件"
    ),
    "lca.layer1_cognitive.brain.default_factory.SimpleBrainFactory": (
        "BrainFactory Protocol 可调用实现 "
    ),
    "lca.layer1_cognitive.brain.decision_gates.must_consult_all.MustConsultAllMembers": (
        "DecisionGate 实现，Protocol 在 contracts.protocols.cognition "
    ),
    "lca.layer2_runtime.default_stop_rule.DefaultStopRule": (
        "StopRule 实现，Protocol 在 contracts.stop (ADR-0015)"
    ),
    "lca.layer2_runtime.agent_runtime.phases.AgentPhase": (
        "LobeHub agent-runtime phase 枚举，文档契约非可插拔组件 (G2A 对齐)"
    ),
    "lca.layer1_cognitive.member_status.required_action.RequiredAction": (
        "纯数据声明（gate 裁决结果），非可插拔组件"
    ),
    "lca.layer1_cognitive.member_status.consult_policy.ConsultNextAction": (
        "纯数据声明（ConsultPolicy 下一步），非可插拔组件 (ADR-0049)"
    ),
    "lca.layer0_infra.llm_adapter.api_style.LLMApiStyle": (
        "L0 wire-protocol 配置枚举，非跨层契约 (ADR-0038)"
    ),
    "lca.layer0_infra.sandbox.streaming.SandboxStreamEmitter": (
        "沙箱适配器内部 seq 发射器，非可插拔组件 (ADR-0044)"
    ),
    "lca.layer0_infra.file_store.LocalFileStore": (
        "FileStore Protocol 定义在 L0 本模块，非 contracts.protocols (ADR-0043)"
    ),
    "lca.layer0_infra.file_store.StoredFile": ("文件产物元数据值对象，纯数据结构 (ADR-0043)"),
    "lca.layer0_infra.llm_adapter.openai_compat._chat_completions._ChatCompletionsStrategy": (
        "OpenAICompatAdapter 内部 Strategy，模块私有 (ADR-0038)"
    ),
    "lca.layer0_infra.llm_adapter.openai_compat._responses._ResponsesStrategy": (
        "OpenAICompatAdapter 内部 Strategy，模块私有 (ADR-0038)"
    ),
    "lca.layer0_infra.llm_adapter.openai_compat._anthropic_messages._AnthropicMessagesStrategy": (
        "OpenAICompatAdapter 内部 Strategy，模块私有 (ADR-0038)"
    ),
    "lca.layer0_infra.llm_adapter.openai_compat._anthropic_stream._AnthropicStreamDecoder": (
        "Anthropic SSE → LLMStreamEvent 状态机，adapter 内部 (ADR-0038)"
    ),
    "lca.layer0_infra.llm_adapter.openai_compat._shared._RawToolCall": (
        "L0 内部 tool_call 归一化 NamedTuple，非可插拔组件 (ADR-0038)"
    ),
    "lca.layer0_infra.llm_adapter.openai_compat._shared.ThinkTagStreamSplitter": (
        "流式 content 拆分器，adapter 内部状态机 (ADR-0038)"
    ),
    "lca.layer0_infra.llm_adapter.settings.LLMSettings": (
        "pydantic-settings 生成参数配置模型，非可插拔组件"
    ),
    "lca.layer0_infra.skills.settings.SkillSettings": (
        "pydantic-settings 技能库配置模型，非可插拔组件 (ADR-0048)"
    ),
    "lca.layer0_infra.skills.url_sources.ParsedSkillUrl": (
        "URL 解析结果值对象，纯数据结构 (ADR-0048)"
    ),
    "lca.layer0_infra.skills.marketplace.LobeHubMarketClient": (
        "Market HTTP 辅助客户端，SkillImporter 内部依赖 (ADR-0048)"
    ),
    "lca.layer0_infra.llm_adapter.tool_arguments.ToolArgumentsOk": (
        "tool arguments wire 三态 Outcome 值对象，纯数据结构 (ADR-0047)"
    ),
    "lca.layer0_infra.llm_adapter.tool_arguments.ToolArgumentsIncomplete": (
        "tool arguments wire 三态 Outcome 值对象，纯数据结构 (ADR-0047)"
    ),
    "lca.layer0_infra.llm_adapter.tool_arguments.ToolArgumentsInvalid": (
        "tool arguments wire 三态 Outcome 值对象，纯数据结构 (ADR-0047)"
    ),
    # ── 可观测性子系统（OTel 骨干重建后）──
    "lca.layer0_infra.observability.facade.SpanContext": ("correlation 值对象，非可插拔组件"),
    "lca.layer0_infra.observability.handles.SpanHandle": ("span 句柄内部类型，非公共组件"),
    "lca.layer0_infra.observability.handles.NullSpanHandle": ("span 句柄 no-op 内部类型"),
    "lca.layer0_infra.observability.handles._IsolatedExporter": ("导出器故障隔离包装，子系统内部"),
    "lca.layer0_infra.observability.policy.AttributePolicy": ("属性脱敏/截断策略，子系统内部"),
    "lca.layer0_infra.observability.policy.Verbosity": ("信息量档位配置枚举，非组件"),
    "lca.layer0_infra.observability.settings.ObservabilitySettings": (
        "pydantic-settings 配置模型，非组件"
    ),
    "lca.layer0_infra.observability.team_profile.TeamTraceProfile": (
        "团队 span 静态档案值对象，纯数据结构，非可插拔组件 (ADR-0034)"
    ),
    "lca.layer0_infra.observability.view.SpanView": ("ReadableSpan 投影值对象，非组件"),
    "lca.layer0_infra.observability.exporters.langfuse.ExporterUnavailableError": ("异常类型"),
    "lca.layer0_infra.observability.registry.UnknownExporterError": ("异常类型"),
    # ── RunStore（ADR-0055 唯一写入仲裁）──
    "lca.layer0_infra.observability.journal.engine.RunStore": (
        "唯一写入仲裁，subscriber 侧协议为 JournalProjector"
    ),
    "lca.layer0_infra.observability.journal.engine.UnregisteredJournalEventError": ("异常类型"),
    "lca.layer0_infra.observability.journal.reducer.RunState": (
        "纯数据派生结果（ADR-0055 fold_run_state 输出）"
    ),
    "lca.layer0_infra.observability.journal.reducer.RunStatus": (
        "纯数据枚举（ADR-0055 派生状态词表）"
    ),
    "lca.layer0_infra.observability.journal.console_projector._TraceState": (
        "console 投影内部累加器（同 _RunDigest 先例）"
    ),
    "lca.layer0_infra.observability.journal.journal_io.JournalFormatError": ("异常类型"),
    "lca.layer0_infra.observability.journal.otel_span_index.SpanContainerIndex": (
        "OtelProjector 内部容器索引机制件（同 _IsolatedExporter 先例）"
    ),
    "lca.layer0_infra.observability.llm_stream_activity.LlmStreamActivityTracker": (
        "LLM 流活动心跳内部 tracker，非可插拔组件 (ADR-0051)"
    ),
    "lca.layer0_infra.observability.response_text_stream.ResponseTextStreamExtractor": (
        "LLM 流式 response_text 提取器，LobeHub 内容边界内部机制件 (ADR-0051)"
    ),
    "lca.layer0_infra.workspace.artifact_ledger.ArtifactLedger": (
        "Run 级产物账本，Workspace 内部数据结构 (ADR-0051)"
    ),
    "lca.layer0_infra.workspace.scope.RunWorkspace": (
        "Run 级 workspace 上下文值对象，非可插拔组件 (ADR-0051)"
    ),
    "lca.layer1_cognitive.brain.decision_gates.chained.ChainedDecisionGate": (
        "DecisionGate 组合器，Protocol 在 contracts.protocols.cognition (ADR-0051)"
    ),
    "lca.layer1_cognitive.brain.decision_gates.terminal_respond.TerminalRespondGate": (
        "DecisionGate 实现，Protocol 在 contracts.protocols.cognition (ADR-0051)"
    ),
    "lca.layer1_cognitive.brain.decision_gates.tool_loop_breaker.ToolLoopBreakerGate": (
        "DecisionGate 实现，Protocol 在 contracts.protocols.cognition (ADR-0051)"
    ),
    "lca.layer1_cognitive.brain.decision_gates.artifact_respond_injector.ArtifactRespondInjector": (
        "DecisionGate 实现，Protocol 在 contracts.protocols.cognition (ADR-0051)"
    ),
    "lca.layer1_cognitive.brain.decision_gates.office_works_sealer.OfficeWorksSealer": (
        "DecisionGate 实现，Protocol 在 contracts.protocols.cognition (ADR-0051)"
    ),
    "lca.layer1_cognitive.brain.llm_turn.mode.LlmTurnMode": (
        "LobeHub call_llm 模式枚举，非跨层契约 (G2A agent-runtime 对齐)"
    ),
    "lca.layer0_infra.search.models.SearchHit": ("Search 平面结果值对象，非可插拔组件 (ADR-0053)"),
    "lca.layer0_infra.search.models.SearchResponse": (
        "Search 平面响应值对象，非可插拔组件 (ADR-0053)"
    ),
    "lca.layer0_infra.search.models.SearchRunState": (
        "Search run 上下文值对象，非可插拔组件 (ADR-0053)"
    ),
    "lca.layer0_infra.search.settings.SearchSettings": (
        "Search 平面 pydantic-settings 配置，非可插拔组件 (ADR-0053)"
    ),
    "lca.layer0_infra.skills.market_auth._CachedToken": (
        "Market OAuth token 缓存值对象，纯内部数据结构 (ADR-0048)"
    ),
    "lca.layer0_infra.llm_resolver.ProductionLLMResolver": (
        "LLMResolver Protocol 的实现，纯 env 读取 + 委托 resolve_llm_adapter"
    ),
    "lca.layer0_infra.llm.catalog.ModelRegistry": (
        "模型路由注册表，非可插拔组件 (同 ComponentRegistry 模式)"
    ),
    "lca.layer0_infra.llm.catalog.ModelDefinition": ("模型元数据值对象，纯数据结构"),
    "lca.layer0_infra.llm.config.LLMFace": ("LLM 调用面枚举，纯数据声明"),
    "lca.layer0_infra.llm.config.ResolvedEndpoint": ("解析后的 provider 端点值对象，纯数据"),
    "lca.layer0_infra.llm.config.LLMProviderSettings": (
        "pydantic-settings provider 身份配置，非可插拔组件"
    ),
    "lca.layer0_infra.llm.openai_client.LLMUnavailableError": ("异常类型，非可插拔组件"),
    "lca.layer0_infra.openai_compat.StructuredLLMError": ("异常类型，非可插拔组件"),
    "lca.layer0_infra.computer.machine.MachineComputer": (
        "LobeHub LocalSystemExecutionRuntime 的 LCA 实现，注入 MachineTransport (Computer Use)"
    ),
    "lca.layer0_infra.plane.resolve.PlaneBindingError": ("异常类型，非可插拔组件"),
    "lca.layer0_infra.plane.resolve.PlaneRequest": ("绑定请求值对象，纯数据，非可插拔组件"),
    "lca.layer0_infra.sandbox.host_settings.HostRuntimeSettings": (
        "sidecar pydantic-settings 配置，非可插拔组件"
    ),
    "lca.layer0_infra.dsh.settings.DshSettings": ("DSH driver pydantic-settings，非可插拔组件"),
    "lca.layer0_infra.dsh.models.DshNotification": ("DSH JSON-RPC 通知值对象，纯数据"),
    "lca.layer0_infra.dsh.models.DshTurnResult": ("DSH 一轮结果值对象，纯数据"),
    "lca.layer0_infra.dsh.mapping.ToolProjection": ("DSH 工具投影值对象，纯数据"),
    "lca.layer0_infra.dsh.driver.DshTurnSpec": ("DSH 一轮输入值对象，纯数据"),
    "lca.layer0_infra.dsh.driver.DshTurnDriver": (
        "DSH 一轮编排器，协议缝在 DshRuntime (DSH compare driver)"
    ),
    "lca.layer0_infra.dsh.projector.DshJournalProjector": (
        "DSH session → Journal 投影器，内部策略表 (DSH compare driver)"
    ),
    "lca.layer0_infra.dsh.archive.JsonlEventArchive": (
        "DSH 原始通知归档，文件后端 (DSH compare driver)"
    ),
    "lca.layer0_infra.dsh.sink.HandleJournalSink": (
        "Journal store.append() 适配器，非跨层组件 (DSH compare driver)"
    ),
    "lca.layer0_infra.dsh.runtime.DshUnavailableError": ("异常类型，非可插拔组件"),
    # ── 附件身份平面（LobeHub files_info 对齐，run-scoped inbox）──
    "lca.layer0_infra.attachment.settings.AttachmentPolicyDocument": (
        "policy.yaml 值对象，配置数据，非可插拔组件"
    ),
    "lca.layer0_infra.attachment.settings.AttachmentSettings": (
        "pydantic-settings 配置模型，非可插拔组件"
    ),
    "lca.layer0_infra.attachment.layout.AttachmentLayout": (
        "路径派生工具，纯函数聚合，非可插拔组件"
    ),
    "lca.layer0_infra.attachment.files_info.FilesInfoFile": ("files_info XML 节点值对象，纯数据"),
    "lca.layer0_infra.attachment.files_info.FilesInfoDocument": ("files_info 文档值对象，纯数据"),
    "lca.layer0_infra.attachment.service.FileStoreAttachmentIdentity": (
        "AttachmentIdentity Protocol 的 FileStore 实现 (LobeHub files_info 对齐)"
    ),
    # ── Plugin Tree Runtime (2026-08-16) ───────────────────────
    "lca.layer0_infra.plugin.kernel._context.PluginContext": (
        "插件运行上下文：mount/effect/child 基础设施，不是可插拔组件 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._host.PluginHost": (
        "插件数据容器：服务表 + 事件总线 + handle 注册表 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._handle.PluginHandle": (
        "插件运行时状态 (Fiber)：值对象 + 效果累积 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._service.Service": (
        "Service 基类：构造即注册模式 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._service_record.ServiceRecord": (
        "服务归属记录：值对象 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._spec.PluginSpec": (
        "插件描述符：值对象 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._effect_meta.EffectMeta": (
        "诊断树节点：值对象 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._disposable.DisposableList": (
        "O(1) 可销毁集合：基础设施 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._events.EventBus": (
        "5-mode 事件总线：基础设施 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.loader._entry.BootedTree": (
        "Loader 加载后的产物：值对象 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.loader._entry.PluginEntry": (
        "profile YAML 行数据类：值对象 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.loader._loader.Loader": (
        "插件拓扑加载器：组合根基础设施 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.loader._loader.LoaderError": (
        "加载异常：错误信号 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.include._profile.ProfileError": (
        "profile 组合异常：错误信号 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.include._profile.ProfileLoader": (
        "Profile 加载器：组合根基础设施 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._events._ListenerRecord": (
        "事件监听器记录：内部数据类 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._types.DependencyUnavailable": (
        "依赖不可用异常：错误信号 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._types.PluginError": (
        "插件运行时异常：错误信号 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.kernel._types.PluginState": (
        "插件状态枚举：值类型 (Plugin Tree)"
    ),
    "lca.layer0_infra.plugin.loader._loader.SeamCompletenessError": (
        "Seam 完整性校验异常：Loader 内部控制流 (Harness Spine)"
    ),
    "lca.layer0_infra.plugin.scope.index._ScopeTargetCarrier": (
        "scope 事件载体：内部路由值 (DSH core/scope mirror)"
    ),
    "lca.layer0_infra.plugin.scope.index._ScopedCtx": (
        "scope 子上下文包装：内部辅助 (DSH core/scope mirror)"
    ),
    "lca.layer0_infra.plugin.scope.store._EntryValues": (
        "条目表抽象基类：模块内部组合 (DSH core/scope store)"
    ),
    "lca.layer0_infra.plugin.scope.store.ScopeLayer": (
        "scope 层基类：模块内部契约 (DSH core/scope store)"
    ),
    "lca.layer0_infra.plugin.scope.store.NamedEntries": (
        "具名条目表：通用容器 (DSH core/scope store)"
    ),
    "lca.layer0_infra.plugin.scope.store.AnonymousEntries": (
        "匿名条目表：通用容器 (DSH core/scope store)"
    ),
    "lca.layer0_infra.plugin.scope.store.ScopedLayers": (
        "全局+scope 分层注册表：内核基础设施 (DSH core/scope store)"
    ),
    "lca.layer0_infra.plugin.expr.pyexpr.PyExpr": (
        "!py 表达式值载体：可序列化配置 (Cordis !!js mirror)"
    ),
    "lca.layer0_infra.plugin.expr.pyexpr.SafeEvaluator": (
        "AST 白名单沙箱求值器：内部工具 (Cordis !!js mirror)"
    ),
    "lca.layer0_infra.plugin.builtins.timer.TimerService": (
        "fiber 归属定时器服务：内核插件 (Cordis timer mirror)"
    ),
    "lca.layer0_infra.plugin.builtins.timer._Ticks": (
        "interval 异步迭代器：内部辅助 (Cordis timer mirror)"
    ),
    "lca.layer0_infra.capability.dispatch.ProviderDispatch": (
        "provider 注册表：可逆 effect 挂载 (DSH registry seam)"
    ),
    "lca.layer0_infra.capability.tools.ToolFactory": (
        "工具工厂基类：fork_for_run 绑定 run (DSH core/tools)"
    ),
    "lca.layer2_runtime.runtime_loop._PhaseCtx": (
        "loop 阶段上下文：内部状态值 (Execution Planes)"
    ),
    "lca.layer0_infra.attachment.normalizer.TextNormalizationRules": (
        "附件规范化规则值对象 (Attachment Pipeline)"
    ),
    "lca.layer0_infra.attachment.normalizer.TextNormalizationService": (
        "附件文本规范化服务实现 (Attachment Pipeline)"
    ),
    "lca.layer0_infra.capability.files.FileStoreService": (
        "file_store seam Definition (Capability Seams)"
    ),
    "lca.layer0_infra.capability.hub.CapabilityHub": (
        "capability 组合容器 (Capability Seams)"
    ),
    "lca.layer0_infra.capability.memory.MemoryService": (
        "memory seam Definition (Capability Seams)"
    ),
    "lca.layer0_infra.capability.observability.ObservabilityService": (
        "observability seam Definition (Capability Seams)"
    ),
    "lca.layer0_infra.capability.search.SearchService": (
        "search seam Definition (Capability Seams)"
    ),
    "lca.layer0_infra.capability.skills.SkillsService": (
        "skills seam Definition (Capability Seams)"
    ),
    "lca.layer0_infra.capability.state_store.StateStoreService": (
        "state_store seam Definition (Capability Seams)"
    ),
    "lca.layer0_infra.computer.machine_exec.MachineExecMixin": (
        "machine 执行器混入：模块内部组合 (Computer Use)"
    ),
    "lca.layer0_infra.host_runtime.config.CLIConfig": (
        "CLI 配置模型 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.config.GatewayConfig": (
        "Gateway 配置模型 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.config.HostRuntimeConfig": (
        "宿主运行时配置模型 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.config.PathConfig": (
        "路径配置模型 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.config.SystemPackagesConfig": (
        "系统包配置模型 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.config.ToolsConfig": (
        "工具配置模型 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.config.UserConfig": (
        "用户配置模型 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.config.VenvConfig": (
        "虚拟环境配置模型 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.environment.HostEnvironment": (
        "宿主环境探测实现 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.CheckResult": (
        "检查结果值对象 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.ItemStatus": (
        "条目状态枚举 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.Provider": (
        "provider 抽象基类 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.StatusReport": (
        "状态报告值对象 (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.shared.PackagesProvider": (
        "系统包检查 provider (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.shared.PathProvider": (
        "路径检查 provider (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.shared.ToolsProvider": (
        "工具检查 provider (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.shared.VenvProvider": (
        "venv 检查 provider (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.user.CLIProvider": (
        "CLI 检查 provider (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.user.UserProvider": (
        "用户检查 provider (Host Runtime)"
    ),
    "lca.layer0_infra.host_runtime.providers.user.WorkspaceProvider": (
        "workspace 检查 provider (Host Runtime)"
    ),
    "lca.layer0_infra.ops.config.DaemonConfig": (
        "daemon 配置模型 (Ops)"
    ),
    "lca.layer0_infra.ops.config.DshConfig": (
        "DSH 配置模型 (Ops)"
    ),
    "lca.layer0_infra.ops.config.GatewayConfig": (
        "Gateway 配置模型 (Ops)"
    ),
    "lca.layer0_infra.ops.config.InfraConfig": (
        "基础设施配置模型 (Ops)"
    ),
    "lca.layer0_infra.ops.config.LobeHubConfig": (
        "LobeHub 配置模型 (Ops)"
    ),
    "lca.layer0_infra.ops.config.OnlyboxesConfig": (
        "Onlyboxes 配置模型 (Ops)"
    ),
    "lca.layer0_infra.ops.config.OpsConfig": (
        "Ops 聚合配置模型 (Ops)"
    ),
    "lca.layer0_infra.ops.console.Console": (
        "终端控制台实现 (Ops)"
    ),
    "lca.layer0_infra.ops.console.ConsoleConfig": (
        "控制台配置模型 (Ops)"
    ),
    "lca.layer0_infra.ops.pipeline.Pipeline": (
        "服务管道编排 (Ops)"
    ),
    "lca.layer0_infra.ops.pipeline.PipelineContext": (
        "管道上下文 (Ops)"
    ),
    "lca.layer0_infra.ops.registry.ServiceRegistry": (
        "服务注册表 (Ops)"
    ),
    "lca.layer0_infra.ops.service.HealthCheck": (
        "健康检查值对象 (Ops)"
    ),
    "lca.layer0_infra.ops.service.ServiceState": (
        "服务状态值对象 (Ops)"
    ),
    "lca.layer0_infra.ops.service.ServiceStatus": (
        "服务状态枚举 (Ops)"
    ),
    "lca.layer0_infra.ops.services.daemon.DaemonService": (
        "daemon 服务管理实现 (Ops)"
    ),
    "lca.layer0_infra.ops.services.dsh.DshObservation": (
        "DSH 观测值对象 (Ops)"
    ),
    "lca.layer0_infra.ops.services.dsh.DshService": (
        "DSH 服务管理实现 (Ops)"
    ),
    "lca.layer0_infra.ops.services.dsh.SystemDshProbe": (
        "系统 DSH 探测 (Ops)"
    ),
    "lca.layer0_infra.ops.services.gateway.GatewayService": (
        "Gateway 服务管理实现 (Ops)"
    ),
    "lca.layer0_infra.ops.services.infra.InfraService": (
        "基础设施服务管理实现 (Ops)"
    ),
    "lca.layer0_infra.ops.services.lobehub.LobeHubService": (
        "LobeHub 服务管理实现 (Ops)"
    ),
    "lca.layer0_infra.ops.services.onlyboxes.OnlyboxesObservation": (
        "Onlyboxes 观测值对象 (Ops)"
    ),
    "lca.layer0_infra.ops.services.onlyboxes.OnlyboxesService": (
        "Onlyboxes 服务管理实现 (Ops)"
    ),
    "lca.layer0_infra.ops.services.onlyboxes.SystemOnlyboxesProbe": (
        "系统 Onlyboxes 探测 (Ops)"
    ),
    "lca.layer0_infra.ops.state.ChangeReport": (
        "变更报告值对象 (Ops)"
    ),
    "lca.layer0_infra.ops.state.StateStore": (
        "Ops 状态存储 (Ops)"
    ),
    "lca.layer0_infra.ops.sudo.Sudo": (
        "sudo 包装实现 (Ops)"
    ),
}

_SCAN_PACKAGES = [
    "lca.layer0_infra",
    "lca.layer1_cognitive",
    "lca.layer2_runtime",
    "lca.layer3_agent",
]


def _collect_protocol_classes() -> set[type]:
    """收集 lca.contracts.protocols 中所有 Protocol 类。

    利用 typing 模块对 Protocol 子类设置的 _is_protocol 标记，
    只匹配直接继承 Protocol 的接口定义，不会误匹配实现了 Protocol 的具体类。
    """
    import lca.contracts.mechanisms as mechanisms_mod
    import lca.contracts.models.core.stop as stop_mod
    import lca.contracts.models.team.member_status as member_status_mod
    import lca.contracts.protocols as protocols_mod
    import lca.contracts.protocols.action as action_mod

    result: set[type] = set()
    for mod in (
        protocols_mod,
        action_mod,
        mechanisms_mod,
        member_status_mod,
        stop_mod,
    ):
        for _name, obj in inspect.getmembers(mod, inspect.isclass):
            if getattr(obj, "_is_protocol", False) and obj.__module__.startswith("lca.contracts"):
                result.add(obj)
    return result


def _collect_concrete_classes() -> dict[str, type]:
    """扫描 L0-L3 所有模块，收集其中定义的公开具体类。

    通过 cls.__module__ 过滤，确保只收录"定义在"目标包中的类，
    排除从 contracts 或其他包 import 进来的类。
    """
    result: dict[str, type] = {}
    for pkg_name in _SCAN_PACKAGES:
        pkg = importlib.import_module(pkg_name)
        for _importer, modname, _ispkg in pkgutil.walk_packages(
            pkg.__path__,
            prefix=pkg.__name__ + ".",
        ):
            try:
                mod = importlib.import_module(modname)
            except ImportError:
                continue
            for _cls_name, cls in inspect.getmembers(mod, inspect.isclass):
                if not cls.__module__.startswith(pkg_name):
                    continue
                qualname = f"{cls.__module__}.{cls.__qualname__}"
                result[qualname] = cls
    return result


class TestArchitectureConformance(unittest.TestCase):
    """L0-L3 每个具体类必须显式声明 Protocol 基类，否则必须出现在 EXEMPT 中。"""

    def test_protocol_count_regression(self) -> None:
        """回归防护：Protocol 数量不得低于当前基线（32 个），防止重构意外删除协议。"""
        protocol_bases = _collect_protocol_classes()
        self.assertGreaterEqual(
            len(protocol_bases),
            31,
            "Protocol 数量低于基线 31 —— 是否有协议被意外删除？"
            " 如果确实需要减少协议数量，请同步更新此断言并附 ADR。"
            "（PromptManager 已溶解进 Reasoner，基线 32→31）",
        )

    def test_every_l0_to_l3_class_declares_a_protocol(self) -> None:
        protocol_bases = _collect_protocol_classes()
        self.assertGreater(
            len(protocol_bases),
            0,
            "contracts.protocols 中未找到任何 Protocol 类——扫描逻辑可能有误",
        )

        concrete_classes = _collect_concrete_classes()
        self.assertGreater(
            len(concrete_classes),
            0,
            "L0-L3 未扫描到任何具体类——包路径或扫描逻辑可能有误",
        )

        offenders: list[str] = []
        for qualname, cls in sorted(concrete_classes.items()):
            if qualname in EXEMPT:
                continue
            if getattr(cls, "_is_protocol", False):
                continue
            if set(cls.__mro__) & protocol_bases:
                continue
            offenders.append(qualname)

        self.assertFalse(
            offenders,
            "以下类未声明任何 Protocol 且未在 EXEMPT 中注明理由：\n"
            + "\n".join(f"  - {q}" for q in offenders),
        )

    def test_exempt_entries_are_accurate(self) -> None:
        """EXEMPT 中的每个条目必须指向真实存在的类，防止白名单腐烂。"""
        concrete_classes = _collect_concrete_classes()
        stale = [qualname for qualname in EXEMPT if qualname not in concrete_classes]
        self.assertFalse(
            stale,
            "EXEMPT 中包含不存在的类（已删除或重命名），请清理：\n"
            + "\n".join(f"  - {q}" for q in stale),
        )


class TestCognitiveLoopSkeleton(unittest.TestCase):
    """ADR-0002 保障：Loop 本体必须保持精简（<30 条 AST 语句），禁止回渗业务逻辑。"""

    _LOOP_FILE = (
        Path(__file__).resolve().parent.parent / "lca" / "layer2_runtime" / "runtime_loop.py"
    )
    _MAX_LOOP_STATEMENTS = 30

    def test_loop_body_statement_count(self) -> None:
        """_loop 方法的 AST 语句数不得超过阈值，防止业务判定逻辑重新泄漏进 Loop。"""
        source = self._LOOP_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)

        loop_func = None
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "_loop":
                loop_func = node
                break

        self.assertIsNotNone(loop_func, "未找到 _loop 方法——CognitiveRuntime 结构可能已变更")
        # mypy 无法将 assertIsNotNone 识别为类型收窄
        stmt_count = len(loop_func.body)  # type: ignore[arg-type]
        self.assertLessEqual(
            stmt_count,
            self._MAX_LOOP_STATEMENTS,
            f"_loop 方法体包含 {stmt_count} 条 AST 语句，"
            f"超过 ADR-0002 上限 {self._MAX_LOOP_STATEMENTS}。"
            "请将业务判定逻辑提取到 StopOutcomePolicy / Hook / Body 装饰器中。",
        )

    def test_runtime_loop_import_whitelist(self) -> None:
        """runtime_loop.py 只允许 import contracts 协议类型，禁止 import 具体策略实现。

        防止事件总线实现等具体概念重新泄漏进 Loop。
        """
        source = self._LOOP_FILE.read_text(encoding="utf-8")
        tree = ast.parse(source)

        forbidden_modules = {
            "lca.layer1_cognitive.event_bus",
            "lca.contracts.protocols.action",
        }
        violations: list[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in forbidden_modules:
                        violations.append(f"import {alias.name} (line {node.lineno})")
            elif (
                isinstance(node, ast.ImportFrom)
                and node.module is not None
                and node.module in forbidden_modules
            ):
                names = ", ".join(a.name for a in node.names)
                violations.append(f"from {node.module} import {names} (line {node.lineno})")

        self.assertFalse(
            violations,
            "runtime_loop.py 包含禁止的 import——Loop 不应直接依赖具体策略实现：\n"
            + "\n".join(f"  - {v}" for v in violations),
        )


if __name__ == "__main__":
    unittest.main()
