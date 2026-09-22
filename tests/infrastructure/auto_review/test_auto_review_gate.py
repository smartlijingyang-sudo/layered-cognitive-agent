from lca.contracts.models.auto_review.models import AutoReviewAction, AutoReviewMode
from lca.infrastructure.auto_review.gate import AutoReviewGate


def test_gate_off_mode_always_allows():
    gate = AutoReviewGate(mode=AutoReviewMode.OFF)
    verdict = gate.evaluate("run_shell", {"command": "rm -rf /home/box/data"})
    assert verdict.action == AutoReviewAction.ALLOW


def test_gate_shadow_mode_audits_and_allows():
    gate = AutoReviewGate(mode=AutoReviewMode.SHADOW)
    verdict = gate.evaluate("run_shell", {"command": "rm -rf /home/box/data"})
    assert verdict.action == AutoReviewAction.ALLOW
    assert len(gate.get_audit_records()) == 1
    assert gate.get_audit_records()[0]["flagged"] is True


def test_gate_enforce_mode_blocks_dangerous_and_adapt():
    gate = AutoReviewGate(mode=AutoReviewMode.ENFORCE)
    verdict = gate.evaluate("run_shell", {"command": "cat /etc/shadow"})
    assert verdict.action == AutoReviewAction.BLOCK


def test_gate_enforce_escalate_and_verify_fingerprint():
    gate = AutoReviewGate(mode=AutoReviewMode.ENFORCE)
    args = {"command": "rm -rf /home/box/cache"}
    verdict = gate.evaluate("run_shell", args)
    assert verdict.action == AutoReviewAction.ESCALATE
    fp = verdict.action_fingerprint
    assert fp is not None

    # 人工审批放行
    gate.grant_approval(fp)

    # 1. 相同动作原封不动重放：放行
    replay_verdict = gate.evaluate("run_shell", args)
    assert replay_verdict.action == AutoReviewAction.ALLOW

    # 2. 换命令试图偷渡：拒绝
    tampered_verdict = gate.evaluate("run_shell", {"command": "rm -rf /home/box/other"})
    assert tampered_verdict.action == AutoReviewAction.ESCALATE
