"""SSOT: LCA real module paths + runtime availability + fallback policy.

Generated from runtime probes on 2026-09-08 against lca main + lca_kernel.

Each entry: (module_path, symbol, runtime_status, fallback_class).
Runtime status:
  OK   — `from lca.X import Y` works in current env
  MISS — ModuleNotFoundError or missing symbol
          (typically because the LCA hard dep `cordis` is not installed)
  FB   — adapter fell back to a _Noop* stub

Fallback policy:
  - OK  → node plugins import directly
  - MISS → node plugins use `try: from lca.X except ImportError: use _Noop*`
           The _Noop* stub is defined in the same node plugin file,
           co-located with the consumer (no central fallback registry)
  - FB  → adapter-only behaviour, no longer needed after refactor
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class LcaStatus(StrEnum):
    OK = "ok"             # direct import works
    MISS = "miss"         # import fails (missing cordis / not in env)
    FB = "fallback"       # was only used inside adapter fallback chain


@dataclass(frozen=True)
class LcaPath:
    module: str
    symbol: str
    status: LcaStatus
    used_by: tuple[str, ...]   # which node plugin / adapter depends on this


# --- Provenance: runtime probes, not docs ---------------------------------
# Each entry below was verified by `python -c "from <module> import <symbol>"`
# at the time of generation.

LCA_PATHS: tuple[LcaPath, ...] = (
    # ── OK: direct import works in current env ──
    LcaPath("lca.contracts.atoms.enums.enums", "ActionType",
            LcaStatus.OK, ("nodes/think/parse_decision",)),
    LcaPath("lca.contracts.atoms.enums.enums", "ReflectionVerdict",
            LcaStatus.OK, ("nodes/reflect/join_reflection_inputs",)),
    LcaPath("lca.contracts.atoms.ids.ids", "new_id",
            LcaStatus.OK, ("nodes/reflect/call_critic", "nodes/reflex adapters")),
    LcaPath("lca.contracts.models.core.execution.decision", "Decision",
            LcaStatus.OK, ("nodes/think/parse_decision", "nodes/think/gate_enforce",
                           "nodes/remember/append_event", "nodes/stop/evaluate_stop")),
    LcaPath("lca.contracts.models.core.execution.decision", "Observation",
            LcaStatus.OK, ("nodes/reflect/call_critic",)),
    LcaPath("lca.contracts.models.core.execution.decision", "Reflection",
            LcaStatus.OK, ("nodes/reflect/extract_memory_candidates",
                           "nodes/reflect/persist_memory")),
    LcaPath("lca.contracts.models.core.execution.decision", "ToolCall",
            LcaStatus.OK, ("nodes/think/parse_decision", "nodes/stop/evaluate_stop")),
    LcaPath("lca.contracts.models.core.conversation.llm", "LLMResponse",
            LcaStatus.OK, ("nodes/think/parse_decision",)),
    LcaPath("lca.contracts.models.core.conversation.llm", "NativeToolCall",
            LcaStatus.OK, ("nodes/think/parse_decision",)),
    LcaPath("lca.contracts.models.core.conversation.llm", "TokenUsage",
            LcaStatus.OK, ("nodes/think/parse_decision",)),
    LcaPath("lca.contracts.models.core.policy.stop", "StopDecision",
            LcaStatus.OK, ("nodes/stop/evaluate_stop",)),
    LcaPath("lca.contracts.models.core.policy.stop", "StopReason",
            LcaStatus.OK, ("nodes/stop/evaluate_stop",)),
    LcaPath("lca.contracts.models.core.state.lifecycle", "TaskStatus",
            LcaStatus.OK, ("nodes/stop/evaluate_stop",)),
    LcaPath("lca.contracts.models.core.state.lifecycle", "coerce_status",
            LcaStatus.OK, ("nodes/stop/evaluate_stop",)),
    LcaPath("lca.contracts.models.core.state.state", "AgentState",
            LcaStatus.OK, ("nodes/perceive/perceive_fold",
                           "nodes/reflect/call_critic", "nodes/reflex adapters")),
    LcaPath("lca.contracts.models.team.role.team", "ToolPermissionManifest",
            LcaStatus.OK, ("nodes/effect/tool_dispatch",)),
    LcaPath("lca.contracts.protocols.session.model.context", "ModelContextAssembler",
            LcaStatus.OK, ("nodes/model_visible/commit_manifest",)),
    LcaPath("lca.contracts.protocols.session.model.context", "ModelVisibleRequest",
            LcaStatus.OK, ("nodes/model_visible/commit_manifest",)),
    LcaPath("lca.infrastructure.llm_adapter.openai_compat", "OpenAICompatAdapter",
            LcaStatus.OK, ("nodes/think/call_llm",)),
    LcaPath("lca.infrastructure.session.context.model_context_assembler",
            "DefaultModelContextAssembler",
            LcaStatus.OK, ("nodes/model_visible/commit_manifest",)),

    # ── MISS: blocked by missing `cordis` dep (installable, but not now) ──
    # Node plugins MUST wrap these in `try: from lca.X except ImportError: _Noop*`
    LcaPath("lca.session.append", "Session",
            LcaStatus.MISS, ("nodes/remember/append_event",
                              "nodes/remember/tail_events",
                              "nodes/remember/fold_messages")),
    LcaPath("lca.session.append", "SessionEvent",
            LcaStatus.MISS, ("nodes/remember/append_event",)),
    LcaPath("lca.cognition.body.executor.safe_executor", "SimpleSafeExecutor",
            LcaStatus.MISS, ("nodes/effect/tool_dispatch",)),
    LcaPath("lca.cognition.brain.reasoner.null_critic", "NullCritic",
            LcaStatus.MISS, ("nodes/reflect/call_critic",)),
    LcaPath("lca.plugins.composer.runtime.fixture.runtime_factory", "NullPerceiveHub",
            LcaStatus.MISS, ("nodes/perceive/perceive_fold",)),
)


def ok_paths() -> tuple[LcaPath, ...]:
    """Return only paths verified importable in current env."""
    return tuple(p for p in LCA_PATHS if p.status == LcaStatus.OK)


def miss_paths() -> tuple[LcaPath, ...]:
    """Return paths that need try/except fallback (missing cordis)."""
    return tuple(p for p in LCA_PATHS if p.status == LcaStatus.MISS)


def format_table() -> str:
    """Render a human-readable table for docs / describe output."""
    rows = ["module".ljust(64), "symbol".ljust(28), "status".ljust(6), "used_by"]
    for p in LCA_PATHS:
        rows.append(f"{p.module.ljust(64)} {p.symbol.ljust(28)} "
                    f"{p.status.value.ljust(6)} {', '.join(p.used_by)}")
    return "\n".join(rows)


__all__ = ["LcaPath", "LcaStatus", "LCA_PATHS", "ok_paths", "miss_paths", "format_table"]
