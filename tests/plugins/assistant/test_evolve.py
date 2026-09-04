"""assistant.evolve plugin tests（ADR-0187 §3 D9 + §7 PR-8）。

覆盖契约：

- distill：产 experiment 候选，**不落盘**到 ``skills/``；提案卡落
  ``{home}/.evolve/pending/``；发 ``assistant.skill.evolved.proposed`` EP
- promote 无 WriteApproval ⇒ 拒收（fail-closed）
- promote 有 approval ⇒ 0067 三闸 + 写 ``{home}/skills/`` +
  ``revision_seq++`` + 发 ``assistant.skill.evolved.promoted`` EP
- 跨助理隔离：A 的候选不得在 B 名下提升；B 的 list_pending 看不到 A
- SkillAcquirer 缝复用：同一 Protocol、独立 capability
- Plugin Manifest 形状（provides / requires / effects / test_suite）
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from lca.contracts.capabilities import ASSISTANT_EVOLVE
from lca.contracts.observability.assistant_ep_closure import (
    ASSISTANT_REQUIRED_FIELDS,
    ASSISTANT_SKILL_EVOLVED_PROMOTED,
    ASSISTANT_SKILL_EVOLVED_PROPOSED,
)
from lca.contracts.protocols.assistant.catalog import CreateAssistantRequest
from lca.contracts.protocols.assistant.evolve import (
    ObservationDigest,
    WriteApproval,
)
from lca.contracts.protocols.think.learning import SkillAcquirer
from lca.harness.plugin_api import definition_from_plugin
from lca.harness.plugin_manifest import EffectClass
from lca.plugins.assistant.catalog import AssistantCatalogImpl
from lca.plugins.assistant.evolve import (
    AssistantEvolveImpl,
    MissingWriteApproval,
    PromoteGateRejected,
    UnknownCandidate,
    setup,
)

_FIXED_NOW = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


# ── fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def emitted() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
def catalog(tmp_path: Path, emitted: list[tuple[str, dict[str, Any]]]) -> AssistantCatalogImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantCatalogImpl(root=tmp_path, event_emitter=_record)


@pytest.fixture
def evolve(
    catalog: AssistantCatalogImpl, emitted: list[tuple[str, dict[str, Any]]]
) -> AssistantEvolveImpl:
    def _record(event: str, payload: Mapping[str, Any]) -> None:
        emitted.append((event, dict(payload)))

    return AssistantEvolveImpl(
        catalog=catalog,
        event_emitter=_record,
        clock=lambda: _FIXED_NOW,
    )


@pytest.fixture
def assistant_id(catalog: AssistantCatalogImpl) -> str:
    return catalog.create(CreateAssistantRequest(name="Evolve Demo")).assistant_id


@pytest.fixture
def digest(assistant_id: str) -> ObservationDigest:
    return ObservationDigest(
        assistant_id=assistant_id,
        run_ids=("run-1", "run-2"),
        evidence_refs=("spine:run-1", "spine:run-2"),
        observed_at="2026-09-04T11:00:00Z",
    )


@pytest.fixture
def approval() -> WriteApproval:
    return WriteApproval(
        approved_by="lichao",
        approved_at="2026-09-04T12:30:00Z",
        reason="提案复盘通过,接受沉淀为技能",
    )


# ── observe ─────────────────────────────────────────────────────────


class TestObserve:
    def test_observe_returns_digest_with_spine_evidence(
        self, evolve: AssistantEvolveImpl, assistant_id: str
    ) -> None:
        digest = evolve.observe(assistant_id, ("run-a", "run-b"))
        assert digest.assistant_id == assistant_id
        assert digest.run_ids == ("run-a", "run-b")
        assert digest.evidence_refs == ("spine:run-a", "spine:run-b")
        assert digest.observed_at == "2026-09-04T12:00:00Z"

    def test_observe_empty_run_ids_rejected(
        self, evolve: AssistantEvolveImpl, assistant_id: str
    ) -> None:
        with pytest.raises(ValueError, match="run_id"):
            evolve.observe(assistant_id, ())

    def test_observe_unknown_assistant_fails_closed(self, evolve: AssistantEvolveImpl) -> None:
        from lca.plugins.assistant._home_layout import AssistantCatalogError

        with pytest.raises(AssistantCatalogError):
            evolve.observe("asst_missing", ("run-1",))


# ── distill：experiment 候选,默认不落盘(I-A8)────────────────────────


class TestDistill:
    def test_distill_returns_experiment_candidate(
        self, evolve: AssistantEvolveImpl, assistant_id: str, digest: ObservationDigest
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        assert candidate.status == "experiment"
        assert candidate.candidate_id.startswith("asst-skill-candidate-")
        assert candidate.task_ref.startswith(f"assistant:{assistant_id}:runs:")
        assert candidate.evidence_refs == digest.evidence_refs
        assert candidate.confidence > 0

    def test_distill_does_not_write_skills_dir(
        self,
        evolve: AssistantEvolveImpl,
        catalog: AssistantCatalogImpl,
        assistant_id: str,
        digest: ObservationDigest,
    ) -> None:
        """I-A8：distill 后 ``skills/`` 必须为空（默认不落盘）。"""
        evolve.distill(assistant_id, digest)
        home = Path(catalog.get(assistant_id).home_path)
        skills = home / "skills"
        assert skills.is_dir()
        assert list(skills.iterdir()) == []

    def test_distill_writes_pending_card_and_draft(
        self,
        evolve: AssistantEvolveImpl,
        catalog: AssistantCatalogImpl,
        assistant_id: str,
        digest: ObservationDigest,
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        home = Path(catalog.get(assistant_id).home_path)
        card_path = home / ".evolve" / "pending" / f"{candidate.candidate_id}.json"
        draft_path = home / ".evolve" / "pending" / f"{candidate.candidate_id}.md"
        assert card_path.is_file()
        assert draft_path.is_file()
        card = json.loads(card_path.read_text(encoding="utf-8"))
        assert card["assistant_id"] == assistant_id
        assert card["status"] == "experiment"
        assert card["scope"] == "experiment"
        assert card["draft_digest"].startswith("sha256:")
        assert card["skill_name"].startswith("evolved-")

    def test_distill_emits_proposed_ep_with_metadata_only(
        self,
        evolve: AssistantEvolveImpl,
        assistant_id: str,
        digest: ObservationDigest,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        events = [event for event, _ in emitted]
        assert ASSISTANT_SKILL_EVOLVED_PROPOSED in events
        payload = dict(emitted[events.index(ASSISTANT_SKILL_EVOLVED_PROPOSED)][1])
        for field_name in ASSISTANT_REQUIRED_FIELDS:
            assert field_name in payload
        assert payload["candidate_id"] == candidate.candidate_id
        assert payload["actor"] == "assistant.evolve"
        assert payload["draft_digest"].startswith("sha256:")

    def test_distill_same_input_is_deterministic(
        self, evolve: AssistantEvolveImpl, assistant_id: str, digest: ObservationDigest
    ) -> None:
        a = evolve.distill(assistant_id, digest)
        b = evolve.distill(assistant_id, digest)
        assert a.candidate_id == b.candidate_id


# ── propose：SkillAcquirer 证据门 ────────────────────────────────────


class TestProposeEvidenceGate:
    def test_implements_skill_acquirer_protocol(self, evolve: AssistantEvolveImpl) -> None:
        assert isinstance(evolve, SkillAcquirer)

    def test_propose_insufficient_evidence_returns_none(
        self, catalog: AssistantCatalogImpl
    ) -> None:
        impl = AssistantEvolveImpl(catalog=catalog, min_evidence=3)
        candidate = impl.propose(
            task_ref="t",
            procedure="p",
            success=True,
            confidence=0.9,
            evidence_refs=("e1",),
        )
        assert candidate is None

    def test_propose_low_confidence_returns_none(self, evolve: AssistantEvolveImpl) -> None:
        candidate = evolve.propose(
            task_ref="t",
            procedure="p",
            success=True,
            confidence=0.1,
            evidence_refs=("e1",),
        )
        assert candidate is None

    def test_propose_returns_experiment_candidate(self, evolve: AssistantEvolveImpl) -> None:
        candidate = evolve.propose(
            task_ref="t",
            procedure="p",
            success=True,
            confidence=0.9,
            evidence_refs=("e1",),
        )
        assert candidate is not None
        assert candidate.status == "experiment"


# ── list_pending ─────────────────────────────────────────────────────


class TestListPending:
    def test_list_pending_empty_initially(
        self, evolve: AssistantEvolveImpl, assistant_id: str
    ) -> None:
        assert evolve.list_pending(assistant_id) == ()

    def test_list_pending_returns_distilled_candidates(
        self, evolve: AssistantEvolveImpl, assistant_id: str, digest: ObservationDigest
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        pending = evolve.list_pending(assistant_id)
        assert len(pending) == 1
        assert pending[0].candidate_id == candidate.candidate_id
        assert pending[0].status == "experiment"
        assert pending[0].procedure  # 草稿正文从 .md 恢复


# ── promote：无审批拒收 ──────────────────────────────────────────────


class TestPromoteWithoutApproval:
    def test_promote_none_approval_rejected(
        self,
        evolve: AssistantEvolveImpl,
        assistant_id: str,
        digest: ObservationDigest,
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        with pytest.raises(MissingWriteApproval):
            evolve.promote(assistant_id, candidate.candidate_id, None)  # type: ignore[arg-type]

    def test_promote_non_approval_object_rejected(
        self,
        evolve: AssistantEvolveImpl,
        assistant_id: str,
        digest: ObservationDigest,
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        with pytest.raises(MissingWriteApproval):
            evolve.promote(assistant_id, candidate.candidate_id, {"approved_by": "x"})  # type: ignore[arg-type]

    def test_promote_unknown_candidate_rejected(
        self, evolve: AssistantEvolveImpl, assistant_id: str, approval: WriteApproval
    ) -> None:
        with pytest.raises(UnknownCandidate):
            evolve.promote(assistant_id, "asst-skill-candidate-missing", approval)


# ── promote：有审批 ⇒ 0067 闸 + 写 Home + EP ────────────────────────


class TestPromoteWithApproval:
    def test_promote_writes_skill_package(
        self,
        evolve: AssistantEvolveImpl,
        catalog: AssistantCatalogImpl,
        assistant_id: str,
        digest: ObservationDigest,
        approval: WriteApproval,
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        receipt = evolve.promote(assistant_id, candidate.candidate_id, approval)
        home = Path(catalog.get(assistant_id).home_path)
        skill_dir = home / "skills" / receipt.skill_name
        assert (skill_dir / "SKILL.md").is_file()
        install = json.loads((skill_dir / "install.json").read_text(encoding="utf-8"))
        assert install["state"] == "active"
        assert install["logical_id"] == candidate.candidate_id
        assert install["approved_by"] == "lichao"
        assert receipt.state == "active"
        assert receipt.skill_path == str(skill_dir)

    def test_promote_increments_revision_seq(
        self,
        evolve: AssistantEvolveImpl,
        catalog: AssistantCatalogImpl,
        assistant_id: str,
        digest: ObservationDigest,
        approval: WriteApproval,
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        before = catalog.get(assistant_id).revision_seq
        evolve.promote(assistant_id, candidate.candidate_id, approval)
        home = Path(catalog.get(assistant_id).home_path)
        manifest = json.loads((home / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["revision_seq"] == before + 1

    def test_promote_emits_promoted_ep_with_metadata_only(
        self,
        evolve: AssistantEvolveImpl,
        assistant_id: str,
        digest: ObservationDigest,
        approval: WriteApproval,
        emitted: list[tuple[str, dict[str, Any]]],
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        evolve.promote(assistant_id, candidate.candidate_id, approval)
        events = [event for event, _ in emitted]
        assert ASSISTANT_SKILL_EVOLVED_PROMOTED in events
        payload = dict(emitted[events.index(ASSISTANT_SKILL_EVOLVED_PROMOTED)][1])
        for field_name in ASSISTANT_REQUIRED_FIELDS:
            assert field_name in payload
        assert payload["candidate_id"] == candidate.candidate_id
        assert payload["approved_by"] == "lichao"
        assert payload["actor"] == "lichao"

    def test_promote_removes_pending_card(
        self,
        evolve: AssistantEvolveImpl,
        catalog: AssistantCatalogImpl,
        assistant_id: str,
        digest: ObservationDigest,
        approval: WriteApproval,
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        evolve.promote(assistant_id, candidate.candidate_id, approval)
        home = Path(catalog.get(assistant_id).home_path)
        pending_dir = home / ".evolve" / "pending"
        assert not (pending_dir / f"{candidate.candidate_id}.json").exists()
        assert evolve.list_pending(assistant_id) == ()

    def test_promote_twice_rejected_by_invariant_gate(
        self,
        evolve: AssistantEvolveImpl,
        assistant_id: str,
        digest: ObservationDigest,
        approval: WriteApproval,
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        evolve.promote(assistant_id, candidate.candidate_id, approval)
        # 第二次:候选卡已删 ⇒ UnknownCandidate（不得覆盖已提升包）
        with pytest.raises(UnknownCandidate):
            evolve.promote(assistant_id, candidate.candidate_id, approval)

    def test_promote_non_experiment_card_rejected_by_experiment_gate(
        self,
        evolve: AssistantEvolveImpl,
        catalog: AssistantCatalogImpl,
        assistant_id: str,
        digest: ObservationDigest,
        approval: WriteApproval,
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        home = Path(catalog.get(assistant_id).home_path)
        card_path = home / ".evolve" / "pending" / f"{candidate.candidate_id}.json"
        card = json.loads(card_path.read_text(encoding="utf-8"))
        card["status"] = "active"
        card_path.write_text(json.dumps(card), encoding="utf-8")
        with pytest.raises(PromoteGateRejected, match="experiment"):
            evolve.promote(assistant_id, candidate.candidate_id, approval)


# ── 跨助理隔离 ───────────────────────────────────────────────────────


class TestCrossAssistantIsolation:
    def test_promote_candidate_under_other_assistant_rejected(
        self,
        evolve: AssistantEvolveImpl,
        catalog: AssistantCatalogImpl,
        assistant_id: str,
        digest: ObservationDigest,
        approval: WriteApproval,
    ) -> None:
        candidate = evolve.distill(assistant_id, digest)
        other_id = catalog.create(CreateAssistantRequest(name="Other")).assistant_id
        with pytest.raises(UnknownCandidate):
            evolve.promote(other_id, candidate.candidate_id, approval)

    def test_promote_tampered_card_cross_assistant_rejected(
        self,
        evolve: AssistantEvolveImpl,
        catalog: AssistantCatalogImpl,
        assistant_id: str,
        digest: ObservationDigest,
        approval: WriteApproval,
    ) -> None:
        """把 A 的候选卡塞进 B 的 pending 目录 ⇒ identity 闸拒收。"""
        candidate = evolve.distill(assistant_id, digest)
        other_id = catalog.create(CreateAssistantRequest(name="Other")).assistant_id
        other_home = Path(catalog.get(other_id).home_path)
        pending_dir = other_home / ".evolve" / "pending"
        pending_dir.mkdir(parents=True, exist_ok=True)
        home = Path(catalog.get(assistant_id).home_path)
        for suffix in (".json", ".md"):
            src = home / ".evolve" / "pending" / f"{candidate.candidate_id}{suffix}"
            (pending_dir / src.name).write_bytes(src.read_bytes())
        with pytest.raises(PromoteGateRejected, match="identity"):
            evolve.promote(other_id, candidate.candidate_id, approval)

    def test_list_pending_isolated_per_assistant(
        self,
        evolve: AssistantEvolveImpl,
        catalog: AssistantCatalogImpl,
        assistant_id: str,
        digest: ObservationDigest,
    ) -> None:
        evolve.distill(assistant_id, digest)
        other_id = catalog.create(CreateAssistantRequest(name="Other")).assistant_id
        assert evolve.list_pending(other_id) == ()
        assert len(evolve.list_pending(assistant_id)) == 1


# ── Plugin Manifest 形状 ────────────────────────────────────────────


class TestPluginManifest:
    def test_definition_id_namespace(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.id == "lca.plugins.assistant.evolve"

    def test_provides_assistant_evolve(self) -> None:
        definition = definition_from_plugin(setup)
        assert ASSISTANT_EVOLVE.key in definition.provided_capability_keys

    def test_requires_catalog(self) -> None:
        definition = definition_from_plugin(setup)
        assert "assistant.catalog" in definition.required_capability_keys

    def test_effects_include_filesystem(self) -> None:
        definition = definition_from_plugin(setup)
        assert EffectClass.FILESYSTEM in definition.spec.effects

    def test_test_suite_path_matches(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.spec.verification.test_suite == "tests/plugins/assistant/test_evolve.py"

    def test_ownership_emits_two_evolve_eps(self) -> None:
        definition = definition_from_plugin(setup)
        assert definition.ownership is not None
        assert set(definition.ownership.emits) == {
            ASSISTANT_SKILL_EVOLVED_PROPOSED,
            ASSISTANT_SKILL_EVOLVED_PROMOTED,
        }

    def test_config_rejects_extra_keys(self) -> None:
        from pydantic import ValidationError

        from lca.plugins.assistant.evolve import Config

        with pytest.raises(ValidationError):
            Config.model_validate({"min_confidence": 0.5, "extra": "x"})
