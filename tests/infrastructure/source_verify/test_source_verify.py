"""Tests for lca.infrastructure.source_verify (+ contracts).

覆盖: 来源登记 → 引用提取 → 逐断言裁决（四种 verdict）→ 答案级决定（三档 mode）.
"""

from lca.contracts.models.cognition.source_verify import (
    ClaimVerdict,
    SourceKind,
    VerifyMode,
)
from lca.infrastructure.source_verify import (
    SourceRegistry,
    SourceVerifier,
    VerifyPolicy,
    extract_citations,
    source_marker,
    split_claims,
    verify_final_answer,
)


def _registry() -> SourceRegistry:
    r = SourceRegistry()
    r.register_tool_result(
        call_id="call_acct",
        tool_name="readFile",
        content="账户记录: 当前套餐为标准版, 无退款条款.",
        label="账户记录",
    )
    r.register_tool_result(
        call_id="call_policy",
        tool_name="readFile",
        content="政策文档: 标准版套餐包含 30 天退款窗口, 自开通日起算.",
        label="政策文档",
    )
    return r


def test_source_id_stable_and_marker() -> None:
    r = SourceRegistry()
    ref = r.register_tool_result(call_id="c1", tool_name="t", content="x")
    assert ref.source_id == "tool:c1"
    assert source_marker(ref.source_id) == "[source:tool:c1]"
    assert ref.kind == SourceKind.TOOL
    assert len(r) == 1


def test_resolve_label() -> None:
    r = _registry()
    assert r.resolve_label("账户记录") == "tool:call_acct"
    assert r.resolve_label("readFile") == "tool:call_acct"  # tool_name 也可解析
    assert r.resolve_label("不存在") is None


def test_split_claims() -> None:
    claims = split_claims("第一句。第二句！\n第三句？")
    assert claims == ("第一句。", "第二句！", "第三句？")


def test_extract_explicit_marker() -> None:
    r = _registry()
    claim = "退款窗口为 30 天 [source:tool:call_policy]。"
    assert extract_citations(claim, r) == ("tool:call_policy",)


def test_extract_label_citation() -> None:
    r = _registry()
    assert extract_citations("根据账户记录, 套餐为标准版。", r) == ("tool:call_acct",)
    assert extract_citations("今天天气不错。", r) == ()


def test_verdict_supported() -> None:
    r = _registry()
    d = verify_final_answer("根据政策文档, 退款窗口为 30 天。", r)
    assert d.decision == "pass"
    assert len(d.verdicts) == 1
    assert d.verdicts[0].verdict == ClaimVerdict.SUPPORTED


def test_verdict_unresolvable_cites_ghost_source() -> None:
    r = _registry()
    d = verify_final_answer("根据用户手册, 退款窗口为 30 天。", r)
    # "用户手册"不在 registry 里 —— resolve_label 返回 None, 无引用, 跳过
    assert d.decision == "pass"
    d2 = verify_final_answer("详见 [source:tool:call_ghost] 的说明。", r)
    assert d2.decision == "needs_review"
    assert d2.verdicts[0].verdict == ClaimVerdict.UNRESOLVABLE


def test_verdict_conflated_wrong_attribution() -> None:
    r = _registry()
    # 30 天在政策文档里, 不在账户记录里 —— 跨来源混同
    d = verify_final_answer("根据账户记录, 该套餐包含 30 天退款窗口。", r)
    assert d.decision == "needs_review"
    v = d.verdicts[0]
    assert v.verdict == ClaimVerdict.CONFLATED
    assert v.cited_source_id == "tool:call_acct"
    assert v.matched_source_id == "tool:call_policy"


def test_verdict_unsupported_literal_nowhere() -> None:
    r = _registry()
    d = verify_final_answer("根据账户记录, 退款窗口为 90 天。", r)
    assert d.decision == "needs_review"
    assert d.verdicts[0].verdict == ClaimVerdict.UNSUPPORTED


def test_no_citation_no_penalty() -> None:
    r = _registry()
    d = verify_final_answer("今天天气不错, 适合出门。", r)
    assert d.decision == "pass"
    assert d.verdicts == ()


def test_mode_off_skips_everything() -> None:
    r = _registry()
    d = verify_final_answer(
        "根据账户记录, 该套餐包含 30 天退款窗口。",
        r,
        VerifyPolicy.disabled(),
    )
    assert d.decision == "pass"
    assert d.verdicts == ()
    assert d.mode == VerifyMode.OFF


def test_mode_enforce_blocks() -> None:
    r = _registry()
    d = SourceVerifier(VerifyPolicy.enforcing()).verify(
        "根据账户记录, 该套餐包含 30 天退款窗口。", r
    )
    assert d.decision == "block"
    assert d.mode == VerifyMode.ENFORCE


def test_policy_defaults() -> None:
    assert VerifyPolicy.default().mode == VerifyMode.WARN
    assert VerifyPolicy.disabled().mode == VerifyMode.OFF
    assert VerifyPolicy.enforcing().mode == VerifyMode.ENFORCE
