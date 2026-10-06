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
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict, cast

_DEFAULT_TRACES_ROOT = Path("traces")

# Mirror DEBUG_RUN_META_FAMILIES from contracts/observability/event/meta_event_taxonomy
# so we do not import from contracts into CLI surface code.
#
# This is the module's SINGLE domain-prefix table: the old _EP_PREFIX_FAMILIES
# split (observation/diagnosis/graph with pure-startswith semantics) is folded
# in here -- "graph" is defined exactly once.
#
# Single match semantic: substring (`p in execution_point`), NOT pure
# startswith. Chosen because:
# 1. It reproduces contracts' debug_run_family_for_key exactly
#    (any(raw_key.startswith(p) or p in raw_key ...), which collapses to
#    `p in raw_key`). The mirror rule's whole point is that CLI classification
#    agrees with contracts classification; a different semantic here would
#    make the mirror lie.
# 2. It is load-bearing, not sloppy: production execution_points are
#    "spine."-prefixed ("spine.body.tool.execute.start",
#    "spine.cognition.prompt_assembler.assemble.end",
#    "spine.phase_graph.node.start"). Pure startswith would silently drop all
#    of them from their domains -- filter_by_domain("graph") would count zero
#    on a real run while load_spine_facts(("graph",)) disagreed with it.
_DOMAIN_PREFIXES: dict[str, tuple[str, ...]] = {
    "session": ("turn.", "step.started", "step.ended", "message.accepted", "session.created"),
    "llm": ("llm.", "model.", "thinking.", "step.thinking"),
    "prompt": (
        "prompt_assembler",
        "prompt.section",
        "prompt.surface",
        "reasoner.reason",
        "skill_router",
        "think.gate",
        "gate.decided",
        "convergence.evaluated",
        "delivery.evidence",
    ),
    "tool": ("body.tool.", "phase.tool.", "step.tool_", "tool.schema"),
    "sandbox": ("body.sandbox.",),
    "skill": ("skill.", "assistant.skill.", "skill.package"),
    "assistant": ("assistant.",),
    "composio": ("composio.",),
    "graph": ("phase_graph.",),
    "phase": ("phase.",),
    "kernel": ("kernel.", "agent_loop.", "lifecycle.", "runtime.", "transport."),
    "observation": ("observation.",),
    "diagnosis": ("diagnosis.",),
}


def _matches_domain(execution_point: str, prefixes: tuple[str, ...]) -> bool:
    """The module's single domain-match semantic: substring match.

    `ep.startswith(p)` implies `p in ep`, so the old
    `ep.startswith(p) or p in ep` disjunction collapses to `p in ep`.
    """
    return any(p in execution_point for p in prefixes)


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
        # SpineRow is a total=False tolerant view; obj is an
        # isinstance-checked dict, so the cast only names the
        # documented tolerance (no runtime change).
        out.append(cast("SpineRow", obj))
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
        e
        for e in events
        if _matches_domain(str(e.get("execution_point", "")), prefixes)
    ]


def load_spine_facts(
    run_id: str,
    families: Sequence[str] = ("observation", "diagnosis"),
    *,
    traces_root: Path | None = None,
) -> list[SpineRow]:
    """Read the spine ledger and keep rows in the named domain-prefix families.

    Fail-soft like load_spine_events (missing file / bad JSON -> []).
    Unknown family names raise ValueError; known families are the keys of
    the module's single domain-prefix table. Match semantic is the module's
    `_matches_domain` (substring), shared with `filter_by_domain` so both
    functions never disagree on the same run.
    This function is the delete-when target of the SHARED_LOADER_EXEMPT
    entries in scripts/lca-cli-shape.py.
    """
    try:
        prefixes = tuple(p for f in families for p in _DOMAIN_PREFIXES[f])
    except KeyError as exc:
        raise ValueError(
        f"unknown spine fact family {exc.args[0]!r}; "
        f"known: {sorted(_DOMAIN_PREFIXES)}"
        ) from exc
    return [
        e
        for e in load_spine_events(run_id, traces_root)
        if _matches_domain(str(e.get("execution_point") or ""), prefixes)
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

    Folded out of `debug_graph._summarize_outputs` (2026-10-06, local copy
    deleted): nested dict gets a key preview, list gets a length,
    primitives get repr-capped. The original str cap (80) is preserved by
    passing cap=80 at the debug_graph call site.
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
        # A str's repr never starts with "datetime.datetime(" (it starts with a
        # quote), so reaching here means v is a datetime-like object.
        if isinstance(v, datetime):
            try:
                return v.isoformat()
            except Exception:
                return f"<{type(v).__name__}>"
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
