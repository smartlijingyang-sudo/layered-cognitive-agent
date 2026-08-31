"""W3C trace context validator 测试(ADR-0065 §八 / PR-7)。

- 合法 traceparent 解析成功
- 格式非法返回 None / reject
- tracestate 隐私字段拒绝
- 长度超限拒绝
- 空 / 缺失 traceparent reject
- 多个 tracestate key 中,合法 + 非法混合,非法被过滤
"""

from __future__ import annotations

import pytest

from lca.contracts.observability.w3c_trace_context import (
    TraceparentParts,
)
from lca.infrastructure.observability.events.w3c_validator import DefaultW3CValidator


@pytest.fixture
def validator() -> DefaultW3CValidator:
    return DefaultW3CValidator()


def test_valid_traceparent_parses(validator: DefaultW3CValidator) -> None:
    raw = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    parts = validator.parse_traceparent(raw)
    assert parts is not None
    assert isinstance(parts, TraceparentParts)
    assert parts.trace_id == "0af7651916cd43dd8448eb211c80319c"
    assert parts.span_id == "b7ad6b7169203331"


def test_invalid_traceparent_format_returns_none(validator: DefaultW3CValidator) -> None:
    assert validator.parse_traceparent("not-a-traceparent") is None
    assert validator.parse_traceparent("00-xyz") is None
    assert validator.parse_traceparent("00-0af7651916cd43dd8448eb211c80319c-xyz-01") is None


def test_traceparent_too_long_rejected(validator: DefaultW3CValidator) -> None:
    assert validator.parse_traceparent("00-" + "a" * 1000) is None


def test_empty_traceparent_rejected(validator: DefaultW3CValidator) -> None:
    assert validator.parse_traceparent("") is None


def test_version_must_be_00_or_01(validator: DefaultW3CValidator) -> None:
    assert (
        validator.parse_traceparent("99-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01")
        is None
    )


def test_tracestate_parses_kv_pairs(validator: DefaultW3CValidator) -> None:
    raw = "k1=v1,k2=v2"
    parsed = validator.parse_tracestate(raw)
    assert parsed == {"k1": "v1", "k2": "v2"}


def test_tracestate_rejects_privacy_keys(validator: DefaultW3CValidator) -> None:
    """tenant_id / user_id / email / password 等敏感键整段拒绝。"""
    parsed = validator.parse_tracestate("tenant_id=acme")
    assert parsed == {}
    parsed = validator.parse_tracestate("user_id=alice")
    assert parsed == {}
    parsed = validator.parse_tracestate("password=hunter2")
    assert parsed == {}


def test_tracestate_filters_invalid_keys(validator: DefaultW3CValidator) -> None:
    """非法 key / value 被过滤,合法保留。

    RFC k = [a-z][a-z0-9_-]{0,15};起始大写 / 数字 / 长度超限都是非法。
    RFC v = [!-~]+(可打印 ASCII,不含 ',' ';' 分隔符)。
    """
    raw = "k1=v1,KEY=val,123=val,thisisaverylongkey123=v,k3=val with space,k4=v4"
    parsed = validator.parse_tracestate(raw)
    assert "k1" in parsed
    assert "KEY" not in parsed  # 起始大写非法
    assert "123" not in parsed  # 起始数字非法
    assert "thisisaverylongkey123" not in parsed  # 长度超 16
    assert "k3" not in parsed  # value 含空格非法
    assert "k4" in parsed


def test_tracestate_too_long_rejected(validator: DefaultW3CValidator) -> None:
    assert validator.parse_tracestate("a" * 1000) == {}


def test_validate_combined_success(validator: DefaultW3CValidator) -> None:
    raw = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    result = validator.validate(traceparent=raw, tracestate="k1=v1")
    assert result.valid is True
    assert result.traceparent is not None
    assert result.tracestate == {"k1": "v1"}


def test_validate_combined_reject(validator: DefaultW3CValidator) -> None:
    result = validator.validate(traceparent=None, tracestate=None)
    assert result.valid is False
    assert result.rejected_reason == "traceparent missing"


def test_validate_combined_format_invalid(validator: DefaultW3CValidator) -> None:
    result = validator.validate(traceparent="garbage", tracestate=None)
    assert result.valid is False
    assert "traceparent format invalid" in result.rejected_reason


def test_validate_combined_privacy_re_rejects(validator: DefaultW3CValidator) -> None:
    """tracestate 隐私字段不导致 valid=False;只是空 dict。"""
    raw = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    result = validator.validate(traceparent=raw, tracestate="tenant_id=acme")
    # tracestate 整段拒绝 → 空 dict;traceparent 仍合法 → valid=True
    assert result.valid is True
    assert result.tracestate == {}
