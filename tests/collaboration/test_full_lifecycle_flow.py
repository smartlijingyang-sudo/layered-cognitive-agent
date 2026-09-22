"""Full-lifecycle end-to-end integration flow tests for Peer Assistants & Rooms (ADR-0250).

Chains together:
1. Workspace materialization of peer specialists (Guanlan, Hengyue, Jingchuan) into persistent AssistantHomes
2. Multi-agent Room creation, persistence in JsonRoomRepository, and lifecycle management
3. RoomMessageRouter policy enforcement (coordinator_first convergence vs mention_only routing)
4. Coordinator Think-phase Tool invocation (TeamCastTool & HandoffToPeerTool)
5. Hermes-style anti-context-pollution and CrewAI mandatory Fold aggregation
6. Fault tolerance, timeout and error degradation handling
7. Frontend CollaborationTeamBar and Collapse payload contract compatibility
8. AP-01 Negative boundaries and AP-02 test invariants
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from lca.application.collaboration.fold import DelegationFoldAggregator
from lca.application.collaboration.peer_provider import (
    PeerProfileResolver,
    materialize_peer_assistant,
)
from lca.application.collaboration.triage import (
    CoordinatorTriageRouter,
    TriageDecisionKind,
)
from lca.contracts.models.collaboration.peer import (
    HandoffEnvelope,
    PeerFoldedResult,
    PeerProfile,
    RoomSpec,
)
from lca.domain.collaboration.room import JsonRoomRepository, RoomMessageRouter
from lca.infrastructure.tools.collaboration.delegate_tool import (
    HandoffToPeerTool,
    TeamCastTool,
)


@pytest.mark.asyncio
async def test_full_collaboration_system_lifecycle_flow(tmp_path: Path):
    """端到端完整协同生命周期串联测试。"""
    lca_home = tmp_path / ".lca"

    # =========================================================================
    # Step 1: 真实工作区物化与角色解析 (PeerProfileResolver & Materializer)
    # =========================================================================
    resolver = PeerProfileResolver(base_home=lca_home)
    triad_profiles = resolver.resolve_triad()
    assert len(triad_profiles) == 3

    materialized_paths: dict[str, Path] = {}
    for profile in triad_profiles:
        home_dir = materialize_peer_assistant(profile)
        materialized_paths[profile.peer_id] = home_dir
        # 验证文件落盘
        assert (home_dir / "SOUL.md").is_file()
        assert (home_dir / "USER.md").is_file()
        assert (home_dir / "AGENTS.md").is_file()
        assert (home_dir / "meta.json").is_file()

        meta = json.loads((home_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["peer_id"] == profile.peer_id
        assert len(meta["capabilities"]) > 0

    # =========================================================================
    # Step 2: 群聊房间创建与仓储持久化 (RoomSpec & JsonRoomRepository)
    # =========================================================================
    repo = JsonRoomRepository(base_dir=lca_home)
    room = RoomSpec(
        room_id="room_arch_war_room",
        display_name="架构作战室",
        coordinator_agent_id="coordinator_sam",
        member_peer_ids=tuple(p.peer_id for p in triad_profiles),
        shared_topic_id="topic_war_room_001",
        routing_policy="coordinator_first",
    )
    repo.save(room)

    # 验证真实落盘并可恢复 (C8 确定性)
    assert (lca_home / "rooms" / "room_arch_war_room.json").is_file()
    recovered_room = repo.get("room_arch_war_room")
    assert recovered_room is not None
    assert recovered_room.display_name == "架构作战室"
    assert recovered_room.member_peer_ids == ("arch_guanlan", "arch_hengyue", "arch_jingchuan")

    # =========================================================================
    # Step 3: 入站消息确定性路由分流 (RoomMessageRouter)
    # =========================================================================
    router = RoomMessageRouter(recovered_room)

    # 3.1 普通非点名消息 -> 严格收敛至协调者单点
    recipients_general = router.route_message("请帮我梳理一下系统当前的整体架构状态")
    assert recipients_general == ("coordinator_sam",)

    # 3.2 显式点名 @观澜 -> 路由至观澜
    recipients_mention_guanlan = router.route_message("@观澜 请核查当前模块的契约边界")
    assert recipients_mention_guanlan == ("arch_guanlan",)

    # 3.3 联合点名 @衡岳 @镜川 -> 同时路由至两名专家
    recipients_mention_both = router.route_message("@衡岳 @镜川 请对状态机迁移与反模式做对抗审查")
    assert set(recipients_mention_both) == {"arch_hengyue", "arch_jingchuan"}

    # =========================================================================
    # Step 4: 协调者接收到复合系统架构任务并触发 Triage (CoordinatorTriageRouter)
    # =========================================================================
    triage_router = CoordinatorTriageRouter()
    objective = "架构室紧急攻坚：重构协同子系统，理清领域边界与Seam接口，保证Reducer状态单写不变量，并对死锁隐患进行对抗反模式审查"
    decision = triage_router.triage(objective, correlation_id="cor_flow_001")

    assert decision.kind == TriageDecisionKind.TEAM_CAST
    assert len(decision.envelopes) == 3
    assert decision.selected_peers == (
        "architecture/guanlan",
        "architecture/hengyue",
        "architecture/jingchuan",
    )

    # 验证生成的 Handoff 信封具备干净切片，无全量聊天历史污染
    for env in decision.envelopes:
        assert env.intent == "delegate"
        assert env.context_slice["topic"] == "architecture_collaboration"
        assert env.timeout_ms == 60000

    # =========================================================================
    # Step 5: 协调者在认知循环中调用 TeamCastTool 执行协同 (TeamCastTool)
    # =========================================================================
    team_tool = TeamCastTool(router=triage_router)
    obs = await team_tool.execute(
        {
            "objective": objective,
            "context_extra": {"room_id": "room_arch_war_room", "session_id": "sess_001"},
        }
    )

    assert obs.success is True
    payload = obs.payload
    assert payload["consensus_status"] == "unanimous"
    assert "架构三角已形成完全共识" in payload["synthesized_verdict"]
    assert len(payload["member_findings"]) == 3

    # =========================================================================
    # Step 6: Hermes 防上下文污染断言 (Hermes Isolation)
    # =========================================================================
    # 模拟专家沙箱产生的带噪音原始输出
    simulated_raw_noisy_outputs = {
        "architecture/guanlan": (
            "DEBUG: scanning contracts/\n$ git diff --check\n观澜结论：契约定义清晰，禁止额外字段。"
        ),
        "architecture/hengyue": (
            "TRACE: reducer lock acquisition\n衡岳结论：状态机迁移符合 C4 单写原则。"
        ),
        "architecture/jingchuan": (
            "INFO: running antipattern rules\ncommit abcdef1234567890\n镜川结论：未发现反模式违例。"
        ),
    }
    aggregator = DelegationFoldAggregator()
    folded: PeerFoldedResult = aggregator.fold("task_flow_001", simulated_raw_noisy_outputs)

    for _peer_id, clean_finding in folded.member_findings.items():
        assert "DEBUG:" not in clean_finding
        assert "TRACE:" not in clean_finding
        assert "INFO:" not in clean_finding
        assert "$" not in clean_finding
        assert "commit" not in clean_finding

    # =========================================================================
    # Step 7: 前端数据映射与折叠卡片契约核验 (Frontend Data Contract)
    # =========================================================================
    # 验证最终报告文本包含触发前端 CollaborationTeamBar 的关键字
    assert "【架构协同汇报】" in payload["synthesized_verdict"]
    # 验证 payload 能被前端 extra / metadata 直接消费并构造 3 个展开详情
    findings = payload["member_findings"]
    assert any("观澜" in k or "guanlan" in k for k in findings)
    assert any("衡岳" in k or "hengyue" in k for k in findings)
    assert any("镜川" in k or "jingchuan" in k for k in findings)


@pytest.mark.asyncio
async def test_full_collaboration_degradation_and_handoff_flow(tmp_path: Path):
    """测试单点转交与专家异常/超时降级容错串联流程。"""
    # 1. 单点转交工具测试
    handoff_tool = HandoffToPeerTool()
    obs = await handoff_tool.execute(
        {
            "peer_id": "arch_guanlan",
            "objective": "定向请教：如何保证领域契约的 extra='forbid' 约束不被绕过？",
            "context_slice": {"caller": "coordinator"},
        }
    )
    assert obs.success is True
    assert obs.payload["receiver_id"] == "arch_guanlan"
    assert "已成功转交" in obs.payload["status_message"]

    # 2. 模拟多专家协同中的超时与报错降级 (Fault Tolerance)
    aggregator = DelegationFoldAggregator()
    receipts_with_failures = {
        "architecture/guanlan": "观澜结论：契约边界合规通过",
        "architecture/hengyue": "[ERROR] 状态机验证模块内部抛出异常",
        "architecture/jingchuan": "[TIMEOUT] 审查耗时超过 60000ms 触发熔断截断",
    }
    folded = aggregator.fold("task_degradation_001", receipts_with_failures)

    assert folded.consensus_status == "concerns_noted"
    assert "部分降级" in folded.synthesized_verdict
    assert "镜川分析超时" in folded.synthesized_verdict
    assert "衡岳执行异常" in folded.synthesized_verdict
    assert "基于就绪专家（观澜）" in folded.synthesized_verdict

    # 3. 测试 mention_only 房间纯点名策略
    mention_room = RoomSpec(
        room_id="room_quiet",
        display_name="静默协同室",
        coordinator_agent_id="coordinator_sam",
        member_peer_ids=("arch_guanlan", "arch_hengyue", "arch_jingchuan"),
        shared_topic_id="topic_quiet_001",
        routing_policy="mention_only",
    )
    quiet_router = RoomMessageRouter(mention_room)
    assert quiet_router.route_message("大家有什么新想法吗？") == ()
    assert quiet_router.route_message("@衡岳 请看下") == ("arch_hengyue",)


def test_negative_boundaries_and_contracts_invariants():
    """验证架构铁律：AP-01 负向清单守卫与 AP-02 自动化测试不变量。"""
    # AP-01 负向清单：认知 6 阶段目录严格保持纯净
    core_phase_dirs = [
        Path("lca/nodes/perceive"),
        Path("lca/nodes/think"),
        Path("lca/nodes/act"),
        Path("lca/nodes/reflect"),
        Path("lca/nodes/remember"),
    ]
    for pdir in core_phase_dirs:
        assert pdir.is_dir()

    # AP-02 测试不变量：模型不可变性 (frozen=True) 与严禁额外字段 (extra="forbid")
    profile = PeerProfile(
        peer_id="arch_guanlan",
        name="观澜",
        role="总监",
        description="desc",
        home_namespace="/path",
        capabilities=("contracts",),
    )
    with pytest.raises(ValidationError):
        profile.name = "修改不可变属性将报错"

    with pytest.raises(ValidationError):
        PeerProfile(
            peer_id="arch_guanlan",
            name="观澜",
            role="总监",
            description="desc",
            home_namespace="/path",
            capabilities=(),
            extra_forbidden_field="fail",
        )

    envelope = HandoffEnvelope(
        correlation_id="cor_1",
        sender_id="sender",
        receiver_id="receiver",
        intent="consult",
        objective="obj",
        context_slice={},
    )
    with pytest.raises(ValidationError):
        envelope.intent = "delegate"

    result = PeerFoldedResult(
        task_id="t1",
        member_findings={},
        synthesized_verdict="ok",
        consensus_status="unanimous",
    )
    with pytest.raises(ValidationError):
        result.consensus_status = "split"
