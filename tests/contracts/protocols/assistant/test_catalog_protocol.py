"""Tests for ADR-0187 §3 D4 AssistantCatalog Protocol + supporting dataclasses.

Scope: Protocol shape, runtime_checkable acceptance, and ``__post_init__``
invariants of the supporting dataclasses. PR-2 keeps the Catalog as a
Protocol only; PR-3 lands the implementation.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

import pytest

from lca.contracts.models.assistant.spec import AssistantBootstrapRefs, AssistantSpec
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols.assistant.catalog import (
    AssistantCatalog,
    AssistantHandle,
    AssistantSummary,
    CreateAssistantRequest,
    PlanRevision,
    ProfilePatch,
)
from lca.contracts.protocols.journal.spec import AgentSpec

# ── helpers ────────────────────────────────────────────────


@dataclass
class _StubLLM:
    async def complete(self, prompt: str, **kwargs: object) -> object:  # pragma: no cover
        return None

    async def stream(self, prompt: str, **kwargs: object):  # pragma: no cover
        if False:
            yield None


def _agent_spec() -> AgentSpec:
    return AgentSpec(
        profile=RoleProfile(
            role="assistant.role",
            goal="be helpful",
            backstory="default",
            tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
        ),
        llm=_StubLLM(),
    )


def _bootstrap() -> AssistantBootstrapRefs:
    return AssistantBootstrapRefs(
        soul_digest="soul-abc",
        identity_digest="identity-abc",
        user_digest="user-abc",
        agents_digest="agents-abc",
    )


def _assistant_spec() -> AssistantSpec:
    return AssistantSpec(
        assistant_id="asst_demo",
        home_path="/var/lca/assistants/asst_demo",
        revision_seq=0,
        template_id="assistant.default",
        profile_name="Demo",
        profile_description="demo assistant",
        agent_spec=_agent_spec(),
        bootstrap=_bootstrap(),
        skill_ids=(),
        job_ids=(),
        grant_digest="grant-abc",
        tools_policy_digest="tools-abc",
    )


class _FakeCatalog:
    """最小 AssistantCatalog 实现（仅 Protocol shape 校验用）。"""

    def create(self, req: CreateAssistantRequest) -> AssistantHandle:
        return AssistantHandle(
            assistant_id="asst_demo",
            home_path="/var/lca/assistants/demo",
            revision_seq=1,
        )

    def get(self, assistant_id: str) -> AssistantSpec:
        return _assistant_spec()

    def list(self) -> tuple[AssistantSummary, ...]:
        return ()

    def revise_profile(self, assistant_id: str, patch: ProfilePatch) -> PlanRevision:
        return PlanRevision(
            assistant_id=assistant_id,
            revision_seq=1,
            manifest_digest="manifest-abc",
            actor="user",
            snapshot_path="/var/lca/assistants/demo/revisions/1.json",
        )

    def reimport(self, assistant_id: str, reason: str) -> PlanRevision:
        return PlanRevision(
            assistant_id=assistant_id,
            revision_seq=1,
            manifest_digest="manifest-abc",
            actor="reimport",
            snapshot_path="/var/lca/assistants/demo/revisions/1.json",
        )

    def retire(self, assistant_id: str, reason: str) -> None:
        return None


class _MissingMethods:
    """故意缺失方法的占位实现，验证 isinstance() 拒绝。"""


# ── Protocol shape ──────────────────────────────────────────


class TestAssistantCatalogProtocol:
    def test_protocol_is_runtime_checkable(self) -> None:
        assert hasattr(AssistantCatalog, "__protocol_attrs__")

    def test_runtime_check_accepts_structural_match(self) -> None:
        assert isinstance(_FakeCatalog(), AssistantCatalog)

    def test_runtime_check_rejects_missing_methods(self) -> None:
        assert not isinstance(_MissingMethods(), AssistantCatalog)

    def test_protocol_defines_expected_methods(self) -> None:
        for method in ("create", "get", "list", "revise_profile", "reimport", "retire"):
            assert hasattr(AssistantCatalog, method)


# ── CreateAssistantRequest ──────────────────────────────────


class TestCreateAssistantRequest:
    def test_default_template_id_is_assistant_default(self) -> None:
        req = CreateAssistantRequest(name="Demo")
        assert req.template_id == "assistant.default"

    def test_empty_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="name"):
            CreateAssistantRequest(name="")

    def test_frozen_rejects_mutation(self) -> None:
        with pytest.raises(FrozenInstanceError):
            req = CreateAssistantRequest(name="Demo")
            req.name = "Other"  # type: ignore[misc]


# ── AssistantHandle / AssistantSummary ───────────────────────


class TestAssistantHandle:
    def test_minimal_handle(self) -> None:
        handle = AssistantHandle(
            assistant_id="a",
            home_path="/var/lca/assistants/demo",
            revision_seq=1,
        )
        assert handle.assistant_id == "a"
        assert handle.home_path == "/var/lca/assistants/demo"
        assert handle.revision_seq == 1


class TestAssistantSummary:
    def test_summary_defaults(self) -> None:
        summary = AssistantSummary(
            assistant_id="a",
            name="Demo",
            status="active",
            template_id="assistant.default",
            revision_seq=3,
            home_path="/var/lca/assistants/demo",
        )
        assert summary.skill_count == 0
        assert summary.job_count == 0
        assert summary.updated_at == ""


# ── ProfilePatch ────────────────────────────────────────────


class TestProfilePatch:
    def test_all_fields_default_to_none(self) -> None:
        patch = ProfilePatch()
        assert patch.profile_name is None
        assert patch.profile_description is None
        assert patch.soul_md is None
        assert patch.identity_md is None
        assert patch.user_md is None
        assert patch.agents_md is None
        assert patch.goals_yaml is None
        assert patch.grants_yaml is None
        assert patch.tools_yaml is None
        assert patch.skills is None
        assert patch.routines is None
        assert patch.extra == {}


# ── PlanRevision ───────────────────────────────────────────


class TestPlanRevision:
    def test_valid_revision(self) -> None:
        rev = PlanRevision(
            assistant_id="a",
            revision_seq=1,
            manifest_digest="m",
            actor="user",
            snapshot_path="/var/lca/assistants/demo/revisions/1.json",
        )
        assert rev.assistant_id == "a"
        assert rev.revision_seq == 1
        assert rev.actor == "user"

    def test_zero_or_negative_revision_seq_rejected(self) -> None:
        with pytest.raises(ValueError, match="revision_seq"):
            PlanRevision(
                assistant_id="a",
                revision_seq=0,
                manifest_digest="m",
                actor="user",
                snapshot_path="/var/lca/assistants/demo/revisions/1.json",
            )

    def test_empty_manifest_digest_rejected(self) -> None:
        with pytest.raises(ValueError, match="manifest_digest"):
            PlanRevision(
                assistant_id="a",
                revision_seq=1,
                manifest_digest="",
                actor="user",
                snapshot_path="/var/lca/assistants/demo/revisions/1.json",
            )

    def test_empty_actor_rejected(self) -> None:
        with pytest.raises(ValueError, match="actor"):
            PlanRevision(
                assistant_id="a",
                revision_seq=1,
                manifest_digest="m",
                actor="",
                snapshot_path="/var/lca/assistants/demo/revisions/1.json",
            )

    def test_empty_snapshot_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="snapshot_path"):
            PlanRevision(
                assistant_id="a",
                revision_seq=1,
                manifest_digest="m",
                actor="user",
                snapshot_path="",
            )
