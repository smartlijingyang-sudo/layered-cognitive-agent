"""SpanHandle 行为测试：批量属性写入 + 异常捕获 + Null 句柄安全。"""

from __future__ import annotations

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from lca.layer0_infra.observability import ObservabilityHub, policy
from lca.layer0_infra.observability.handles import NullSpanHandle, SpanHandle


def _make_hub() -> ObservabilityHub:
    return ObservabilityHub(exporters=[InMemorySpanExporter()])


def test_span_handle_uses_set_attributes_batch() -> None:
    """__exit__ 必须单次 set_attributes，而非循环 set_attribute（评估文档 §89）。"""
    hub = _make_hub()
    provider = hub.provider
    tracer = provider.get_tracer("test")
    otel_span = tracer.start_span("test.span")

    batch_calls: list[dict] = []

    real_set_attribute = otel_span.set_attribute
    real_set_attributes = otel_span.set_attributes

    def tracking_set_attribute(key: str, value: object) -> None:
        batch_calls.append({"op": "set_attribute", "key": key})
        real_set_attribute(key, value)

    def tracking_set_attributes(attrs: dict) -> None:
        batch_calls.append({"op": "set_attributes", "size": len(attrs)})
        real_set_attributes(attrs)

    otel_span.set_attribute = tracking_set_attribute  # type: ignore[method-assign]
    otel_span.set_attributes = tracking_set_attributes  # type: ignore[method-assign]

    handle = SpanHandle(hub, otel_span, {"a": 1, "b": "two", "c": True})
    handle.__exit__(None, None, None)

    set_attr_ops = [c for c in batch_calls if c["op"] == "set_attribute"]
    set_attrs_ops = [c for c in batch_calls if c["op"] == "set_attributes"]
    assert not set_attr_ops, f"__exit__ 必须批量写入，但发现 {len(set_attr_ops)} 次 set_attribute"
    assert len(set_attrs_ops) == 1, f"__exit__ 应只调用一次 set_attributes，实际 {len(set_attrs_ops)}"
    assert set_attrs_ops[0]["size"] >= 3


def test_span_handle_records_exception_on_exit() -> None:
    hub = _make_hub()
    tracer = hub.provider.get_tracer("test")
    otel_span = tracer.start_span("test.err")
    handle = SpanHandle(hub, otel_span, {"step": 1})
    try:
        raise ValueError("boom")
    except ValueError as exc:
        handle.__exit__(type(exc), exc, exc.__traceback__)

    assert otel_span.attributes is not None
    attrs = dict(otel_span.attributes)
    assert attrs["error_type"] == "ValueError"
    assert attrs["error_message"].startswith("boom")
    status = otel_span.status
    from opentelemetry.trace import StatusCode

    assert status.status_code is StatusCode.ERROR


def test_span_handle_mark_error_sets_status_and_attribute() -> None:
    hub = _make_hub()
    tracer = hub.provider.get_tracer("test")
    otel_span = tracer.start_span("test.manual")
    handle = SpanHandle(hub, otel_span, {})
    handle.mark_error("manual fail")
    from opentelemetry.trace import StatusCode

    assert otel_span.status.status_code is StatusCode.ERROR
    assert handle.attributes.get("error_message") == "manual fail"


def test_null_span_handle_safe_no_op() -> None:
    handle = NullSpanHandle()
    with handle as h:
        h.attributes["x"] = 1
        h.mark_error("ignored")
    # 不抛、不挂属性、不报错
    assert handle.attributes["x"] == 1


def test_attribute_policy_is_applied_at_exit() -> None:
    """策略只在 __exit__ 时跑一次；中间写入不重复过 policy。"""
    hub = _make_hub()
    policy_sentinel = policy.AttributePolicy(verbosity=policy.Verbosity.MINIMAL, redact=True)
    hub_orig_policy = hub.policy
    try:
        hub._policy = policy_sentinel  # type: ignore[attr-defined]
        tracer = hub.provider.get_tracer("test")
        otel_span = tracer.start_span("test.policy")
        handle = SpanHandle(hub, otel_span, {"prompt_preview": "hello world", "plain": "x"})
        handle.__exit__(None, None, None)
        # minimal verbosity 把 prompt_preview 删掉
        attrs = dict(otel_span.attributes) if otel_span.attributes else {}
        assert "prompt_preview" not in attrs
        assert attrs.get("plain") == "x"
    finally:
        hub._policy = hub_orig_policy  # type: ignore[attr-defined]