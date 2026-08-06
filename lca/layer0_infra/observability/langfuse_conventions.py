"""Langfuse OTel 观测约定 —— ``langfuse.*`` 属性键名与类型值的单一事实源。

Langfuse v4 服务端按 ``langfuse.*`` 命名空间属性把 OTel span 映射到其数据模型
（trace/observation 字段、类型、环境等，见
https://langfuse.com/integrations/native/opentelemetry ）。LCA 用到的键名与
观测类型值在此登记，供发射点共享引用——禁止在各模块散落字面量：

- LLM 适配器（``adapters``）→ generation（model/tokens/cost 自动核算）；
- 工具执行（``safe_executor``）→ tool（可按类型过滤、挂评测器）；
- run 边缘（``cognitive_agent`` / ``team_handle``）→ agent 类型与根 I/O、tags。

类型取值说明：OTel 映射文档列 ``span | generation | event`` 三档，SDK 的
``ObservationTypeSpanLike`` 另接受 ``agent / tool / chain / retriever /
evaluator / guardrail``（驱动 Agent Graph 与类型过滤），本框架按最佳实践使用。
"""

from __future__ import annotations

from lca.contracts.telemetry import SpanName

# ── 属性键名（langfuse.* 命名空间）──────────────────────
LANGFUSE_OBSERVATION_TYPE = "langfuse.observation.type"
LANGFUSE_OBSERVATION_MODEL_NAME = "langfuse.observation.model.name"
LANGFUSE_OBSERVATION_INPUT = "langfuse.observation.input"
LANGFUSE_OBSERVATION_OUTPUT = "langfuse.observation.output"
LANGFUSE_OBSERVATION_USAGE_DETAILS = "langfuse.observation.usage_details"
LANGFUSE_OBSERVATION_METADATA_AGENT_ROLE = "langfuse.observation.metadata.agent_role"
LANGFUSE_TRACE_TAGS = "langfuse.trace.tags"
LANGFUSE_ENVIRONMENT = "langfuse.environment"

# ── 观测类型值 ──────────────────────────────────────────
OBSERVATION_TYPE_AGENT = "agent"
OBSERVATION_TYPE_GENERATION = "generation"
OBSERVATION_TYPE_TOOL = "tool"
OBSERVATION_TYPE_EVENT = "event"
"""瞬时事实（决策/综合/洞察...）投影为 EVENT 观测（自托管 v3/v4 实证：
OTel span event 不被导出，须以 ``langfuse.observation.type=event`` 的
零时长 span 承载，方能在 Langfuse 视图可见）。"""

# ── OpenTelemetry GenAI 语义约定键名（业界标准，非 LCA 词表）──
# generation 投影（journal OtelProjector）与 LLM 适配器共享，禁止散落字面量。
GEN_AI_OPERATION = "gen_ai.operation.name"
GEN_AI_OPERATION_CHAT = "chat"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_INPUT = "gen_ai.input"
GEN_AI_OUTPUT = "gen_ai.output"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# ── trace 级标签（业务维度过滤）────────────────────────
FRAMEWORK_TAG = "lca"

# ── Langfuse 视图噪音过滤 ──────────────────────────────
# 框架内部零 I/O、按步高频重复的 span 不进 Langfuse，保证 trace 树
# 可读（console/jsonl/memory 后端不受影响，全量保留）。
# ``LCA_OBS_VERBOSITY=verbose`` 时过滤器停用，全量导出（排障用）。
LANGFUSE_HIDDEN_SPAN_PREFIXES: tuple[str, ...] = ("loop.phase.", "hook.")
"""按前缀隐藏：认知四相相位与生命周期钩子边界 span。"""

LANGFUSE_HIDDEN_SPAN_NAMES: frozenset[str] = frozenset(
    {
        SpanName.MEMORY_READ.value,
        SpanName.MEMORY_WRITE.value,
        SpanName.TRANSPORT_REQUEST.value,
        SpanName.TRANSPORT_RESPONSE.value,
    }
)
"""按名隐藏：零 I/O 的资源边界 span。

注：ADR-0037 后成员父子链由 ``delegation`` span 承载，
transport.request/response 退回纯机制细节（verbose 档可见）。
"""


def langfuse_span_visible(span_name: str) -> bool:
    """span 是否进入 Langfuse 视图（噪音过滤的单一判定点）。"""
    if any(span_name.startswith(prefix) for prefix in LANGFUSE_HIDDEN_SPAN_PREFIXES):
        return False
    return span_name not in LANGFUSE_HIDDEN_SPAN_NAMES
