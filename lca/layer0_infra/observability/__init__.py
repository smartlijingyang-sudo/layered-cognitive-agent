"""LCA 可观测性子系统 —— 唯一公共面（白名单守卫）。

架构三层：
    ① 认知语义层（contracts 词表 + 本包 facade）—— 我们拥有
    ② 遥测骨干（OpenTelemetry）—— 业界标准，被 facade 封装，业务层不可见
    ③ 后端（console/jsonl/memory/langfuse）—— 注册表装配，配置化

外部使用（唯一入口）::

    from lca.layer0_infra.observability import create_observability, bind, span, event

    hub = create_observability("console+langfuse")   # 或 Agent(observability=...)
    with bind(hub):
        with span(SpanName.RUN_AGENT):
            ...

包外禁止 import 任何子模块（守卫测试强制）；本 ``__init__`` 是唯一表面。
"""

from lca.layer0_infra.observability.exporters.langfuse import ExporterUnavailableError
from lca.layer0_infra.observability.facade import (
    SpanContext,
    annotate,
    bind,
    event,
    get_span_context,
    score,
    set_actor,
    set_session,
    span,
    traced,
)
from lca.layer0_infra.observability.hub import ObservabilityHub
from lca.layer0_infra.observability.narrative import plan_steps_joined
from lca.layer0_infra.observability.policy import AttributePolicy, Verbosity
from lca.layer0_infra.observability.registry import (
    UnknownExporterError,
    create_observability,
)
from lca.layer0_infra.observability.settings import ObservabilitySettings
from lca.layer0_infra.observability.team_profile import (
    TeamTraceProfile,
    objective_preview,
    plan_card_attrs,
    team_id_for,
    team_run_attrs,
)
from lca.layer0_infra.observability.view import SpanView

__all__ = [
    "AttributePolicy",
    "ExporterUnavailableError",
    "ObservabilityHub",
    "ObservabilitySettings",
    "SpanContext",
    "SpanView",
    "TeamTraceProfile",
    "UnknownExporterError",
    "Verbosity",
    "annotate",
    "bind",
    "create_observability",
    "event",
    "get_span_context",
    "objective_preview",
    "plan_card_attrs",
    "plan_steps_joined",
    "score",
    "set_actor",
    "set_session",
    "span",
    "team_id_for",
    "team_run_attrs",
    "traced",
]
