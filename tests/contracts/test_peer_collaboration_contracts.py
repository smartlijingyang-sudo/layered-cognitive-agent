import pytest
from pydantic import ValidationError

from lca.contracts.models.collaboration.peer import (
    FoldedDelegationResult,
    HandoffEnvelope,
    PeerFoldedResult,
    PeerProfile,
    RoomSpec,
)


def test_peer_profile_immutability_and_forbid():
    peer = PeerProfile(
        peer_id="arch_guanlan",
        name="观澜",
        role="架构契约与边界总监",
        description="专注系统分层与第一性原理",
        home_namespace="/home/user/.lca/assistants/guanlan",
        capabilities=("contracts", "adr_guard"),
    )
    assert peer.peer_id == "arch_guanlan"
    assert peer.name == "观澜"

    # 额外非法字段必须触发 ValidationError (extra="forbid")
    with pytest.raises(ValidationError):
        PeerProfile(
            peer_id="arch_guanlan",
            name="观澜",
            role="架构",
            description="desc",
            home_namespace="/path",
            capabilities=(),
            illegal_extra="forbidden",
        )

    # 修改属性必须触发 ValidationError (frozen=True)
    with pytest.raises(ValidationError):
        peer.name = "新名字"


def test_handoff_envelope_contract():
    envelope = HandoffEnvelope(
        correlation_id="run_12345",
        sender_id="coordinator_sam",
        receiver_id="arch_hengyue",
        intent="delegate",
        objective="审查状态机与不变量",
        context_slice={"topic": "approval_engine"},
    )
    assert envelope.intent == "delegate"
    assert envelope.timeout_ms == 60000
    assert envelope.priority is False

    # 额外非法字段必须拒绝
    with pytest.raises(ValidationError):
        HandoffEnvelope(
            correlation_id="run_12345",
            sender_id="coordinator_sam",
            receiver_id="arch_hengyue",
            intent="delegate",
            objective="审查",
            context_slice={},
            unknown_arg=123,
        )


def test_room_spec_contract():
    room = RoomSpec(
        room_id="room_arch_studio",
        display_name="李超架构室",
        coordinator_agent_id="coordinator_sam",
        member_peer_ids=("arch_guanlan", "arch_hengyue", "arch_jingchuan"),
        shared_topic_id="topic_999",
    )
    assert room.routing_policy == "coordinator_first"
    assert len(room.member_peer_ids) == 3


def test_folded_delegation_result_contract():
    result = FoldedDelegationResult(
        task_id="task_12345",
        member_findings={
            "arch_guanlan": "边界严密，协议无泄漏",
            "arch_hengyue": "符合C4 Reducer单写不变量",
        },
        synthesized_verdict="架构审查全数通过",
        consensus_status="unanimous",
    )
    assert PeerFoldedResult is FoldedDelegationResult
    assert result.consensus_status == "unanimous"
    assert len(result.member_findings) == 2

    # 序列化/反序列化一致性 (C8/C13)
    dumped = result.model_dump_json()
    restored = PeerFoldedResult.model_validate_json(dumped)
    assert restored == result

    # 额外字段必须拒绝 (extra="forbid")
    with pytest.raises(ValidationError):
        PeerFoldedResult(
            task_id="task_12345",
            member_findings={},
            synthesized_verdict="ok",
            consensus_status="unanimous",
            illegal="value",
        )


def test_peer_folded_result_supports_member_metadata():
    result = PeerFoldedResult(
        task_id="task_meta_1",
        member_findings={"custom/analyst": "分析完成"},
        synthesized_verdict="【协同汇报】全员共识已形成",
        consensus_status="unanimous",
        member_metadata={
            "custom/analyst": {"name": "李四", "role": "数据分析师", "emoji": "📊"}
        },
    )
    assert result.member_metadata["custom/analyst"]["name"] == "李四"
    assert result.member_metadata["custom/analyst"]["emoji"] == "📊"
