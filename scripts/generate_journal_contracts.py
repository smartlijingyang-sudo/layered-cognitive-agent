#!/usr/bin/env python3
"""从 journal_catalog + journal.py 生成 web/src/contracts/journal.generated.ts。"""

from __future__ import annotations

import dataclasses
import enum
import sys
import typing
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from lca.contracts.models.observability.journal import (  # noqa: E402
    ActionDegraded,
    AgentRunFinished,
    AgentRunStarted,
    DecisionMade,
    DelegationCacheHit,
    DelegationCompleted,
    DelegationIssued,
    DelegationMechanism,
    JournalEvent,
    LlmCallCompleted,
    RunInsight,
    StepCompleted,
    StepTextDelta,
    SynthesisCompleted,
    TeamRunFinished,
    TeamRunStarted,
    ToolDenied,
    ToolInvoked,
)
from lca.contracts.models.observability.journal_catalog import (  # noqa: E402
    JOURNAL_CATALOG,
    JOURNAL_EVENT_CLASSES,
)

_OUT = _ROOT / "web" / "src" / "contracts" / "journal.generated.ts"

_PY_TO_TS: dict[type, str] = {
    str: "string",
    int: "number",
    float: "number",
    bool: "boolean",
}


def _ts_type(field_type: object) -> str:
    if isinstance(field_type, type) and field_type in _PY_TO_TS:
        return _PY_TO_TS[field_type]
    origin = typing.get_origin(field_type)
    if origin is tuple:
        return "readonly string[]"
    if isinstance(field_type, type) and issubclass(field_type, JournalEvent):
        return "never"
    if isinstance(field_type, type) and issubclass(field_type, enum.Enum):
        members = list(field_type.__members__.values())
        return " | ".join(f'"{m.value}"' for m in members)
    return "unknown"


def _event_interface(name: str, cls: type) -> str:
    hints = typing.get_type_hints(cls)
    lines = [f"export interface {name} {{", f'  readonly type: "{name}";']
    for f in dataclasses.fields(cls):
        if f.name == "type":
            continue
        ts = _ts_type(hints.get(f.name, f.type))
        lines.append(f"  readonly {f.name}: {ts};")
    lines.append("}")
    return "\n".join(lines)


def _domain_map() -> str:
    entries = []
    for name, vocab in sorted(JOURNAL_CATALOG.items()):
        entries.append(f'  {name}: "{vocab.domain.value}",')
    return (
        "export const EVENT_DOMAINS: Record<JournalEventType, VocabDomain> = {\n"
        + "\n".join(entries)
        + "\n};"
    )


def generate() -> str:
    event_classes = [
        TeamRunStarted,
        TeamRunFinished,
        AgentRunStarted,
        AgentRunFinished,
        DelegationIssued,
        DelegationCompleted,
        DelegationCacheHit,
        SynthesisCompleted,
        DecisionMade,
        StepCompleted,
        ActionDegraded,
        LlmCallCompleted,
        StepTextDelta,
        ToolInvoked,
        ToolDenied,
        RunInsight,
    ]
    names = [cls.__name__ for cls in event_classes]
    assert set(names) == set(JOURNAL_EVENT_CLASSES), "generator 与 catalog 不同步"

    parts = [
        "/** AUTO-GENERATED — scripts/generate_journal_contracts.py */",
        "",
        'export type VocabDomain = "run" | "team" | "cognitive" | "resource" | "event";',
        "",
        "export interface RunScope {",
        "  readonly trace_id: string;",
        "  readonly run_id: string;",
        "  readonly parent_run_id: string | null;",
        "  readonly delegation_id: string | null;",
        "  readonly agent_role: string;",
        "}",
        "",
        "export interface StampedRecord<E = JournalEvent> {",
        '  readonly schema: "journal.v1";',
        "  readonly seq: number;",
        "  readonly ts: number;",
        "  readonly scope: RunScope;",
        "  readonly event_type: JournalEventType;",
        "  readonly event: E;",
        "  readonly domain?: VocabDomain;",
        "}",
        "",
    ]
    for cls in event_classes:
        parts.append(_event_interface(cls.__name__, cls))
        parts.append("")

    union = " | ".join(f"{n}" for n in names)
    parts.append(f"export type JournalEvent = {union};")
    parts.append('export type JournalEventType = JournalEvent["type"];')
    parts.append(f"export const JOURNAL_EVENT_TYPES = {names!r} as const;")
    parts.append("")
    parts.append(_domain_map())
    parts.append("")
    parts.append(f"export type DelegationMechanism = {_ts_type(DelegationMechanism)};")
    return "\n".join(parts) + "\n"


def main() -> None:
    content = generate()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(content, encoding="utf-8")
    print(f"Wrote {_OUT}")


if __name__ == "__main__":
    main()
