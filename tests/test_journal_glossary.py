"""Glossary 健全性 —— 确保每条事件类型都有准确 / 全面 / 不误导的中文说明。"""

from __future__ import annotations

import pytest

from lca.contracts.models.observability.event import (
    EventAudience,
    EventSensitivity,
)
from lca.contracts.models.observability.journal_catalog import JOURNAL_EVENT_CLASSES
from lca.infrastructure.observability.event_descriptors_data import build_default_registry
from lca.infrastructure.observability.event_doc import (
    EVENT_DOCS,
    EventDoc,
    doc_for,
    register_doc,
)


def _infer_layer(emitter: str) -> str:
    """Layer 推导与 ``event_doc.py`` 内置词表保持一致。"""
    if emitter.startswith("gateway."):
        return "gateway"
    if emitter.startswith("lca.infrastructure."):
        return "L0"
    if emitter.startswith("lca.cognition."):
        return "L1"
    if emitter.startswith("lca.runtime."):
        return "L2"
    if emitter.startswith("lca.agent."):
        return "L3"
    if (
        emitter.startswith("lca.application.")
        or emitter.startswith("lca.harness.")
        or emitter.startswith("lca.plugins.")
    ):
        return "L4"
    return f"?({emitter})"


def test_glossary_covers_every_catalog_event() -> None:
    """catalog 里 47 个事件类型,glossary 必须全覆盖。"""
    catalog = set(JOURNAL_EVENT_CLASSES.keys())
    documented = set(EVENT_DOCS.keys())
    missing = catalog - documented
    extra = documented - catalog
    assert not missing, f"events without Chinese doc: {sorted(missing)}"
    assert not extra, f"doc entries not in catalog: {sorted(extra)}"
    assert len(catalog) == 47


@pytest.mark.parametrize("event_type", sorted(JOURNAL_EVENT_CLASSES.keys()))
def test_each_doc_has_four_non_empty_fields(event_type: str) -> None:
    """summary / why / arch / layer 都必须有非空中文内容。"""
    doc = doc_for(event_type)
    assert doc is not None, f"no doc for {event_type}"
    assert isinstance(doc, EventDoc)
    for field_name in ("summary", "why", "arch", "layer"):
        value = getattr(doc, field_name)
        assert isinstance(value, str) and value.strip(), f"{event_type}.{field_name} 为空"


def test_runtime_observed_layer_admits_multi_layer() -> None:
    """RuntimeObserved 由任一层发射,layer 字段允许 'L0..L4' 这种区间表达。"""
    doc = doc_for("RuntimeObserved")
    assert doc is not None
    assert "L0" in doc.layer and "L4" in doc.layer


@pytest.mark.parametrize(
    "event_type",
    sorted(JOURNAL_EVENT_CLASSES.keys() - {"RuntimeObserved"}),
)
def test_layer_matches_descriptor_emitter(event_type: str) -> None:
    """非 RuntimeObserved 的 layer 字段必须与 emitter 前缀一致。"""
    reg = build_default_registry()
    target = next(
        d
        for d in reg.all()
        if d.payload_class is not None and d.payload_class.__name__ == event_type
    )
    expected = _infer_layer(target.emitter)
    actual = doc_for(event_type).layer
    assert actual == expected, (
        f"{event_type}: glossary layer={actual!r}, emitter {target.emitter!r} → {expected!r}"
    )


def test_summary_does_not_contradict_required_fields() -> None:
    """summary 不许声称有 X 字段,而 descriptor.required 不要求 X(避免误导)。"""
    reg = build_default_registry()
    by_name = {d.payload_class.__name__: d for d in reg.all() if d.payload_class is not None}
    for name, doc in EVENT_DOCS.items():
        if name not in by_name:
            continue
        required = set(by_name[name].required)
        # 已知对照表:doc 中明确提到的字段,要么 required 要么允许"可选"
        # 这条是弱检查:仅验证没有"必须 ... 才能用"这种反向误导。
        for field in required:
            assert "必须填" not in doc.summary or field in doc.summary, (
                f"{name} 声称 summary 含 '必须' 但 required 字段 {field} 未在 summary 中提及"
            )


def test_register_doc_rejects_duplicates() -> None:
    """同一 event_type 重复登记必须报错(避免悄无声息覆盖)。"""
    with pytest.raises(ValueError, match="already registered"):
        register_doc(
            "InboxFollowupCreated",
            EventDoc("dup", "dup", "dup", "L4"),
        )


def test_doc_for_unknown_type_returns_none() -> None:
    assert doc_for("DefinitelyNotARealEvent") is None
    # 完全空字符串 / None 也安全
    assert doc_for("") is None


def test_sensitive_events_are_marked_in_summary() -> None:
    """confidential 敏感级别事件,doc 必须显式提醒(避免新手无意中泄漏)。"""
    reg = build_default_registry()
    confidential = {
        d.payload_class.__name__
        for d in reg.all()
        if d.payload_class is not None and d.sensitivity is EventSensitivity.CONFIDENTIAL
    }
    for name in confidential:
        doc = doc_for(name)
        assert doc is not None
        # confidential 事件必须在 arch / why / layer 中带 'restricted' 或 'confidential'
        # 关键词,避免 doc 误把它当 public 描述
        joined = doc.arch + doc.why + doc.layer
        assert "restricted" in joined or "confidential" in joined, (
            f"{name} 是 confidential,doc 未提及 restricted / confidential"
        )


def test_end_user_events_have_user_facing_arch_note() -> None:
    """end_user audience 事件 doc 必须含 '前端' / '用户' 等可视化关键词。"""
    reg = build_default_registry()
    end_user = {
        d.payload_class.__name__
        for d in reg.all()
        if d.payload_class is not None and d.audience is EventAudience.END_USER
    }
    for name in end_user:
        doc = doc_for(name)
        assert doc is not None
        joined = doc.summary + doc.why
        assert "前端" in joined or "用户" in joined or "UI" in joined, (
            f"{name} 是 end_user,doc 未解释给用户看"
        )
