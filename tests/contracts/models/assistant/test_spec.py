"""Tests for ADR-0187 §3 D3 AssistantSpec / AssistantBootstrapRefs frozen views.

Contract surface only: no Catalog implementation, no plugins. PR-2 scope
(ADR-0187 §7 PR-2) gates ``AssistantSpec`` shape and ``__post_init__``
invariants; PR-3+ adds the Catalog that materializes these values.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass, replace

import pytest

from lca.contracts.models.assistant.spec import AssistantBootstrapRefs, AssistantSpec
from lca.contracts.models.team.role_team import RoleProfile, ToolPermissionManifest
from lca.contracts.protocols.journal.spec import AgentSpec

# ── helpers ────────────────────────────────────────────────


def _agent_spec() -> AgentSpec:
    """最小合法 AgentSpec（ADR-0033 声明式构造）。"""
    profile = RoleProfile(
        role="assistant.role",
        goal="be helpful",
        backstory="default",
        tool_permission_manifest=ToolPermissionManifest(allowed_tools=[]),
    )
    return AgentSpec(profile=profile, llm=_StubLLM())


@dataclass
class _StubLLM:
    """Protocol 形状的 LLM 替身（runtime_checkable 不要求真实现）。"""

    async def complete(self, prompt: str, **kwargs: object) -> object:  # pragma: no cover
        return None

    async def stream(self, prompt: str, **kwargs: object):  # pragma: no cover
        if False:
            yield None


def _bootstrap() -> AssistantBootstrapRefs:
    return AssistantBootstrapRefs(
        soul_digest="soul-abc",
        identity_digest="identity-abc",
        user_digest="user-abc",
        agents_digest="agents-abc",
    )


def _spec() -> AssistantSpec:
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


# ── AssistantBootstrapRefs ────────────────────────────────────


class TestAssistantBootstrapRefs:
    def test_construction_stores_digests(self) -> None:
        refs = _bootstrap()
        assert refs.soul_digest == "soul-abc"
        assert refs.identity_digest == "identity-abc"
        assert refs.user_digest == "user-abc"
        assert refs.agents_digest == "agents-abc"

    @pytest.mark.parametrize(
        "field_name",
        ["soul_digest", "identity_digest", "user_digest", "agents_digest"],
    )
    def test_empty_digest_rejected(self, field_name: str) -> None:
        valid = {
            "soul_digest": "soul-abc",
            "identity_digest": "identity-abc",
            "user_digest": "user-abc",
            "agents_digest": "agents-abc",
        }
        valid[field_name] = ""
        with pytest.raises(ValueError, match=field_name):
            AssistantBootstrapRefs(**valid)

    def test_frozen_instance_rejects_mutation(self) -> None:
        with pytest.raises(FrozenInstanceError):
            _bootstrap().soul_digest = "tampered"  # type: ignore[misc]


# ── AssistantSpec ───────────────────────────────────────────


class TestAssistantSpec:
    def test_construction_preserves_fields(self) -> None:
        spec = _spec()
        assert spec.assistant_id == "asst_demo"
        assert spec.home_path == "/var/lca/assistants/asst_demo"
        assert spec.revision_seq == 0
        assert spec.template_id == "assistant.default"
        assert spec.profile_name == "Demo"
        assert spec.profile_description == "demo assistant"
        assert spec.bootstrap.soul_digest == "soul-abc"
        assert spec.skill_ids == ()
        assert spec.job_ids == ()
        assert spec.grant_digest == "grant-abc"
        assert spec.tools_policy_digest == "tools-abc"

    def test_frozen_rejects_field_mutation(self) -> None:
        with pytest.raises(FrozenInstanceError):
            _spec().revision_seq = 99  # type: ignore[misc]

    def test_dataclass_replace_is_the_only_mutation_path(self) -> None:
        spec = _spec()
        revised = replace(spec, revision_seq=spec.revision_seq + 1)
        assert revised.revision_seq == 1
        assert spec.revision_seq == 0  # original is untouched

    def test_empty_assistant_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="assistant_id"):
            AssistantSpec(
                assistant_id="",
                home_path="/var/lca/assistants/demo",
                revision_seq=0,
                template_id="assistant.default",
                profile_name="Demo",
                profile_description="",
                agent_spec=_agent_spec(),
                bootstrap=_bootstrap(),
                skill_ids=(),
                job_ids=(),
                grant_digest="g",
                tools_policy_digest="t",
            )

    def test_empty_home_path_rejected(self) -> None:
        with pytest.raises(ValueError, match="home_path"):
            AssistantSpec(
                assistant_id="asst_demo",
                home_path="",
                revision_seq=0,
                template_id="assistant.default",
                profile_name="Demo",
                profile_description="",
                agent_spec=_agent_spec(),
                bootstrap=_bootstrap(),
                skill_ids=(),
                job_ids=(),
                grant_digest="g",
                tools_policy_digest="t",
            )

    def test_negative_revision_seq_rejected(self) -> None:
        with pytest.raises(ValueError, match="revision_seq"):
            AssistantSpec(
                assistant_id="asst_demo",
                home_path="/var/lca/assistants/demo",
                revision_seq=-1,
                template_id="assistant.default",
                profile_name="Demo",
                profile_description="",
                agent_spec=_agent_spec(),
                bootstrap=_bootstrap(),
                skill_ids=(),
                job_ids=(),
                grant_digest="g",
                tools_policy_digest="t",
            )

    def test_empty_template_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="template_id"):
            AssistantSpec(
                assistant_id="asst_demo",
                home_path="/var/lca/assistants/demo",
                revision_seq=0,
                template_id="",
                profile_name="Demo",
                profile_description="",
                agent_spec=_agent_spec(),
                bootstrap=_bootstrap(),
                skill_ids=(),
                job_ids=(),
                grant_digest="g",
                tools_policy_digest="t",
            )

    def test_empty_grant_digest_rejected(self) -> None:
        with pytest.raises(ValueError, match="grant_digest"):
            AssistantSpec(
                assistant_id="asst_demo",
                home_path="/var/lca/assistants/demo",
                revision_seq=0,
                template_id="assistant.default",
                profile_name="Demo",
                profile_description="",
                agent_spec=_agent_spec(),
                bootstrap=_bootstrap(),
                skill_ids=(),
                job_ids=(),
                grant_digest="",
                tools_policy_digest="t",
            )

    def test_empty_tools_policy_digest_rejected(self) -> None:
        with pytest.raises(ValueError, match="tools_policy_digest"):
            AssistantSpec(
                assistant_id="asst_demo",
                home_path="/var/lca/assistants/demo",
                revision_seq=0,
                template_id="assistant.default",
                profile_name="Demo",
                profile_description="",
                agent_spec=_agent_spec(),
                bootstrap=_bootstrap(),
                skill_ids=(),
                job_ids=(),
                grant_digest="g",
                tools_policy_digest="",
            )
