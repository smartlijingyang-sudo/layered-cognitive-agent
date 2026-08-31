"""span 树诊断渲染 —— 测试失败摘要用的里程碑过滤与单行格式化。

ADR-0037 后人类视图由 journal console 投影承担；本模块只剩 span 平面的
诊断工具（harness/report.py 在断言失败时渲染 span 树定位问题）。
"""

from __future__ import annotations

from lca.contracts.atoms.telemetry import (
    ATTR_ACTION_TYPE,
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
from lca.infrastructure.observability.narrative.narrative_utils import attr_text, wrap_words
from lca.infrastructure.observability.adapters.view import SpanView

_NAME_WIDTH = 22


def _short_name(span: SpanView) -> str:
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
    if name == SpanName.DELEGATION.value:
        return "delegation"
    if name == SpanName.LLM_CHAT.value:
        return "llm.chat"
    if name == SpanName.RUN_AGENT.value:
        return "run.agent"
    if name == SpanName.RUN_TEAM.value:
        return "run.team"
    return name


def format_span_line(span: SpanView, *, depth: int = 0) -> str:
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
    if callee and ("transport" in name or span.name in (SpanName.DELEGATION.value,)):
        bits.append(callee)
        subtask = attr_text(attrs, ATTR_SUBTASK_PREVIEW)
        if subtask and span.name == SpanName.DELEGATION.value:
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

    dur = span.duration_ms
    if dur > 0 or span.name in (
        SpanName.LLM_CHAT.value,
        SpanName.TOOL_EXECUTE.value,
        SpanName.DELEGATION.value,
    ):
        bits.append(f"{dur}ms")

    if span.status not in ("ok", ""):
        bits.append(span.status)
    st = attr_text(attrs, ATTR_STATUS)
    if st:
        bits.append(f"status={st}")
    if attrs.get("ok") is False:
        bits.append("FAIL")

    sk = attr_text(attrs, ATTR_STRATEGY_KEY)
    if sk and span.name == SpanName.RUN_TEAM.value:
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


def is_milestone_span(span: SpanView) -> bool:
    """诊断摘要的里程碑 span（ADR-0037 拓扑：delegation 承载委派链）。"""
    name = span.name
    if name in (
        SpanName.RUN_TEAM.value,
        SpanName.RUN_AGENT.value,
        SpanName.DELEGATION.value,
        SpanName.TRANSPORT_REQUEST.value,
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
