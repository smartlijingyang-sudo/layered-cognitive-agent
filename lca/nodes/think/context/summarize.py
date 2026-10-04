"""``think.context.summarize`` graph node (ADR-0283).

Single responsibility: sediment-before-compact + structured summary.
At/above the shared 0.7 soft gate the node:

1. splits the payload into ``kept`` (tail, toward the 0.5 settle target)
   and the doomed head region;
2. runs the sediment pass over the head region — candidate facts are
   persisted through the memory write path with
   ``metadata["source"] = "compaction"`` (ADR-0283 C1);
3. builds a structured :class:`CompactSummary` and prepends its rendering
   to the kept tail.

Fail-closed (ADR-0283 C2): if the sediment pass raises, persists nothing
when it should have, or no writer is installed, the node does NOT
summarize — it degrades to ``truncate_oldest`` and the receipt honestly
records ``strategy="truncate_oldest"`` with ``sedimented=0``.
"0 sedimented + summarize" never emits.

If the summary's own byte overhead exceeds the savings, the node still
byte-cuts — but the sediment evidence is preserved (facts are already in
memory; the receipt keeps ``sedimented=N``).

Failure semantics mirror ``think.context.truncate``: any unexpected
exception yields ``CompactReceipt.skipped`` — never raises out of the
graph. Like truncate, this node is evidence-only: typed
``CompactReceipt`` out, payload application stays the orchestrator's job.

v1 summarization is extractive-deterministic (no LLM in the loop) so the
acceptance bar — 100% retention of planted facts on fixtures — is
enforceable. The prompt file ``summarize_prompt.md`` is the contract a
future LLM-backed summarizer must satisfy.

Canonical shape: hand-written ``@dataclass(frozen=True, slots=True)`` +
``@plugin(...)`` carrier, per ADR-0228 D2. Executor method count stays
within the PR-B bound (``tests/architecture/test_node_def_count.py``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.dto.compact_receipt import CompactReceipt
from lca.contracts.dto.compact_summary import CompactSummary
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.state.state import Budget
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeContext,
    NodeInput,
    NodeOutput,
)
from lca.contracts.protocols.declarative.declarative_1.ports import PortName
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.nodes.think.context.budgeting import (
    TARGET_AFTER_RATIO,
    payload_byte_size,
    resolve_budget,
    resolve_context_payload,
    should_compact,
    truncate_oldest_to_byte_budget,
)
from lca.nodes.think.context.sediment import (
    SedimentCandidate,
    extract_sediment_candidates,
    get_sediment_writer,
)

# Must match the "<!-- SUMMARIZE_PROMPT_VERSION: ... -->" marker in
# summarize_prompt.md (drift is a test failure, ADR-0283 T4).
SUMMARIZE_PROMPT_VERSION = "v1"

# Honest "we lost this" ledger caps (ADR-0283 C4).
MAX_DROPPED_LEDGER = 20
_MAX_DROPPED_REPR_CHARS = 120

_SUMMARY_MARKER = "[compact-summary"


def summarize_prompt_version() -> str:
    """Read the version marker from ``summarize_prompt.md``."""
    text = Path(__file__).with_name("summarize_prompt.md").read_text(encoding="utf-8")
    match = re.search(r"SUMMARIZE_PROMPT_VERSION:\s*([^\s>]+)", text)
    if match is None:
        raise ValueError("summarize_prompt.md lacks a SUMMARIZE_PROMPT_VERSION marker")
    return match.group(1)


def build_compact_summary(
    candidates: tuple[SedimentCandidate, ...],
    dropped: tuple[str, ...],
    *,
    prompt_version: str = SUMMARIZE_PROMPT_VERSION,
) -> CompactSummary:
    """Fold sediment candidates into the structured summary DTO.

    ``fact``-class candidates land in ``entity_states`` (the DTO has no
    generic bucket by design — every fact is either a decision, a
    commitment, an entity state, or an open question).
    """
    decisions: list[str] = []
    commitments: list[str] = []
    entity_states: list[str] = []
    open_questions: list[str] = []
    for candidate in candidates:
        if candidate.category == "decision":
            decisions.append(candidate.content)
        elif candidate.category == "commitment":
            commitments.append(candidate.content)
        elif candidate.category == "open_question":
            open_questions.append(candidate.content)
        else:  # "entity_state" | "fact"
            entity_states.append(candidate.content)
    return CompactSummary(
        decisions=tuple(decisions),
        commitments=tuple(commitments),
        entity_states=tuple(entity_states),
        open_questions=tuple(open_questions),
        dropped=tuple(dropped[:MAX_DROPPED_LEDGER]),
        prompt_version=prompt_version,
    )


def render_compact_summary(summary: CompactSummary) -> str:
    """Deterministic one-block rendering prepended to the kept tail."""

    def _section(title: str, items: tuple[str, ...]) -> list[str]:
        lines = [f"{title}:"]
        lines.extend(f"- {item}" for item in items)
        return lines

    lines = [f"{_SUMMARY_MARKER} {summary.prompt_version}]"]
    lines += _section("decisions", summary.decisions)
    lines += _section("commitments", summary.commitments)
    lines += _section("entity_states", summary.entity_states)
    lines += _section("open_questions", summary.open_questions)
    lines.append(f"dropped_without_sediment: {len(summary.dropped)}")
    return "\n".join(lines)


def _compact_with_sediment(
    *,
    payload: tuple[Any, ...],
    budget: Budget,
) -> tuple[CompactReceipt, tuple[Any, ...], CompactSummary | None]:
    """Sediment-before-compact core (pure logic; the node is a thin wrapper).

    Returns ``(receipt, new_payload, summary_or_None)``. The node emits
    only the receipt (evidence-only design, mirroring truncate); tests
    assert on the full triple.
    """
    bytes_before = payload_byte_size(payload)
    if not should_compact(budget):
        return CompactReceipt.noop(bytes_seen=bytes_before), payload, None

    target_bytes = int(TARGET_AFTER_RATIO * (budget.max_tokens or 0))
    kept = truncate_oldest_to_byte_budget(payload, target_bytes=target_bytes)
    if kept == payload:
        return CompactReceipt.noop(bytes_seen=bytes_before), payload, None

    def _byte_cut(*, sedimented: int) -> tuple[CompactReceipt, tuple[Any, ...], None]:
        """Fail-closed fallback: pure byte cut, honestly labeled (C2).

        ``sedimented`` is preserved — facts already persisted to memory
        stay evidenced even when the in-context summary is dropped.
        """
        return (
            CompactReceipt.applied(
                bytes_before=bytes_before,
                bytes_after=payload_byte_size(kept),
                strategy="truncate_oldest",
                sedimented=sedimented,
            ),
            kept,
            None,
        )

    dropped_region = payload[: len(payload) - len(kept)]
    candidates = extract_sediment_candidates(dropped_region)

    sedimented = 0
    if candidates:
        writer = get_sediment_writer()
        if writer is None:
            return _byte_cut(sedimented=0)  # B1: no bootstrap — fail closed
        try:
            sedimented = writer.write(candidates)
        except Exception:
            return _byte_cut(sedimented=0)
        if sedimented < len(candidates):
            # Partial persistence is not persistence.
            return _byte_cut(sedimented=0)

    covered = {candidate.source_index for candidate in candidates}
    dropped_ledger = tuple(
        repr(item)[:_MAX_DROPPED_REPR_CHARS]
        for index, item in enumerate(dropped_region)
        if index not in covered
    )
    summary = build_compact_summary(candidates, dropped_ledger)
    rendered = render_compact_summary(summary)
    new_payload = (rendered, *kept)
    bytes_after = payload_byte_size(new_payload)
    if bytes_after > bytes_before:
        # Summary overhead exceeds the savings: keep the byte cut, keep
        # the sediment evidence (facts are already in memory).
        return _byte_cut(sedimented=sedimented)
    return (
        CompactReceipt.applied(
            bytes_before=bytes_before,
            bytes_after=bytes_after,
            strategy="summarize",
            sedimented=sedimented,
        ),
        new_payload,
        summary,
    )


@dataclass(frozen=True, slots=True)
class ThinkContextSummarizeExecutor:
    """think.context.summarize 节点: typed ``(budget, context_payload)`` → ``CompactReceipt``."""

    semantic_name: str = "think.context.summarize"
    region: str = "think"
    declared_inputs: tuple = ()
    declared_outputs: tuple[PortName, ...] = (PortName("compact_receipt"),)

    async def node_execute(
        self,
        context: NodeContext,
        input: NodeInput,
    ) -> NodeOutput:
        """Sediment first, then summarize; degrade to byte cut on sediment failure."""
        budget = resolve_budget(context=context)
        payload = resolve_context_payload(context=context)
        try:
            receipt, _, _ = _compact_with_sediment(payload=payload, budget=budget)
        except Exception:
            receipt = CompactReceipt.skipped(bytes_seen=0)
        return NodeOutput(port_values={PortName("compact_receipt"): receipt})


@plugin(
    id="phase.think.context.summarize",
    Config=None,
    provides=("think::think.context.summarize",),
    requires=(),
    layer="L2",
    kind=PluginKind.PRIMITIVE,
    effects="none",
    description=(
        "Sediment-before-compact + structured summary (ADR-0283). "
        "Extracts facts from the compacted-away region into memory before "
        "summarizing; fail-closed degrade to truncate_oldest."
    ),
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=(
                "phase_think_context_summarize.checked",
                "phase_think_context_summarize.served",
            )
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=("plugin.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config=None) -> None:
    """Composite-key 注册: ``{region}::{semantic_name}``。"""
    del config
    executor = ThinkContextSummarizeExecutor()
    composite_key = f"{executor.region}::{executor.semantic_name}"
    ctx.provide(composite_key, executor)


__all__ = [
    "MAX_DROPPED_LEDGER",
    "SUMMARIZE_PROMPT_VERSION",
    "ThinkContextSummarizeExecutor",
    "build_compact_summary",
    "render_compact_summary",
    "setup",
    "summarize_prompt_version",
]
