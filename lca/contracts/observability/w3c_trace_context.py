"""W3C Trace Context 契约 —— ADR-0065 §八 / PR-7。

W3C `traceparent` (RFC) + `tracestate` 解析与校验契约。**入站上下文必须视为
不可信数据**:格式 / 长度 / 来源 / 隐私都要过;通过后只作为 ``causation.links``
中的 ``external_trace_id``,不得覆盖 LCA 的 ``trace_id`` / ``run_id`` / ``run_seq``
或授权身份(0065 §八)。

`traceparent`(RFC 0000):

    <version>-<trace-id 32hex>-<span-id 16hex>-<flags 2hex>

`tracestate`:

    k1=v1,k2=v2  # k: [a-z][a-z0-9_-]{0,15}; v: [!-~]+

隐私:`tracestate` 中含 `tenant_id=` / `user_id=` / `email=` / `password=` 等
明确拒绝;含 `o=`(tenant)走 policy。

实现位置:``lca/layer0_infra/observability/w3c_validator.py:DefaultW3CValidator``。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class TraceparentParts:
    """``traceparent`` 解析结果。"""

    version: str
    trace_id: str
    span_id: str
    flags: str


@dataclass(frozen=True, slots=True)
class W3CValidationResult:
    """``W3CValidator`` 校验结果。"""

    valid: bool
    traceparent: TraceparentParts | None = None
    tracestate: Mapping[str, str] = field(default_factory=dict)
    rejected_reason: str = ""

    @classmethod
    def reject(cls, reason: str) -> W3CValidationResult:
        return cls(valid=False, rejected_reason=reason)


@runtime_checkable
class W3CTraceContextValidator(Protocol):
    """W3C trace context 不可信入站校验(0065 §八)。"""

    def parse_traceparent(self, raw: str) -> TraceparentParts | None:
        """解析 + 校验 ``traceparent``;格式错误返回 None。"""

    def parse_tracestate(self, raw: str) -> Mapping[str, str]:
        """解析 ``tracestate`` 键值对;非法键值跳过,合法保留。"""

    def validate(self, *, traceparent: str | None, tracestate: str | None) -> W3CValidationResult:
        """综合校验;返回 W3CValidationResult。"""


__all__ = ["TraceparentParts", "W3CTraceContextValidator", "W3CValidationResult"]
