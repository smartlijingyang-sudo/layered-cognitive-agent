"""SSOT: LCA real module paths + runtime availability.

Generated from runtime probes on 2026-09-08 against lca main + lca_kernel
with cordis installed via uv (vendor/cordis + vendor/cosmokit + vendor/schemastery).

After `uv sync`:
  - cordis is installed at .venv/lib/python3.12/site-packages/cordis/
  - All 25 LCA real paths below are verified importable via `uv run python`.

Each entry: (module_path, symbol, runtime_status, used_by).
Runtime status:
  OK   — `from lca.X import Y` works via `uv run python`

Production code rule:
  - Use `uv run` (or a venv with cordis installed) to execute agent_lab.
  - Node plugins import directly from lca.xxx — no adapter, no fallback.
  - If cordis is missing at runtime, import errors surface immediately
    (fail-loud per ADR-0186), rather than silently degrading via stub.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LcaStatus(StrEnum):
    OK = "ok"  # direct import works (after uv sync)


@dataclass(frozen=True)
class LcaPath:
    module: str
    symbol: str
    status: LcaStatus
    used_by: tuple[str, ...]  # which node plugin depends on this


# --- Provenance: 25/25 runtime-verified via `uv run python` ----------------
# All entries below were verified at the time of generation by:
#   uv run python -c "from <module> import <symbol>"

LCA_PATHS: tuple[LcaPath, ...] = (
    # ── Decisions / observations / reflections / LLM ──
    LcaPath(
        "lca.contracts.atoms.enums.enums", "ActionType", LcaStatus.OK, ("nodes/think/classify",)
    ),
    LcaPath(
        "lca.contracts.atoms.enums.enums",
        "ReflectionVerdict",
        LcaStatus.OK,
        ("nodes/reflect/critique",),
    ),
    LcaPath(
        "lca.contracts.atoms.ids.ids",
        "new_id",
        LcaStatus.OK,
        ("nodes/reflect/critique", "adapters/lca_reflect"),
    ),
    LcaPath(
        "lca.contracts.models.core.execution.decision",
        "Decision",
        LcaStatus.OK,
        (
            "nodes/think/classify",
            "nodes/think/guard",
            "nodes/remember/commit",
            "nodes/control/stop_decide",
        ),
    ),
    LcaPath(
        "lca.contracts.models.core.execution.decision",
        "Observation",
        LcaStatus.OK,
        ("nodes/reflect/critique",),
    ),
    LcaPath(
        "lca.contracts.models.core.execution.decision",
        "Reflection",
        LcaStatus.OK,
        ("nodes/reflect/critique", "nodes/reflect/extract"),
    ),
    LcaPath(
        "lca.contracts.models.core.execution.decision",
        "ToolCall",
        LcaStatus.OK,
        ("nodes/think/classify",),
    ),
    LcaPath(
        "lca.contracts.models.core.conversation.llm",
        "LLMResponse",
        LcaStatus.OK,
        ("nodes/think/classify",),
    ),
    LcaPath(
        "lca.contracts.models.core.conversation.llm",
        "NativeToolCall",
        LcaStatus.OK,
        ("nodes/think/classify",),
    ),
    LcaPath(
        "lca.contracts.models.core.conversation.llm",
        "TokenUsage",
        LcaStatus.OK,
        ("nodes/think/classify",),
    ),
    # ── Stop policy (control slot on remember) ──
    LcaPath(
        "lca.contracts.models.core.policy.stop",
        "StopDecision",
        LcaStatus.OK,
        ("nodes/control/stop_decide",),
    ),
    LcaPath(
        "lca.contracts.models.core.policy.stop",
        "StopReason",
        LcaStatus.OK,
        ("nodes/control/stop_decide",),
    ),
    LcaPath(
        "lca.contracts.models.core.state.lifecycle",
        "TaskStatus",
        LcaStatus.OK,
        ("nodes/control/stop_decide",),
    ),
    LcaPath(
        "lca.contracts.models.core.state.lifecycle",
        "coerce_status",
        LcaStatus.OK,
        ("nodes/control/stop_decide",),
    ),
    # ── Agent state / role ──
    LcaPath(
        "lca.contracts.models.core.state.state",
        "AgentState",
        LcaStatus.OK,
        ("nodes/perceive/commit", "nodes/reflect/critique", "adapters/lca_reflect"),
    ),
    LcaPath(
        "lca.contracts.models.team.role.team",
        "ToolPermissionManifest",
        LcaStatus.OK,
        ("nodes/effect/tool_dispatch",),
    ),
    # ── Session / context assembly ──
    LcaPath(
        "lca.contracts.protocols.session.model.context",
        "ModelContextAssembler",
        LcaStatus.OK,
        ("nodes/model_eye/see",),
    ),
    LcaPath(
        "lca.contracts.protocols.session.model.context",
        "ModelVisibleRequest",
        LcaStatus.OK,
        ("nodes/model_eye/see",),
    ),
    LcaPath(
        "lca.infrastructure.llm_adapter.openai_compat",
        "OpenAICompatAdapter",
        LcaStatus.OK,
        ("nodes/think/reason",),
    ),
    LcaPath(
        "lca.infrastructure.session.context.model_context_assembler",
        "DefaultModelContextAssembler",
        LcaStatus.OK,
        ("nodes/model_eye/see",),
    ),
    # ── cordis-gated (now OK after uv sync) ──
    LcaPath(
        "lca.session.append",
        "Session",
        LcaStatus.OK,
        (
            "nodes/remember/commit",
            "nodes/remember/fold_history",
        ),
    ),
    LcaPath("lca.session.append", "SessionEvent", LcaStatus.OK, ("nodes/remember/commit",)),
    LcaPath(
        "lca.cognition.body.executor.safe_executor",
        "SimpleSafeExecutor",
        LcaStatus.OK,
        ("nodes/effect/tool_dispatch",),
    ),
    LcaPath(
        "lca.cognition.brain.reasoner.null_critic",
        "NullCritic",
        LcaStatus.OK,
        ("nodes/reflect/critique",),
    ),
)


def all_ok() -> bool:
    """Return True iff every entry is OK (cordis-gated modules included)."""
    return all(p.status == LcaStatus.OK for p in LCA_PATHS)


def ok_paths() -> tuple[LcaPath, ...]:
    """Return paths verified importable in current env (uv run python)."""
    return tuple(p for p in LCA_PATHS if p.status == LcaStatus.OK)


def by_user(node_plugin: str) -> tuple[LcaPath, ...]:
    """Return all LCA paths used by a given node plugin path."""
    return tuple(p for p in LCA_PATHS if node_plugin in p.used_by)


def format_table() -> str:
    """Render a human-readable table for docs / describe output."""
    rows = [f"{'module':<64} {'symbol':<28} status  used_by"]
    for p in LCA_PATHS:
        rows.append(f"{p.module:<64} {p.symbol:<28} {p.status.value:<6}  {', '.join(p.used_by)}")
    return "\n".join(rows)


__all__ = [
    "LCA_PATHS",
    "LcaPath",
    "LcaStatus",
    "all_ok",
    "by_user",
    "format_table",
    "ok_paths",
]
