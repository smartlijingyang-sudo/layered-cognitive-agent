"""Procedural-memory curator (ADR-0244 D6.2).

Passive ``RuntimeLifecycleSubscriber`` that observes terminal run events,
extracts the generic ``ProceduralMemoryCandidate`` produced by
``phase.reflect.score`` from the run spine, and stages a proposal in the run
directory. On user confirmation, ``confirm`` installs a distilled skill into
``{assistant_home}/skills/`` through the sanctioned ``assistant.skill_overlay``
seam (C10 narrow door). No scheduler, thread, or timer is used (I-A12).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.capabilities import (
    ASSISTANT_CURATOR,
    ASSISTANT_SKILL_OVERLAY,
    RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY,
)
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.protocols.assistant.skill_overlay import SkillSource
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.contracts.protocols.runtime.runtime.lifecycle import (
    RuntimeLifecycleEvent,
    RuntimeLifecycleEventType,
    RuntimeLifecycleSubscriber,
    RuntimeLifecycleSubscriberContribution,
    RuntimeLifecycleSubscriberRegistry,
)
from lca.harness.plugin.manifest import EffectClass
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.skill_overlay import (
        AssistantSkillOverlay,
        SkillInstallReceipt,
    )

_TERMINAL_TYPES = frozenset(
    {
        RuntimeLifecycleEventType.COMPLETED,
        RuntimeLifecycleEventType.PARTIAL,
        RuntimeLifecycleEventType.FAILED,
    }
)

_PROPOSAL_FILENAME = "curator_proposal.json"
_CONFIRMED_FILENAME = "curator_proposal.confirmed.json"


def _find_candidate(obj: Any) -> dict[str, Any] | None:
    """Recursively locate a ``procedural_candidate`` dict in a parsed spine record."""
    if isinstance(obj, dict):
        candidate = obj.get("procedural_candidate")
        if isinstance(candidate, dict):
            return candidate
        for value in obj.values():
            found = _find_candidate(value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_candidate(value)
            if found is not None:
                return found
    return None


def extract_procedural_candidate(run_dir: Path) -> dict[str, Any] | None:
    """Scan the run spine for the first ``ProceduralMemoryCandidate`` payload."""
    spine = run_dir / f"{run_dir.name}.spine.jsonl"
    if not spine.is_file():
        return None
    for line in spine.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "procedural_candidate" not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        candidate = _find_candidate(record.get("payload", {}))
        if candidate is not None:
            return candidate
    return None


def build_skill_md(candidate: dict[str, Any], run_id: str) -> str:
    """Build a minimal SKILL.md from a generic procedural candidate."""
    workflow = str(candidate.get("workflow_summary") or "Distilled procedural workflow")
    steps = candidate.get("tool_sequence") or []
    short = run_id[-8:] if run_id else "sop"
    name = f"procedural-{short}"
    step_lines = "\n".join(f"{i + 1}. {step}" for i, step in enumerate(steps))
    if not step_lines:
        step_lines = "1. Follow the recorded workflow."
    return (
        f"---\n"
        f"name: {name}\n"
        f"description: {workflow}. Trigger when the user asks to repeat this workflow or save it as a reusable procedure.\n"
        f"---\n\n"
        f"# {workflow}\n\n## Steps\n\n{step_lines}\n"
    )


class ProceduralCurator:
    """Passive terminal subscriber that stages and confirms procedural skills."""

    def __init__(
        self,
        overlay: AssistantSkillOverlay,
        traces_root: Path,
    ) -> None:
        self._overlay = overlay
        self._traces_root = traces_root

    async def publish(self, event: RuntimeLifecycleEvent) -> None:
        """Stage a proposal when the run spine carries a procedural candidate."""
        if event.type not in _TERMINAL_TYPES:
            return
        run_dir = self._traces_root / event.trace_id
        candidate = extract_procedural_candidate(run_dir)
        if candidate is None:
            return
        proposal = {
            "run_id": event.trace_id,
            "candidate": candidate,
            "status": "proposed",
        }
        (run_dir / _PROPOSAL_FILENAME).write_text(
            json.dumps(proposal, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    async def confirm(self, assistant_id: str, run_id: str) -> SkillInstallReceipt | None:
        """Install the proposed workflow as a skill for one assistant (idempotent)."""
        run_dir = self._traces_root / run_id
        proposal_path = run_dir / _PROPOSAL_FILENAME
        confirmed_path = run_dir / _CONFIRMED_FILENAME
        if not proposal_path.is_file() or confirmed_path.is_file():
            return None
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        candidate = proposal["candidate"]
        staging = run_dir / ".curator-staging"
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "SKILL.md").write_text(
            build_skill_md(candidate, run_id),
            encoding="utf-8",
        )
        try:
            receipt = await self._overlay.install(
                assistant_id,
                SkillSource(local_path=str(staging)),
                actor="curator",
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        confirmed_path.write_text(
            json.dumps(
                {**proposal, "status": "confirmed", "assistant_id": assistant_id},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return receipt


@plugin(
    id="lca-assistant-curator",
    provides=[ASSISTANT_CURATOR.key],
    requires=[
        RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key,
        ASSISTANT_SKILL_OVERLAY.key,
    ],
    implements=[RuntimeLifecycleSubscriber],
    layer="L4",
    effects=EffectClass.FILESYSTEM,
    description="Procedural-memory curation: propose and confirm distilled skills (ADR-0244 D6.2).",
    test_suite="tests/plugins/assistant/test_curator.py",
    kind=PluginKind.PROVIDER,
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.PROFILE,)),
        authority=AuthorityContract(grants=("plugin.serve",)),
        observability=EvidenceContract(
            descriptors=("lca-assistant-curator.checked", "lca-assistant-curator.served")
        ),
    ),
    relations=(),
    ownership=OwnershipDeclaration(
        reads=("plugin.serve",),
        emits=(),
        state_mutation="scoped",
    ),
)
async def setup(ctx: PluginContext, config: object) -> None:
    """Wire the curator and register it as a passive terminal subscriber."""
    del config
    registry = ctx.require(RUNTIME_LIFECYCLE_SUBSCRIBER_REGISTRY.key)
    if not isinstance(registry, RuntimeLifecycleSubscriberRegistry):
        raise TypeError(
            "runtime_lifecycle_subscriber_registry must implement "
            "RuntimeLifecycleSubscriberRegistry"
        )
    overlay = ctx.require(ASSISTANT_SKILL_OVERLAY.key)
    traces_root = Path("traces") / "runs"
    curator = ProceduralCurator(
        overlay=overlay,
        traces_root=traces_root,
    )
    ctx.provide(ASSISTANT_CURATOR.key, curator)
    registry.register(
        RuntimeLifecycleSubscriberContribution(
            id="assistant-curator",
            subscriber=curator,
            priority=90,
        )
    )


__all__ = [
    "ProceduralCurator",
    "build_skill_md",
    "extract_procedural_candidate",
    "setup",
]
