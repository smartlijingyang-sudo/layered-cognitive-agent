"""Human-readable diagnostics for team-mode tests (inline in AssertionError).

Not a separate reporting product — failure messages must show enough
trace topology to locate which node/step broke.

CLI also uses :func:`format_human_digest` (story + milestone tree).
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from lca.contracts.observability import TraceSpan
from lca.contracts.result import Result
from lca.contracts.telemetry import SpanName
from lca.layer0_infra.observability.run_narrative import is_milestone_span
from tests.harness.collector import TraceBundle


def _status_str(value: Any) -> str:
    return str(getattr(value, "value", value))


def _dur_ms(span: TraceSpan) -> int:
    if span.ended_at is None:
        return 0
    return int((span.ended_at - span.started_at).total_seconds() * 1000)


def format_case_digest(
    bundle: TraceBundle,
    *,
    title: str = "CASE",
    result: Result | None = None,
) -> str:
    """Compact header + span histogram + full chain tree for assert failures."""
    lines: list[str] = [
        f"=== {title} ===",
        f"spans={len(bundle.spans)} trace_ids={sorted(bundle.shared_trace_ids())}",
    ]
    if result is not None:
        lines.append(
            f"result.status={result.status!r} total_steps={result.total_steps} "
            f"output_preview={(result.output or '')[:120]!r}"
        )
    counts = Counter(bundle.names())
    if counts:
        hist = ", ".join(f"{n}×{c}" for n, c in sorted(counts.items()))
        lines.append(f"span_hist: {hist}")
    roles = sorted(
        {
            str(s.attributes.get("agent_role"))
            for s in bundle.by_name(SpanName.RUN_AGENT.value)
            if s.attributes.get("agent_role")
        }
    )
    if roles:
        lines.append(f"agent_roles: {roles}")
    callees = sorted(
        {
            str(s.attributes.get("callee_role"))
            for s in bundle.by_name(SpanName.TRANSPORT_REQUEST.value)
            if s.attributes.get("callee_role")
        }
    )
    if callees:
        lines.append(f"transport_callees: {callees}")
    # Path probes for quick health read
    probes = [
        (SpanName.RUN_TEAM.value, SpanName.TEAM_STRATEGY.value),
        (SpanName.RUN_TEAM.value, SpanName.TRANSPORT_REQUEST.value),
        (SpanName.RUN_TEAM.value, SpanName.LLM_CHAT.value),
        (SpanName.RUN_TEAM.value, SpanName.LOOP_PHASE_THINK.value),
        (SpanName.RUN_AGENT.value, SpanName.LLM_CHAT.value),
    ]
    path_bits = []
    for root, leaf in probes:
        if bundle.by_name(root):
            ok = bundle.has_path_to(root, leaf)
            path_bits.append(f"{root}→{leaf}={'OK' if ok else 'MISS'}")
    if path_bits:
        lines.append("paths: " + " | ".join(path_bits))
    lines.append(format_trace_tree(bundle, title="TRACE"))
    return "\n".join(lines)


def format_human_digest(
    bundle: TraceBundle,
    *,
    title: str = "CASE",
    result: Result | None = None,
    full_tree: bool = False,
) -> str:
    """Story-first digest for CLI: what happened, cost, path health, tree."""
    lines: list[str] = [f"=== {title} ==="]

    llm_spans = bundle.by_name(SpanName.LLM_CHAT.value)
    tool_spans = bundle.by_name(SpanName.TOOL_EXECUTE.value)
    agent_spans = bundle.by_name(SpanName.RUN_AGENT.value)
    roles = sorted(
        {str(s.attributes.get("agent_role")) for s in agent_spans if s.attributes.get("agent_role")}
    )
    llm_ms = sum(_dur_ms(s) for s in llm_spans)
    wall_ms = max((_dur_ms(s) for s in bundle.root_spans()), default=0)
    strategies = sorted(
        {
            str(s.attributes.get("strategy_key"))
            for s in bundle.by_name(SpanName.TEAM_STRATEGY.value)
            if s.attributes.get("strategy_key")
        }
    )
    actions = [
        str(getattr(s.attributes.get("action_type"), "value", s.attributes.get("action_type")))
        for s in bundle.spans
        if s.attributes.get("action_type") is not None
        and s.name == SpanName.LOOP_PHASE_THINK.value
        and str(s.attributes.get("event") or "").startswith("post")
    ]
    # fallback: any think with action
    if not actions:
        actions = [
            str(getattr(s.attributes.get("action_type"), "value", s.attributes.get("action_type")))
            for s in bundle.spans
            if s.name == SpanName.LOOP_PHASE_THINK.value and s.attributes.get("action_type")
        ]

    story_bits = [
        f"agents={roles or ['—']}",
        f"steps={result.total_steps if result else '?'}",
        f"llm_calls={len(llm_spans)} ({llm_ms}ms)",
    ]
    if tool_spans:
        story_bits.append(f"tools={len(tool_spans)}")
    if strategies:
        story_bits.append(f"strategy={','.join(strategies)}")
    if wall_ms:
        story_bits.append(f"wall≈{wall_ms}ms")
    lines.append("story: " + " · ".join(story_bits))

    if actions:
        # de-dupe preserve order
        seen: set[str] = set()
        ordered: list[str] = []
        for a in actions:
            if a not in seen:
                seen.add(a)
                ordered.append(a)
        lines.append("decisions: " + " → ".join(ordered))

    if result is not None:
        st = _status_str(result.status)
        lines.append(f"result: status={st} · steps={result.total_steps}")
        out = (result.output or "").strip()
        if out:
            preview = out if len(out) <= 240 else out[:240] + "…"
            lines.append(f"output: {preview}")

    # path health (only probes that apply)
    probes: list[tuple[str, str]] = []
    if bundle.by_name(SpanName.RUN_TEAM.value):
        probes.extend(
            [
                (SpanName.RUN_TEAM.value, SpanName.TEAM_STRATEGY.value),
                (SpanName.RUN_TEAM.value, SpanName.LLM_CHAT.value),
            ]
        )
    if bundle.by_name(SpanName.RUN_AGENT.value):
        probes.append((SpanName.RUN_AGENT.value, SpanName.LLM_CHAT.value))
    if probes:
        path_bits = []
        for root, leaf in probes:
            mark = "✓" if bundle.has_path_to(root, leaf) else "✗"
            path_bits.append(f"{root}→{leaf} {mark}")
        lines.append("paths: " + " | ".join(path_bits))

    if llm_spans:
        slow = sorted(llm_spans, key=_dur_ms, reverse=True)[:3]
        for s in slow:
            model = s.attributes.get("model") or "?"
            lines.append(f"llm: {_dur_ms(s)}ms · model={model}")

    tree_title = "TRACE" if full_tree else "TRACE (milestones)"
    lines.append(format_trace_tree(bundle, title=tree_title, milestones_only=not full_tree))
    lines.append(f"(raw spans: {len(bundle.spans)}; use --full-trace for every span)")
    return "\n".join(lines)


def format_trace_tree(
    bundle: TraceBundle,
    *,
    title: str = "TRACE",
    milestones_only: bool = False,
) -> str:
    selected = (
        [s for s in bundle.spans if is_milestone_span(s)] if milestones_only else list(bundle.spans)
    )
    lines = [f"--- {title} ({len(selected)} shown / {len(bundle.spans)} total) ---"]
    if not selected:
        lines.append("(no spans)")
        return "\n".join(lines)

    if milestones_only:
        # Tree order (parent before children); non-milestones are skipped but
        # still connect descendants for indentation.
        def walk_milestones(span: TraceSpan, depth: int) -> list[str]:
            out: list[str] = []
            show = is_milestone_span(span)
            child_depth = depth + 1 if show else depth
            if show:
                out.append(_format_span(span, depth))
            for child in bundle.children(span):
                out.extend(walk_milestones(child, child_depth))
            return out

        roots = bundle.root_spans() or list(bundle.spans)
        emitted: set[str] = set()
        for root in roots:
            for line in walk_milestones(root, 0):
                lines.append(line)
            for node in bundle.walk(root):
                emitted.add(node.span_id)
        for s in selected:
            if s.span_id not in emitted:
                lines.append(_format_span(s, 0, orphan=True))
        return "\n".join(lines)

    roots = bundle.root_spans()
    if not roots:
        for s in bundle.spans:
            lines.append(_format_span(s, 0, orphan=True))
        return "\n".join(lines)

    seen: set[str] = set()
    for root in roots:
        lines.extend(_render_subtree(bundle, root, 0, seen))
    for s in bundle.spans:
        if s.span_id not in seen:
            lines.append(_format_span(s, 0, orphan=True))
    return "\n".join(lines)


def _render_subtree(bundle: TraceBundle, span: TraceSpan, depth: int, seen: set[str]) -> list[str]:
    if span.span_id in seen:
        return []
    seen.add(span.span_id)
    out = [_format_span(span, depth)]
    for child in bundle.children(span):
        out.extend(_render_subtree(bundle, child, depth + 1, seen))
    return out


def _format_span(span: TraceSpan, depth: int, *, orphan: bool = False) -> str:
    """Tree line aligned with ConsoleObservability naming."""
    from lca.layer0_infra.observability.run_narrative import format_span_line

    line = format_span_line(span, depth=depth)
    if orphan:
        return line.replace("·", "?", 1)
    return line
