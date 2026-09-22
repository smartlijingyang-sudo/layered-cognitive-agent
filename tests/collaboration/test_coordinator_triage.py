from lca.application.collaboration.triage import (
    CoordinatorTriageRouter,
    TriageDecisionKind,
)


def test_coordinator_triage_solo_for_simple_tasks():
    router = CoordinatorTriageRouter()
    decision = router.triage("请帮我看一下当前目录有哪些文件")
    assert decision.kind == TriageDecisionKind.SOLO
    assert decision.selected_peers == ()
    assert len(decision.envelopes) == 0


def test_coordinator_triage_single_peer_handoff():
    router = CoordinatorTriageRouter()
    decision = router.triage("请让观澜帮我定一下系统的领域契约与Seam边界")
    assert decision.kind == TriageDecisionKind.PEER_HANDOFF
    assert decision.selected_peers == ("architecture/guanlan",)
    assert len(decision.envelopes) == 1
    assert decision.envelopes[0].receiver_id == "architecture/guanlan"
    assert decision.envelopes[0].intent == "delegate"


def test_coordinator_triage_cast_for_architecture_tasks():
    router = CoordinatorTriageRouter()
    decision = router.triage(
        "请帮我深度重构审批流系统，涉及状态机迁移、Reducer单写不变量、分层契约和对抗审计"
    )
    assert decision.kind == TriageDecisionKind.TEAM_CAST
    assert set(decision.selected_peers) == {
        "architecture/guanlan",
        "architecture/hengyue",
        "architecture/jingchuan",
    }
    assert len(decision.envelopes) == 3
    receivers = {env.receiver_id for env in decision.envelopes}
    assert receivers == {
        "architecture/guanlan",
        "architecture/hengyue",
        "architecture/jingchuan",
    }
    for env in decision.envelopes:
        assert (
            env.objective
            == "请帮我深度重构审批流系统，涉及状态机迁移、Reducer单写不变量、分层契约和对抗审计"
        )
        assert "topic" in env.context_slice


def test_triage_router_dynamic_candidates_mention():
    from lca.contracts.models.collaboration.peer import PeerProfile

    custom_peer = PeerProfile(
        peer_id="custom_auditor",
        name="安全守卫",
        role="网络安全审计师",
        description="系统漏洞审查",
        home_namespace="/home/user/.lca/assistants/custom_auditor",
    )
    router = CoordinatorTriageRouter(candidates=(custom_peer,))
    decision = router.triage("请 @安全守卫 审查下当前的防火墙规则")
    assert decision.kind == TriageDecisionKind.PEER_HANDOFF
    assert decision.selected_peers == ("custom_auditor",)
    assert "安全守卫" in decision.reasoning
    assert decision.envelopes[0].receiver_id == "custom_auditor"
