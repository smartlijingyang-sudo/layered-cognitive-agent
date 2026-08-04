"""实时 span 行叙事 —— 分节键与单行渲染（无状态、属性驱动）。

场景卡（run.plan 横幅）在 ``plan_narrative.py``；共享折行/取属性工具在
``narrative_utils.py``。分节完全由 span 自身属性推导（ADR-0032），
并发成员交错完成时不会把行挂到错误的角色节下。
"""

from __future__ import annotations

from lca.contracts.observability import TraceSpan
from lca.contracts.telemetry import (
    ATTR_ACTION_TYPE,
    ATTR_AGENT_ROLE,
    ATTR_CALLEE_ROLE,
    ATTR_EVENT,
    ATTR_MODEL,
    ATTR_PROMPT_CHARS,
    ATTR_PROMPT_PREVIEW,
    ATTR_RESPONSE_CHARS,
    ATTR_RESPONSE_PREVIEW,
    ATTR_STATUS,
    ATTR_STEP,
    ATTR_STRATEGY_KEY,
    ATTR_SUBTASK_PREVIEW,
    ATTR_TOOL_NAME,
    SpanName,
)
from lca.layer0_infra.observability.narrative_utils import attr_text, wrap_words

_NAME_WIDTH = 22


def _dur_ms(span: TraceSpan) -> int:
    if span.ended_at is None:
        return 0
    return int((span.ended_at - span.started_at).total_seconds() * 1000)


def section_key_for_span(span: TraceSpan) -> str:
    """Group live lines by actor — derived purely from span attributes (ADR-0032).

    Stateless: never falls back to "previous section", so concurrent members
    interleave without misattribution. Every span now carries ``agent_role``
    (ambient autofill at emission); explicit attributes always win.
    """
    attrs = span.attributes or {}
    name = span.name
    if name in (
        SpanName.RUN_TEAM.value,
        SpanName.TEAM_STRATEGY.value,
        SpanName.TEAM_ROUND.value,
        SpanName.TEAM_SYNTHESIS.value,
    ):
        return "team"
    role = attr_text(attrs, ATTR_AGENT_ROLE)
    if role:
        step = attrs.get(ATTR_STEP)
        if step is not None:
            return f"{role} · step {step}"
        return role
    callee = attr_text(attrs, ATTR_CALLEE_ROLE)
    if callee:
        return callee
    return "team"


def format_section_header(key: str) -> str:
    return f"\n── {key} ──"


def _short_name(span: TraceSpan) -> str:
    name = span.name
    attrs = span.attributes or {}
    if name.startswith("loop.phase."):
        phase = name.removeprefix("loop.phase.")
        event = attr_text(attrs, ATTR_EVENT)
        if event.startswith("pre_"):
            return f"{phase}.pre"
        if event.startswith("post_"):
            return f"{phase}.post"
        return phase
    if name.startswith("hook."):
        return name  # hook.on_start / hook.on_complete
    if name == SpanName.TRANSPORT_REQUEST.value:
        return "transport→"
    if name == SpanName.TRANSPORT_RESPONSE.value:
        return "transport←"
    if name == SpanName.DELEGATE_CACHE_HIT.value:
        return "delegate.cache"
    if name == SpanName.TEAM_MEMBER_INVOKE.value:
        return "member_invoke"
    if name == SpanName.LLM_CHAT.value:
        return "llm.chat"
    if name == SpanName.RUN_AGENT.value:
        return "run.agent"
    if name == SpanName.RUN_TEAM.value:
        return "run.team"
    if name == SpanName.TEAM_STRATEGY.value:
        return "team.strategy"
    return name


def format_span_line(span: TraceSpan, *, depth: int = 0) -> str:
    """Aligned span line; llm.chat expands prompt/response block below."""
    attrs = span.attributes or {}
    pad = "  " * max(depth, 0)
    name = _short_name(span)
    col = f"{name:<{_NAME_WIDTH}}"

    bits: list[str] = []

    action = attr_text(attrs, ATTR_ACTION_TYPE)
    if action:
        bits.append(f"→ {action}")
    callee = attr_text(attrs, ATTR_CALLEE_ROLE)
    if (callee and "transport" in name) or (
        callee and span.name == SpanName.TEAM_MEMBER_INVOKE.value
    ):
        bits.append(callee)
    if callee and span.name == SpanName.DELEGATE_CACHE_HIT.value:
        bits.append(callee)
        subtask = attr_text(attrs, ATTR_SUBTASK_PREVIEW)
        if subtask:
            bits.append(f"subtask={subtask}")

    tool = attr_text(attrs, ATTR_TOOL_NAME)
    if tool:
        bits.append(f"tool={tool}")

    model = attr_text(attrs, ATTR_MODEL)
    if model:
        bits.append(f"model={model}")

    step = attrs.get(ATTR_STEP)
    if step is not None and (
        span.name in (SpanName.RUN_AGENT.value, SpanName.LLM_CHAT.value)
        or span.name.startswith("loop.phase.")
    ):
        bits.append(f"step={step}")

    if span.name == SpanName.LLM_CHAT.value:
        pc, rc = attrs.get(ATTR_PROMPT_CHARS), attrs.get(ATTR_RESPONSE_CHARS)
        if pc is not None:
            bits.append(f"in={pc}c")
        if rc is not None:
            bits.append(f"out={rc}c")

    dur = _dur_ms(span)
    if dur > 0 or span.name in (SpanName.LLM_CHAT.value, SpanName.TOOL_EXECUTE.value):
        bits.append(f"{dur}ms")

    st = attr_text(attrs, ATTR_STATUS) or attr_text(attrs, "status")
    span_st = getattr(span.status, "value", span.status)
    if span_st not in ("ok", "OK", None, ""):
        bits.append(str(span_st))
    if st:
        bits.append(f"status={st}")
    if attrs.get("ok") is False:
        bits.append("FAIL")

    sk = attr_text(attrs, ATTR_STRATEGY_KEY)
    if sk and span.name in (
        SpanName.RUN_TEAM.value,
        SpanName.TEAM_STRATEGY.value,
    ):
        bits.append(f"strategy={sk}")

    rnd = attrs.get("round")
    if rnd is not None:
        bits.append(f"round={rnd}")

    detail = "  ".join(bits)
    head = f"{pad}· {col}  {detail}" if detail else f"{pad}· {col}".rstrip()

    if span.name != SpanName.LLM_CHAT.value:
        return head
    body = _format_llm_io_block(attrs, base_pad=pad)
    return head if not body else f"{head}\n{body}"


def _format_llm_io_block(attrs: dict[str, object], *, base_pad: str) -> str:
    prompt = attr_text(attrs, ATTR_PROMPT_PREVIEW)
    response = attr_text(attrs, ATTR_RESPONSE_PREVIEW)
    if not prompt and not response:
        return ""
    ipad = base_pad + "  "
    lines: list[str] = []
    if prompt:
        lines.append(f"{ipad}┌ prompt")
        for row in _wrap_keep_newlines(prompt, width=72):
            lines.append(f"{ipad}│ {row}")
    if response:
        lines.append(f"{ipad}├ response" if prompt else f"{ipad}┌ response")
        for row in _wrap_keep_newlines(response, width=72):
            lines.append(f"{ipad}│ {row}")
    lines.append(f"{ipad}└")
    return "\n".join(lines)


def _wrap_keep_newlines(text: str, *, width: int) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        if not para.strip():
            out.append("")
            continue
        out.extend(wrap_words(para, width))
    return out if out else [""]


def logical_depth(span: TraceSpan) -> int:
    """Indent under a role section: phases/hooks flat, llm nested one level."""
    name = span.name
    if name in (
        SpanName.RUN_TEAM.value,
        SpanName.TEAM_STRATEGY.value,
        SpanName.RUN_AGENT.value,
    ):
        return 0
    if name in (SpanName.LLM_CHAT.value, SpanName.TOOL_EXECUTE.value):
        return 1
    # phases, hooks, transport — same level under section header
    return 0


def is_milestone_span(span: TraceSpan) -> bool:
    """Used by test digests when filtering trees."""
    name = span.name
    if name == SpanName.RUN_PLAN.value:
        return True
    if name in (
        SpanName.RUN_TEAM.value,
        SpanName.RUN_AGENT.value,
        SpanName.TEAM_STRATEGY.value,
        SpanName.TEAM_MEMBER_INVOKE.value,
        SpanName.TRANSPORT_REQUEST.value,
        SpanName.DELEGATE_CACHE_HIT.value,
        SpanName.LLM_CHAT.value,
        SpanName.TOOL_EXECUTE.value,
        SpanName.TEAM_ROUND.value,
        SpanName.TEAM_SYNTHESIS.value,
        SpanName.ERROR.value,
    ):
        return True
    return (
        name.startswith("loop.phase.") and (span.attributes or {}).get(ATTR_ACTION_TYPE) is not None
    )


# Back-compat alias (no longer dual-printed by console)
def format_step_banner(span: TraceSpan) -> str | None:
    if not is_milestone_span(span) or span.name == SpanName.RUN_PLAN.value:
        return None
    return format_span_line(span, depth=0)
