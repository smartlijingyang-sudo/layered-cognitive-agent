"""认知层测试：摄入模态门控与显著性反思过滤器 (Task 3)。"""

from __future__ import annotations

from lca.cognition.memory.guards.modality import (
    ModalityResult,
    filter_ingestion_modality,
)
from lca.cognition.memory.guards.salience import SalienceGate


def test_hypothetical_examples_and_sarcasm_rejected() -> None:
    # 假设、举例过滤
    assert filter_ingestion_modality("比如你有一个表弟在深圳……") == ModalityResult.HYPOTHETICAL_DROP
    assert filter_ingestion_modality("假设我明年搬去火星住……") == ModalityResult.HYPOTHETICAL_DROP
    assert (
        filter_ingestion_modality("如果我将来买了法拉利，请提醒我买车险")
        == ModalityResult.HYPOTHETICAL_DROP
    )
    assert (
        filter_ingestion_modality("我们来角色扮演，假设你是一个皇帝")
        == ModalityResult.HYPOTHETICAL_DROP
    )
    assert (
        filter_ingestion_modality("举个例子，假如张三欠李四钱") == ModalityResult.HYPOTHETICAL_DROP
    )

    # 反讽反话过滤
    assert (
        filter_ingestion_modality("我最爱天天加班了！（明显反讽）") == ModalityResult.SARCASM_DROP
    )
    assert (
        filter_ingestion_modality("我真是太喜欢天天被老板骂了，才怪！")
        == ModalityResult.SARCASM_DROP
    )

    # 真实事实放行
    assert filter_ingestion_modality("我在长沙买了一套房子") == ModalityResult.ADMIT_FACT
    assert filter_ingestion_modality("我表弟叫小杰，在深圳做程序员") == ModalityResult.ADMIT_FACT
    assert filter_ingestion_modality("全栈使用 Rust 与 Go 进行开发") == ModalityResult.ADMIT_FACT


def test_salience_gate_prevents_over_generalization() -> None:
    gate = SalienceGate()

    # 单次偶发事件不能晋升为 preference (不过度泛化为“户外爱好者”)
    candidate_casual = {
        "category": "preference",
        "content": "用户偏好：户外登山爱好者",
        "confidence": 0.9,
        "dedupe_key": "preference:hobby",
    }
    # 原话只是单次爬山
    verdict = gate.evaluate(
        task="周末跟朋友去爬了一次岳麓山",
        candidate=candidate_casual,
    )
    assert verdict.admitted is False
    assert verdict.reason == "single_casual_action_not_preference"

    # 显式偏好陈述放行
    candidate_explicit = {
        "category": "preference",
        "content": "用户偏好：代码必须有类型标注",
        "confidence": 1.0,
        "dedupe_key": "preference:code_style",
    }
    verdict_explicit = gate.evaluate(
        task="我写代码一贯要求必须有严格的类型标注",
        candidate=candidate_explicit,
    )
    assert verdict_explicit.admitted is True
