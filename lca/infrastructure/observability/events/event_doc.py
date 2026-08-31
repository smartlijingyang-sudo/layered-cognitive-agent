"""事件类型的中文说明词表 —— 装饰器风格,可插拔注册。

每个事件类型对应一个 ``EventDoc``:中文一句话摘要、为何存在、它在认知
闭环 / 五层架构中的位置、关联 ADR。``JsonlJournalProjector`` 落盘前
会调用 ``doc_for(event_type)`` 把 ``_doc`` 段注入 disk JSON,新手打开
journal.jsonl 就能读懂每个 block 的来龙去脉。

权威性:本模块是"教新手读 journal"的副本,事实语义仍由 journal.py
frozen dataclass + event_descriptors_data.EventDescriptor 拥有。一旦两边
不一致以 journal.py 为准。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class EventDoc:
    """一条事件类型的中文说明。"""

    summary: str  # 一句话:这条事件是什么
    why: str  # 为何要记:它解决什么可观测问题
    arch: str  # 在五层架构 / 认知闭环 / ADR 中的位置
    layer: str  # 触发射点所在的层 (L0..L4)


_REGISTRY: dict[str, EventDoc] = {}


def register_doc(event_type: str, doc: EventDoc) -> EventDoc:
    """把一条 ``EventDoc`` 绑到 ``event_type``;重复登记抛 ``ValueError``。

    支持装饰器与函数式两种风格,模块可在自己 import 时一次性挂入,无需
    中心 import-order 耦合。
    """
    normalized = event_type.split(".")[-1]
    if normalized in _REGISTRY:
        raise ValueError(f"EventDoc for {normalized!r} already registered")
    _REGISTRY[normalized] = doc
    return doc


def doc_decorator(event_type: str) -> Callable[[Callable[[], EventDoc]], Callable[[], EventDoc]]:
    """装饰器: ``@doc_decorator('Foo')`` 装饰的工厂函数在 import 时注册。"""

    def wrap(factory: Callable[[], EventDoc]) -> Callable[[], EventDoc]:
        register_doc(event_type, factory())
        return factory

    return wrap


def doc_for(event_type: str) -> EventDoc | None:
    """Return Chinese doc for ``event_type`` or ``None`` if unregistered."""
    if not event_type:
        return None
    return _REGISTRY.get(event_type.split(".")[-1])


def registered_event_types() -> Mapping[str, EventDoc]:
    """只读快照,供 glossary 侧车文件 / 健全性检查使用。"""
    return dict(_REGISTRY)


# ── 内置词表 ──────────────────────────────────────────────
# 每条 ``@doc_decorator('EventName')`` 都与 ``event_descriptors_data.py``
# 中的同事件 ``_descriptor(...)`` 一一对应;``layer`` 字段从 emitter 路径
# 推导(``lca.layerN_xxx.*`` → ``Lx``,``kernel_serve.*`` → ``L4``,
# ``lca.harness.*`` / ``lca.plugins.*`` → ``L4``)。手工复核见 ADR-0065 §六
# (认知原语宪法) + ADR-0002(认知闭环相位) + ADR-0041(LLM 流式增量)。


@doc_decorator("InboxFollowupCreated")
def _doc_inbox() -> EventDoc:
    return EventDoc(
        summary="用户 prompt 经 Inbox 通道写入,作为 run 的事实起点",
        why="把外部输入与 run 边界对齐;同一 inbox 可被多个 run 消费(ADR-0073)",
        arch="L4 harness session;ADR-0073 session-turn-task-controller",
        layer="L4",
    )


@doc_decorator("CastingStarted")
def _doc_casting_started() -> EventDoc:
    return EventDoc(
        summary="自动组队选角开始 —— Team 编译前的一次 LLM 调用",
        why="把用户 objective 映射到角色库,产出 CastingPlan 快照",
        arch="L4 default_modes 选角插件入口;ADR-0042/0052 动态选角",
        layer="L4",
    )


@doc_decorator("CastingCompleted")
def _doc_casting_completed() -> EventDoc:
    return EventDoc(
        summary="选角完成,记录 governance_kind + lead_role + selected_roles + rationale",
        why="驱动后续 TeamRunStarted.members;白名单校验后的可回放快照",
        arch="L4 default_modes;rationale 用于事后审计选角理由",
        layer="L4",
    )


@doc_decorator("CastingFailed")
def _doc_casting_failed() -> EventDoc:
    return EventDoc(
        summary="选角失败 —— 解析 / 白名单 / 重试耗尽任一原因",
        why="run 无法展开,run_doctor 标记 H1 断裂(0065 §六)",
        arch="L4 default_modes 降级路径",
        layer="L4",
    )


@doc_decorator("TeamRunStarted")
def _doc_team_started() -> EventDoc:
    return EventDoc(
        summary="团队 run 容器开启 —— 场景卡同时记录 members / mandate / plan_steps",
        why="为后续委派 / 综合 / 决策建立 run-scoped 关联骨架",
        arch="L3 team_handle 编排入口;ADR-0030/0034 团队域语言 + 闭环策略",
        layer="L3",
    )


@doc_decorator("TeamRunFinished")
def _doc_team_finished() -> EventDoc:
    return EventDoc(
        summary="团队 run 容器关闭 —— output_text 是 lead 综合后的最终回答",
        why="给 doctor / manifest 拿终态;为消费方记录团队级成败",
        arch="L3 team_handle 收口;manifest.json.terminal_event 来源",
        layer="L3",
    )


@doc_decorator("TaskCreated")
def _doc_task_created() -> EventDoc:
    return EventDoc(
        summary="session spine 上的 durable task 事实",
        why="把团队 plan_steps 落实成可追踪 / 可恢复的最小任务单元",
        arch="L4 harness command (kernel serve);ADR-0092 durable session command ledger",
        layer="L4",
    )


@doc_decorator("AgentRunStarted")
def _doc_agent_started() -> EventDoc:
    return EventDoc(
        summary="agent run 容器开启 —— 一段 perceive→think→act→reflect 闭环的入口",
        why="为后续 LLM / 工具 / 决策事件提供 scope 上下文,actor_step 计数起点",
        arch="L3 cognitive_agent;CognitiveRuntime 入口,ADR-0002 闭环相位起点",
        layer="L3",
    )


@doc_decorator("AgentRunFinished")
def _doc_agent_finished() -> EventDoc:
    return EventDoc(
        summary="agent run 收口 —— output_text 是 chat-projector 的最终答案源",
        why="给上层 team 综合、SSE 输出、UI 渲染最终答案;失败原因进 error",
        arch="L3 cognitive_agent;ADR-0045 canonical intent shape",
        layer="L3",
    )


@doc_decorator("DelegationIssued")
def _doc_delegation_issued() -> EventDoc:
    return EventDoc(
        summary="lead 把任务委派给成员 —— 一等公民,mechanism 区分 delegate/handoff/member_invoke",
        why="记录跨 agent 的工作交接;mandate 是 lead 给成员的目标",
        arch="L0 transport.invocation;ADR-0030 Team 一等公民 + 0034 策略",
        layer="L0",
    )


@doc_decorator("DelegationCompleted")
def _doc_delegation_completed() -> EventDoc:
    return EventDoc(
        summary="成员完成委派,把 output 回传给 lead",
        why="为 lead 综合 / 黑板更新提供材料;与 DelegationIssued 配对形成因果环",
        arch="L0 transport.invocation;task_id 关联 agent run",
        layer="L0",
    )


@doc_decorator("DelegationCacheHit")
def _doc_delegation_cache() -> EventDoc:
    return EventDoc(
        summary="委派命中幂等缓存 —— 同一 mandate 之前跑过,直接复用结果",
        why="省钱省时;审计 '这是复用,不是真跑' 的标记",
        arch="L1 body.delegation_cache;ADR-0049 咨询资源",
        layer="L1",
    )


@doc_decorator("SynthesisCompleted")
def _doc_synthesis() -> EventDoc:
    return EventDoc(
        summary="lead 综合多个成员输出,产出最终结论(收口)",
        why="board mandate 下 '汇报总结' 是产品卖点;output_text 是用户答案",
        arch="L1 body.action_handlers;TeamRunFinished 之前的最后一步",
        layer="L1",
    )


@doc_decorator("DecisionMade")
def _doc_decision() -> EventDoc:
    return EventDoc(
        summary="一次 think() 的决策产物 —— action_type + confidence + response_text",
        why="把 LLM 输出解析成结构化意图;response_text 是 chat-projector 终态归约权威源",
        arch="L1 body.action_handlers;ADR-0045 canonical intent shape + ADR-0002 think 相位",
        layer="L1",
    )


@doc_decorator("StepCompleted")
def _doc_step_completed() -> EventDoc:
    return EventDoc(
        summary="一个 perceive→think→act→reflect step 收口",
        why="actor_step 计数 + reflect 产物持久化",
        arch="L2 event_emission;ADR-0002 闭环相位收口",
        layer="L2",
    )


@doc_decorator("ActionDegraded")
def _doc_action_degraded() -> EventDoc:
    return EventDoc(
        summary="原决策动作被降级(权限 / 资源 / 审批拦截),实际执行了别的动作",
        why="保留 '为什么没按原本意图跑' 的审计痕迹",
        arch="L2 event_emission;ADR-0078 审批状态机 + DecisionGate",
        layer="L2",
    )


@doc_decorator("LlmCallStarted")
def _doc_llm_started() -> EventDoc:
    return EventDoc(
        summary="一次 LLM 调用开始 —— Body/SafeExecutor 进入世界平面",
        why="为 LlmCallCompleted 与 stream delta 提供锚点;SSE 推流心跳",
        arch="L0 observability.adapters;ADR-0038 流式事件契约 + 0041 reasoner stream",
        layer="L0",
    )


@doc_decorator("LlmCallCompleted")
def _doc_llm_completed() -> EventDoc:
    return EventDoc(
        summary="LLM 调用结束 —— model / latency / token / prompt_preview 视 verbosity 落盘",
        why="性能 + 成本核算 + 审计;CostProjector 据此算 cost",
        arch="L0 observability.adapters;OTel generation span 语义约定",
        layer="L0",
    )


@doc_decorator("StepTextDelta")
def _doc_step_text_delta() -> EventDoc:
    return EventDoc(
        summary="LLM 流式输出 token / 中文片段;channel 区分 decision(原始) vs answer(可向用户展示)",
        why="前端实时渲染 token;落盘由 JsonlJournalProjector 合并",
        arch="L0 observability.adapters;ADR-0041 chat-projector answer 归约",
        layer="L0",
    )


@doc_decorator("ReasoningDelta")
def _doc_reasoning_delta() -> EventDoc:
    return EventDoc(
        summary="模型思维链 / reasoning 段流的 token",
        why="前端 Thinking 面板实时显示 '模型在想什么';与 StepTextDelta 分离",
        arch="L0 observability.adapters;ADR-0041;restricted / confidential —— 不进 SSE / OTel / Langfuse",
        layer="L0",
    )


@doc_decorator("ReasoningCompleted")
def _doc_reasoning_completed() -> EventDoc:
    return EventDoc(
        summary="一次 LLM 调用的 reasoning 段结束 —— duration_ms + content_preview",
        why="前端显示 '已深度思考 Xs' 徽标",
        arch="L0 observability.adapters;面向用户的可观测信号;restricted / confidential 摘要",
        layer="L0",
    )


@doc_decorator("RunActivity")
def _doc_run_activity() -> EventDoc:
    return EventDoc(
        summary="Run 级活动心跳 —— LLM 等待 / 工具运行中的进度信号",
        why="前端面板显示 spinner,不靠抖动的 SSE token",
        arch="L0 observability;LlmStreamActivityTracker,ADR-0051 Phase 2",
        layer="L0",
    )


@doc_decorator("SandboxOutputDelta")
def _doc_sandbox_delta() -> EventDoc:
    return EventDoc(
        summary="沙箱执行的原始增量输出(stdout/stderr 各成流)",
        why="前端实时显示工具运行日志;落盘由 projector 合并",
        arch="L0 sandbox;lca/infrastructure/sandbox/streaming.py",
        layer="L0",
    )


@doc_decorator("ToolCallStreaming")
def _doc_tool_streaming() -> EventDoc:
    return EventDoc(
        summary="LLM 正在流式生成工具调用参数 —— 在响应完成前发出",
        why="前端尽早渲染工具卡片占位,消除 '思考完→工具卡' 的空白期",
        arch="L1 brain.llm_turn.executor;ADR-0099 runs-live-openai-stream",
        layer="L1",
    )


@doc_decorator("ToolStarted")
def _doc_tool_started() -> EventDoc:
    return EventDoc(
        summary="Body/SafeExecutor 发起一次工具调用 —— 参数受治理记录,evidence 留底",
        why="code / command / language / skill_id 走 typed field,不再用 plugin_state 逃逸",
        arch="L1 body.tool_journal_emit;ADR-0065 §四 + 0047 wire anticorruption",
        layer="L1",
    )


@doc_decorator("ToolInvoked")
def _doc_tool_invoked() -> EventDoc:
    return EventDoc(
        summary="工具调用收口 —— ok / latency / output_text / files / state_ref",
        why="审计 + 失败原因;run_doctor 看 tool_success / consecutive_fail",
        arch="L1 body.tool_journal_emit;state_ref 指向 EvidenceStore 大对象",
        layer="L1",
    )


@doc_decorator("ToolDenied")
def _doc_tool_denied() -> EventDoc:
    return EventDoc(
        summary="工具调用被权限 / 安全 / 沙箱策略拒绝",
        why="保留 '为什么没跑' 的因果;agent 可换工具或降级",
        arch="L1 body.tool_journal_emit;权限门 + ADR-0049 资源平面",
        layer="L1",
    )


@doc_decorator("AttachmentStagingStarted")
def _doc_attach_started() -> EventDoc:
    return EventDoc(
        summary="附件暂存开始 —— 把上传文件复制到受治理的工作区",
        why="文件不进 prompt 直送,先 sanitized 后被工具引用",
        arch="L4 lca.plugins.transport.webserver.handlers.runs.execute;ADR-0051 run workspace plane",
        layer="L4",
    )


@doc_decorator("AttachmentStagingCompleted")
def _doc_attach_completed() -> EventDoc:
    return EventDoc(
        summary="附件暂存成功,可被工具读取",
        why="审计 + 为下游工具给路径;路径受 sandbox 策略约束",
        arch="L4 lca.plugins.transport.webserver.handlers.runs.execute",
        layer="L4",
    )


@doc_decorator("AttachmentStagingFailed")
def _doc_attach_failed() -> EventDoc:
    return EventDoc(
        summary="附件暂存失败(权限 / 路径 / 病毒扫描)",
        why="通常意味着 H2 断裂,jsonl 为空",
        arch="L4 lca.plugins.transport.webserver.handlers.runs.execute 错误路径",
        layer="L4",
    )


@doc_decorator("RuntimeObserved")
def _doc_runtime_observed() -> EventDoc:
    return EventDoc(
        summary="插件 / hook / 阶段 / 错误诊断的解释记录(不改变领域状态)",
        why="事实流 + 解释流共享同一账本;Coding Agent 工具据此排查",
        arch="L0..L4 任一层;EventAudience=operator / auditor;ADR-0063 run-scoped diagnostics",
        layer="L0..L4",
    )


@doc_decorator("ContextManifested")
def _doc_context_manifested() -> EventDoc:
    return EventDoc(
        summary="PerceiveHub 一次性发出当 step 的 ContextManifest(item_refs + digest)",
        why="Reasoner 永远不读 prompt_preview,manifest 是唯一真相源;digest 用于 replay 校验",
        arch="L1 brain.context_manifest;ADR-0002 perceive 相位产物",
        layer="L1",
    )


@doc_decorator("PerceptionMerged")
def _doc_perception_merged() -> EventDoc:
    return EventDoc(
        summary="Hub fold 终态 —— 本 step 接收相位的最终结果",
        why="为 think() 准备好统一 view;保留 delta_ref 与 item_kinds",
        arch="L1 perceive_hub;ADR-0002 perceive 相位收口",
        layer="L1",
    )


@doc_decorator("GateDecided")
def _doc_gate_decided() -> EventDoc:
    return EventDoc(
        summary="DecisionGate 裁决 —— verdict∈{warn,rewrite,deny};allow 默认不记",
        why="把治理与 think/act 解耦;C7 控制/观察分离",
        arch="L1 brain.decision_gates;ADR-0077 终态动作协议 + 0078 审批",
        layer="L1",
    )


@doc_decorator("TeamMessagePublished")
def _doc_team_message() -> EventDoc:
    return EventDoc(
        summary="Team 消息发布 —— 一个 team 一个 topic;thread_id 区分委派子线",
        why="异步协作的横向通信,其他成员可订阅",
        arch="L3 team_handle;lca/cognition/collaboration/blackboard.py",
        layer="L3",
    )


@doc_decorator("ApprovalRequested")
def _doc_approval_requested() -> EventDoc:
    return EventDoc(
        summary="执行信封触发审批 —— envelope_id + tool_name + risk_level",
        why="C7 控制平面;run 暂停等审批(配合 RunPaused)",
        arch="L1 body.safe_executor;ADR-0078 审批状态机",
        layer="L1",
    )


@doc_decorator("ApprovalResolved")
def _doc_approval_resolved() -> EventDoc:
    return EventDoc(
        summary="审批决议 —— approved bool;与 ApprovalRequested / RunPaused 配对",
        why="audit + RunResumed 触发条件",
        arch="L1 body.safe_executor;ADR-0078",
        layer="L1",
    )


@doc_decorator("MemoryCommitted")
def _doc_memory_committed() -> EventDoc:
    return EventDoc(
        summary="记忆提交到持久层(scratchpad / long-term / vector store)",
        why="审计记忆写入;C5 capability grant 衰减在此强制",
        arch="L1 memory.simple_memory;lca/cognition/memory.py",
        layer="L1",
    )


@doc_decorator("ContextCompacted")
def _doc_context_compacted() -> EventDoc:
    return EventDoc(
        summary="影子 CompactionPolicy 应用 —— original_kinds / kept_kinds / compression_ratio",
        why="受控压缩(必须保留一个工具调用 + 结果的因果边界);summary 在 EvidenceStore",
        arch="L1 memory.simple_memory;ADR-0002 perceive 阶段 + 长上下文治理",
        layer="L1",
    )


@doc_decorator("RunPaused")
def _doc_run_paused() -> EventDoc:
    return EventDoc(
        summary="Run 暂停 —— HITL 审批 / 资源耗尽;等待恢复",
        why="审批门或预算暂停的可观测标记;与 RunResumed 配对",
        arch="L2 runtime_loop;ADR-0078 审批状态机 + 0094 stop-policy locality",
        layer="L2",
    )


@doc_decorator("RunResumed")
def _doc_run_resumed() -> EventDoc:
    return EventDoc(
        summary="暂停的 run 重新继续执行",
        why="与 RunPaused 配对;记录 '暂停-恢复' 时间窗便于审计",
        arch="L2 runtime_lifecycle;RunLedger 从 checkpoint 重建状态",
        layer="L2",
    )


@doc_decorator("PluginAuthored")
def _doc_plugin_authored() -> EventDoc:
    return EventDoc(
        summary="agent 把 plugin 源码写到磁盘(Creator Step 5)",
        why="与通用 ToolInvoked 区分,按 actor_role 记录 '我写了一个插件'",
        arch="L4 cordis_control tool;ADR-0074 §13.3.4 创造模式流程",
        layer="L4",
    )


@doc_decorator("PluginMounted")
def _doc_plugin_mounted() -> EventDoc:
    return EventDoc(
        summary="plugin 已通过 Composer.mount 挂入 Context(C3 / C5)",
        why="Resolve-before-Boot 顺序合规证据;capability_grant ⊆ 调用方 grant",
        arch="L4 cordis_control;ADR-0061 plugin-manifest-resolve-boot",
        layer="L4",
    )


@doc_decorator("PluginMountRejected")
def _doc_plugin_rejected() -> EventDoc:
    return EventDoc(
        summary="挂载被拒(C5 / PR12 / §23.2 三道闸任一失败)",
        why="失败事实的唯一来源;reason_code 取自 ComposerErrorCode",
        arch="L4 cordis_control;与 PluginMounted 互斥",
        layer="L4",
    )


@doc_decorator("PluginUnmounted")
def _doc_plugin_unmounted() -> EventDoc:
    return EventDoc(
        summary="plugin 已通过 Composer.unmount 退出 Context",
        why="ADR-0062 资源清理审计;逆拓扑 dispose 顺序",
        arch="L4 cordis_control;plugin 生命周期收口",
        layer="L4",
    )


@doc_decorator("PluginInspected")
def _doc_plugin_inspected() -> EventDoc:
    return EventDoc(
        summary="CordisControlTool(inspect) 已返回当前能力图 snapshot",
        why="lca-ops trace 子命令按 seq 回放 '运行时的能力图长什么样'",
        arch="L4 cordis_control;mounted_count + plugins_summary 是 UI 一等字段",
        layer="L4",
    )


@doc_decorator("PresetPublished")
def _doc_preset_published() -> EventDoc:
    return EventDoc(
        summary="plugin 源码 + bundle YAML 写入 preset 目录(Creator Step 6)",
        why="下一次 boot 加载该 bundle 时 plugin 自动挂入,无需 cordis_control",
        arch="L4 preset_authoring;ADR-0074 §13.3.4",
        layer="L4",
    )


__all__ = [
    "EVENT_DOCS",
    "EventDoc",
    "doc_decorator",
    "doc_for",
    "register_doc",
    "registered_event_types",
]

# Backward-compatible constant for callers that still import ``EVENT_DOCS``.
EVENT_DOCS: Mapping[str, EventDoc] = registered_event_types()
