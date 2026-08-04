"""L0 Observability package.

Public application API (only these for business layers)
-------------------------------------------------------
- ``bind(observability)``  — install ambient Telemetry at run entry
- ``span(name, **attrs)``  — emit a correlated span (contracts: SpanName)
- backends: Console / JSONL / Multiplex / Null

Internal
--------
Correlation + Telemetry runtime live in ``runtime.py``.
"""

from lca.layer0_infra.observability.console_observability import ConsoleObservability
from lca.layer0_infra.observability.jsonl_file_observability import JSONLFileObservability
from lca.layer0_infra.observability.multiplex import MultiplexObservability
from lca.layer0_infra.observability.null_observability import NullObservability
from lca.layer0_infra.observability.plan_narrative import (
    format_run_plan_card,
    plan_steps_joined,
    strategy_plan_steps,
)
from lca.layer0_infra.observability.redaction import safe_repr, sanitize, truncate
from lca.layer0_infra.observability.run_narrative import (
    format_section_header,
    format_span_line,
    format_step_banner,
    is_milestone_span,
    logical_depth,
    section_key_for_span,
)
from lca.layer0_infra.observability.runtime import (
    SpanContext,
    bind,
    current,
    get_span_context,
    set_actor,
    span,
)
from lca.layer0_infra.observability.span_attributes import extract_span_attributes
from lca.layer0_infra.observability.team_trace import (
    TeamTraceProfile,
    objective_preview,
    plan_card_attrs,
    team_id_for,
    team_run_attrs,
)

__all__ = [
    "ConsoleObservability",
    "JSONLFileObservability",
    "MultiplexObservability",
    "NullObservability",
    "SpanContext",
    "TeamTraceProfile",
    "bind",
    "current",
    "extract_span_attributes",
    "format_run_plan_card",
    "format_section_header",
    "format_span_line",
    "format_step_banner",
    "get_span_context",
    "is_milestone_span",
    "logical_depth",
    "objective_preview",
    "plan_card_attrs",
    "plan_steps_joined",
    "safe_repr",
    "sanitize",
    "section_key_for_span",
    "set_actor",
    "span",
    "strategy_plan_steps",
    "team_id_for",
    "team_run_attrs",
    "truncate",
]
