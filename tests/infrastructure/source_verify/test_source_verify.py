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


def test_literal_grammar_chinese_date_forms() -> None:
    # 文法直接单测: 无需构建 SourceRegistry
    from lca.infrastructure.source_verify import default_literal_extractor

    assert "2026年10月1日" in default_literal_extractor("截止 2026年10月1日 生效。")
    assert "2026-10-01" in default_literal_extractor("截止 2026-10-01 生效。")


def test_literal_grammar_identifier_length_boundary() -> None:
    from lca.infrastructure.source_verify import default_literal_extractor

    lits = default_literal_extractor("编号 abc 与 abcd。")
    assert "abcd" in lits  # 4 字符标识符被抽取
    assert "abc" not in lits  # 3 字符标识符不在文法内


def test_literal_extractor_seam_is_used_by_judge() -> None:
    # 注入固定抽取器: _judge_claim 必须走接缝, 而非模块私有文法
    from lca.infrastructure.source_verify import SourceVerifier

    r = _registry()
    v = SourceVerifier(literal_extractor=lambda claim: ("90 天",))
    d = v.verify("根据账户记录, 退款窗口为 30 天。", r)
    assert d.decision == "needs_review"
    assert d.verdicts[0].verdict == ClaimVerdict.UNSUPPORTED


def test_default_extractor_keeps_pipeline_semantics() -> None:
    # 默认实现 = 旧文法: 流水线判决语义不变
    from lca.infrastructure.source_verify import SourceVerifier

    r = _registry()
    d = SourceVerifier().verify("根据政策文档, 退款窗口为 30 天。", r)
    assert d.decision == "pass"
    assert d.verdicts[0].verdict == ClaimVerdict.SUPPORTED


def test_empty_registry_does_not_pass_explicit_unknown_source() -> None:
    from lca.contracts.models.core.state.state import AgentState, Budget
    from lca.framework.graph.host_wiring import NodeRuntimeView
    from lca.infrastructure.source_verify.registry import ensure_registry
    from lca.runtime.support.runtime_bindings import RuntimePhaseCapabilities

    registry = SourceRegistry()
    state = AgentState(
        trace_id="source-empty-registry",
        task="verify source",
        budget=Budget(),
        extra={"keep": "reducer-owned"},
    )
    runtime = NodeRuntimeView(
        state=state,
        scope=RuntimePhaseCapabilities({"source_registry": registry}),
    )
    assert ensure_registry(runtime) is registry

    decision = verify_final_answer("详见 [source:tool:call_missing] 的原始记录。", registry)

    assert decision.decision == "needs_review"
    assert decision.mode == VerifyMode.WARN
    assert len(decision.verdicts) == 1
    assert decision.verdicts[0].verdict == ClaimVerdict.UNRESOLVABLE
    assert state.extra == {"keep": "reducer-owned"}
