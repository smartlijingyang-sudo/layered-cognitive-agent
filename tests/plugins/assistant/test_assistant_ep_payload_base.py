"""RA-022 接缝契约：``_AssistantEPPayloadBase``（frozen dataclass）。

9 个 assistant 域 EP payload 收敛到 frozen-dataclass 基类后，基类承诺的
四件事必须被测试钉住（RA-022 落地时 lca-only、tests 侧零新增）：

1. frozen——构造后任何字段赋值/删除都抛 ``FrozenInstanceError``；
2. 基类四件套守门被 9 家共享——某子类改写 ``__post_init__`` 漏调 super
   会立刻红；
3. ``to_dict`` 四件套打头 + 真值 extra 按 ``_extra_items`` 顺序（RA-022
   声称的字节等价）、空 extra 不进 payload；
4. extra 字段守门经基类 ``__post_init__`` 的 ``_validate_extra_fields``
   hook 分发——hook 接线断了会红。
"""

from __future__ import annotations

import dataclasses

import pytest

from lca.plugins.assistant.events._events import (
    AssistantBootstrapCompletedEventPayload,
    AssistantCreatedEventPayload,
    AssistantJobFiredEventPayload,
    AssistantJobRegisteredEventPayload,
    AssistantProfileRevisedEventPayload,
    AssistantSkillActivatedEventPayload,
    AssistantSkillEvolvedPromotedEventPayload,
    AssistantSkillEvolvedProposedEventPayload,
    AssistantSkillInstalledEventPayload,
)

_BASE = {
    "assistant_id": "a1",
    "revision_seq": 3,
    "manifest_digest": "sha256:abc",
    "actor": "system",
}

# 9 个 payload 的最小合法构造参数（RA-022 收敛后的真实签名实证）。
_PAYLOADS = [
    ("created", AssistantCreatedEventPayload, {}),
    ("bootstrap_completed", AssistantBootstrapCompletedEventPayload, {}),
    ("profile_revised", AssistantProfileRevisedEventPayload, {}),
    (
        "skill_evolved_proposed",
        AssistantSkillEvolvedProposedEventPayload,
        {"candidate_id": "c1", "skill_name": "s1"},
    ),
    (
        "skill_evolved_promoted",
        AssistantSkillEvolvedPromotedEventPayload,
        {"candidate_id": "c1", "skill_name": "s1", "approved_by": "u1"},
    ),
    (
        "job_registered",
        AssistantJobRegisteredEventPayload,
        {"job_id": "j1", "work_item_id": "w1"},
    ),
    (
        "job_fired",
        AssistantJobFiredEventPayload,
        {"job_id": "j1", "work_item_id": "w1", "trigger_id": "t1"},
    ),
    (
        "skill_installed",
        AssistantSkillInstalledEventPayload,
        {"skill_id": "s1", "skill_digest": "sha256:def", "artifact_state": "ready"},
    ),
    (
        "skill_activated",
        AssistantSkillActivatedEventPayload,
        {"skill_id": "s1", "activation_id": "act1"},
    ),
]


def _make(cls, extra=None, **overrides):
    kwargs = dict(_BASE)
    kwargs.update(extra or {})
    kwargs.update(overrides)
    return cls(**kwargs)


@pytest.mark.parametrize("name,cls,extra", _PAYLOADS, ids=[p[0] for p in _PAYLOADS])
class TestFrozen:
    """frozen 契约：9 个 payload 构造后不可变。"""

    def test_setattr_raises(self, name, cls, extra) -> None:
        p = _make(cls, extra)
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.actor = "hacker"  # type: ignore[misc]

    def test_delattr_raises(self, name, cls, extra) -> None:
        p = _make(cls, extra)
        with pytest.raises(dataclasses.FrozenInstanceError):
            del p.actor  # type: ignore[misc]


@pytest.mark.parametrize("name,cls,extra", _PAYLOADS, ids=[p[0] for p in _PAYLOADS])
class TestSharedBaseGate:
    """基类四件套守门被 9 家共享（基类 __post_init__ 接线契约）。"""

    def test_empty_assistant_id_rejected(self, name, cls, extra) -> None:
        with pytest.raises(ValueError, match="assistant_id"):
            _make(cls, extra, assistant_id="")

    def test_negative_revision_seq_rejected(self, name, cls, extra) -> None:
        with pytest.raises(ValueError, match="revision_seq"):
            _make(cls, extra, revision_seq=-1)


@pytest.mark.parametrize(
    "name,cls,extra,blank_field",
    [
        (
            "skill_evolved_proposed",
            AssistantSkillEvolvedProposedEventPayload,
            {"candidate_id": "c1", "skill_name": "s1"},
            "candidate_id",
        ),
        (
            "skill_evolved_promoted",
            AssistantSkillEvolvedPromotedEventPayload,
            {"candidate_id": "c1", "skill_name": "s1", "approved_by": "u1"},
            "approved_by",
        ),
        (
            "job_registered",
            AssistantJobRegisteredEventPayload,
            {"job_id": "j1", "work_item_id": "w1"},
            "job_id",
        ),
        (
            "job_fired",
            AssistantJobFiredEventPayload,
            {"job_id": "j1", "work_item_id": "w1", "trigger_id": "t1"},
            "trigger_id",
        ),
        (
            "skill_installed",
            AssistantSkillInstalledEventPayload,
            {"skill_id": "s1", "skill_digest": "sha256:def", "artifact_state": "ready"},
            "skill_digest",
        ),
        (
            "skill_activated",
            AssistantSkillActivatedEventPayload,
            {"skill_id": "s1", "activation_id": "act1"},
            "activation_id",
        ),
    ],
    ids=[
        "skill_evolved_proposed",
        "skill_evolved_promoted",
        "job_registered",
        "job_fired",
        "skill_installed",
        "skill_activated",
    ],
)
def test_extra_field_gate_dispatched_through_base_hook(
    name, cls, extra, blank_field
) -> None:
    """extra 守门经基类 _validate_extra_fields hook 分发（接线契约）。"""
    bad = dict(extra)
    bad[blank_field] = ""
    with pytest.raises(ValueError, match=blank_field):
        _make(cls, bad)


class TestToDict:
    """to_dict：四件套打头 + 真值 extra 按 _extra_items 顺序（字节等价契约）。"""

    def test_required_fields_lead_in_canonical_order(self) -> None:
        p = _make(
            AssistantCreatedEventPayload,
            {"home_path": "/h", "template_id": "t-default"},
        )
        assert list(p.to_dict()) == [
            "assistant_id",
            "revision_seq",
            "manifest_digest",
            "actor",
            "home_path",
            "template_id",
        ]

    def test_falsy_extras_excluded(self) -> None:
        p = _make(AssistantCreatedEventPayload)
        assert p.to_dict() == {
            "assistant_id": "a1",
            "revision_seq": 3,
            "manifest_digest": "sha256:abc",
            "actor": "system",
        }

    def test_extra_order_follows_extra_items(self) -> None:
        p = _make(
            AssistantSkillInstalledEventPayload,
            {
                "skill_id": "s1",
                "skill_digest": "sha256:def",
                "artifact_state": "ready",
                "source": "registry",
                "version": "1.2.0",
                "installed_at": "2026-10-08",
            },
        )
        assert p.to_dict() == {
            "assistant_id": "a1",
            "revision_seq": 3,
            "manifest_digest": "sha256:abc",
            "actor": "system",
            "skill_id": "s1",
            "skill_digest": "sha256:def",
            "artifact_state": "ready",
            "source": "registry",
            "version": "1.2.0",
            "installed_at": "2026-10-08",
        }

    def test_changes_tuple_serialized_as_list(self) -> None:
        p = _make(
            AssistantProfileRevisedEventPayload,
            {"reason": "user asked", "changes": ("model", "runtime")},
        )
        assert p.to_dict()["changes"] == ["model", "runtime"]


class TestValueSemantics:
    """frozen dataclass 的值语义：相等 + 可哈希。"""

    def test_equal_payloads_compare_equal(self) -> None:
        assert _make(AssistantCreatedEventPayload) == _make(AssistantCreatedEventPayload)

    def test_different_revision_seq_not_equal(self) -> None:
        assert _make(AssistantCreatedEventPayload) != _make(
            AssistantCreatedEventPayload, revision_seq=4
        )

    def test_payloads_are_hashable(self) -> None:
        p = _make(AssistantJobFiredEventPayload, {"job_id": "j1", "work_item_id": "w1", "trigger_id": "t1"})
        assert len({p, _make(AssistantJobFiredEventPayload, {"job_id": "j1", "work_item_id": "w1", "trigger_id": "t1"})}) == 1
