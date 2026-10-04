"""Carrier-plane + kernel.run spine EP emission contract (ADR-0166 S4).

``lca/loop/transport.py`` 的 6 个 helper 是薄包装：唯一的职责是把调用参数
塑造成 ``publish_spine_ep`` 的 (execution_point, payload, channel, actor)。
本文件在 seam 层钉住：

1. 6 个 EP 字符串全部在 ``_SPINE_EP_TO_CATEGORY`` 注册（否则真实调用在
   ``publish_spine_ep`` 内 KeyError，事件发不出去）。
2. 每个 helper 传给 ``publish_spine_ep`` 的 EP 字面量 + payload 形状 +
   channel="control" + actor="transport"。
3. 可选字段语义：``carrier_seq=None`` 时不出现在 payload；
   ``outcome`` 默认 "success"；``emit_kernel_run_cancelled`` 强制
   outcome="cancelled"（不可参数化）。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

from lca.loop import transport as loop_transport

_EXPECTED_EPS = (
    "transport.route.enter",
    "transport.route.exit",
    "transport.sse.publish",
    "kernel.run.start",
    "kernel.run.stop",
    "kernel.run.cancelled",
)


def _patch_spine(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_publish(
        execution_point: str,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        captured["execution_point"] = execution_point
        captured["payload"] = payload
        captured["kwargs"] = kwargs
        return None

    monkeypatch.setattr(loop_transport, "publish_spine_ep", fake_publish)
    return captured


def test_all_six_eps_registered_in_category_map() -> None:
    from lca_kernel.events.payloads.spine import _SPINE_EP_TO_CATEGORY

    for ep in _EXPECTED_EPS:
        assert ep in _SPINE_EP_TO_CATEGORY, f"{ep} not registered; publish would KeyError"


def test_route_enter_payload_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_spine(monkeypatch)
    loop_transport.emit_transport_route_enter(path="/v1/runs", method="POST", run_id="r1")
    assert captured["execution_point"] == "transport.route.enter"
    assert captured["payload"] == {"path": "/v1/runs", "method": "POST", "run_id": "r1"}
    assert "carrier_seq" not in captured["payload"]
    assert captured["kwargs"]["channel"] == "control"
    assert captured["kwargs"]["actor"] == "transport"


def test_route_enter_carries_carrier_seq_when_given(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_spine(monkeypatch)
    loop_transport.emit_transport_route_enter(
        path="/v1/runs", method="POST", run_id=None, carrier_seq=41
    )
    assert captured["payload"]["carrier_seq"] == 41
    # run_id=None 归一为空串，不传 None 下游
    assert captured["payload"]["run_id"] == ""


def test_route_exit_defaults_and_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_spine(monkeypatch)
    loop_transport.emit_transport_route_exit(path="/v1/runs", method="GET")
    assert captured["execution_point"] == "transport.route.exit"
    assert captured["payload"]["outcome"] == "success"
    assert captured["payload"]["run_id"] == ""

    loop_transport.emit_transport_route_exit(
        path="/v1/runs", method="GET", outcome="error", carrier_seq=7
    )
    assert captured["payload"]["outcome"] == "error"
    assert captured["payload"]["carrier_seq"] == 7


def test_sse_publish_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_spine(monkeypatch)
    loop_transport.emit_transport_sse_publish(path="/v1/events", run_id="r9")
    assert captured["execution_point"] == "transport.sse.publish"
    assert captured["payload"] == {"path": "/v1/events", "run_id": "r9"}
    assert captured["kwargs"]["channel"] == "control"
    assert captured["kwargs"]["actor"] == "transport"


def test_kernel_run_start_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_spine(monkeypatch)
    loop_transport.emit_kernel_run_start(run_id="k1", trace_id="t1")
    assert captured["execution_point"] == "kernel.run.start"
    assert captured["payload"] == {"run_id": "k1", "trace_id": "t1"}
    assert captured["kwargs"]["actor"] == "transport"


def test_kernel_run_stop_defaults_and_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_spine(monkeypatch)
    loop_transport.emit_kernel_run_stop(run_id="k2")
    assert captured["execution_point"] == "kernel.run.stop"
    assert captured["payload"] == {"run_id": "k2", "trace_id": "", "outcome": "success"}


def test_kernel_run_cancelled_forces_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_spine(monkeypatch)
    loop_transport.emit_kernel_run_cancelled(run_id="k3", trace_id="t3")
    assert captured["execution_point"] == "kernel.run.cancelled"
    assert captured["payload"]["outcome"] == "cancelled"
    assert captured["payload"] == {"run_id": "k3", "trace_id": "t3", "outcome": "cancelled"}
