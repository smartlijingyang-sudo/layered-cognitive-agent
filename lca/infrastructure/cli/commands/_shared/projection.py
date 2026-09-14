"""Shared spine projection utilities for CLI commands.

CLI surface depends on this module for spine parsing + per-domain filtering +
output summarization. The data shape (`SpineRow`) is intentionally tolerant:
real spine rows frequently carry extra fields and omit fields the strict
EventRecord dataclass requires (e.g. `span_id`, `sequence`, `when`). This
projection layer exposes the row as a dict so the CLI surface keeps working
through ongoing spine schema evolution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypedDict

_DEFAULT_TRACES_ROOT = Path("traces")

# Mirror DEBUG_RUN_META_FAMILIES from contracts/observability/event/meta_event_taxonomy
# so we do not import from contracts into CLI surface code.
_DOMAIN_PREFIXES: dict[str, tuple[str, ...]] = {
    "session": ("turn.", "step.started", "step.ended", "message.accepted", "session.created"),
    "llm": ("llm.", "model.", "thinking.", "step.thinking"),
    "prompt": (
        "prompt_assembler", "prompt.section", "prompt.surface",
        "reasoner.reason", "skill_router", "think.gate",
        "gate.decided", "convergence.evaluated", "delivery.evidence",
    ),
    "tool": ("body.tool.", "phase.tool.", "step.tool_", "tool.schema"),
    "sandbox": ("body.sandbox.",),
    "skill": ("skill.", "assistant.skill.", "skill.package"),
    "assistant": ("assistant.",),
    "composio": ("composio.",),
    "graph": ("phase_graph.",),
    "phase": ("phase.",),
    "kernel": ("kernel.", "agent_loop.", "lifecycle.", "runtime.", "transport."),
}


class SpineRow(TypedDict, total=False):
    """Tolerant view of one spine row. `payload` is the dict the producer wrote."""

    execution_point: str
    payload: dict[str, Any]


def spine_filename_for_run_cwd(run_id: str) -> Path:
    """Resolve `<cwd>/traces/runs/<run_id>/<run_id>.spine.jsonl`.

    The filename comes from the SSOT helper so the CLI never spells the
    `.spine.jsonl` literal directly.
    """
    from lca.infrastructure.observability.spine.sinks.naming import (
        spine_filename_for_run,
    )

    return _DEFAULT_TRACES_ROOT / "runs" / run_id / spine_filename_for_run(run_id)


def load_spine_events(
    run_id: str,
    traces_root: Path | None = None,
) -> list[SpineRow]:
    """Read the spine ledger for `run_id` into SpineRow dicts.

    CLI fail-soft: missing file / invalid JSON returns an empty list. Each
    parsed row is returned as the raw JSON dict so the projection layer
    tolerates schema drift in the EventRecord dataclass.
    """
    root = traces_root if traces_root is not None else _DEFAULT_TRACES_ROOT
    from lca.infrastructure.observability.spine.sinks.naming import (
        spine_filename_for_run,
    )

    spine_path = root / "runs" / run_id / spine_filename_for_run(run_id)
    if not spine_path.exists():
        return []
    out: list[SpineRow] = []
    for line in spine_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        out.append(obj)
    return out


def filter_by_domain(
    events: list[SpineRow],
    domain: str,
) -> list[SpineRow]:
    """Keep only events whose execution_point belongs to the given meta family."""
    prefixes = _DOMAIN_PREFIXES.get(domain)
    if prefixes is None:
        return []
    return [
        e for e in events
        if any(
            str(e.get("execution_point", "")).startswith(p)
            or p in str(e.get("execution_point", ""))
            for p in prefixes
        )
    ]


def truncate(text: str, n: int = 120) -> str:
    """Single-line, length-capped string for human rendering."""
    flat = text.replace("\n", " ").strip()
    return flat if len(flat) <= n else flat[: n - 3] + "..."


def summarize_outputs(
    outputs: dict[str, Any],
    *,
    cap: int = 120,
) -> list[str]:
    """One human-readable line per output key.

    Mirrors `debug_graph._summarize_outputs` semantics: nested dict gets a
    key preview, list gets a length, primitives get repr-capped.
    """
    if not isinstance(outputs, dict):
        return []
    lines: list[str] = []
    for k, v in outputs.items():
        if isinstance(v, dict):
            sub_keys = list(v.keys())[:4]
            sample: list[str] = []
            for sk in sub_keys:
                sv = v.get(sk)
                if isinstance(sv, (str, int, float, bool)):
                    sample.append(f"{sk}={_safe_repr(sv, 40)}")
                elif isinstance(sv, list):
                    sample.append(f"{sk}=list[{len(sv)}]")
                elif isinstance(sv, dict):
                    sample.append(f"{sk}=dict[{len(sv)}]")
                else:
                    sample.append(f"{sk}={_safe_repr(sv, 30)}")
            lines.append(f"    out.{k} {{ {', '.join(sample)} }}")
        elif isinstance(v, list):
            lines.append(f"    out.{k} = list[{len(v)}]")
        elif isinstance(v, str):
            lines.append(f"    out.{k} = {_safe_repr(v, cap)}")
        else:
            lines.append(f"    out.{k} = {_safe_repr(v, 60)}")
    return lines


def _safe_repr(v: Any, n: int = 60) -> str:
    """repr that suppresses `<...object at 0x...>` addresses and datetime repr."""
    is_string_dt = isinstance(v, str) and v.startswith("datetime.datetime(")
    r = repr(v)
    if "object at 0x" in r:
        return f"<{type(v).__name__}>"
    if is_string_dt or r.startswith("datetime.datetime("):
        if is_string_dt:
            inner = v[len("datetime.datetime(") : -1]
            return truncate(inner, n)
        try:
            return v.isoformat()
        except Exception:
            return f"<{type(v).__name__}>"
    return truncate(r, n)


__all__ = [
    "SpineRow",
    "filter_by_domain",
    "load_spine_events",
    "spine_filename_for_run_cwd",
    "summarize_outputs",
    "truncate",
]
