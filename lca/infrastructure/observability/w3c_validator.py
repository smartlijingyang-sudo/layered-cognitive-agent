"""DefaultW3CValidator —— ADR-0065 §八 / PR-7 默认实现。

格式校验 + 隐私字段拒绝。
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from lca.contracts.observability.w3c_trace_context import (
    TraceparentParts,
    W3CTraceContextValidator,
    W3CValidationResult,
)

# W3C RFC: k = [a-z][a-z0-9_-]{0,15}
_TRACESTATE_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,15}$")
# RFC: v = [!-~]+,不含 ',' ';' (这两个是分隔符)
_TRACESTATE_VALUE_RE = re.compile(r"^[!-~]+$")
# RFC: 32 hex chars
_HEX_32_RE = re.compile(r"^[0-9a-f]{32}$")
# RFC: 16 hex chars
_HEX_16_RE = re.compile(r"^[0-9a-f]{16}$")
# RFC: 2 hex chars
_HEX_2_RE = re.compile(r"^[0-9a-f]{2}$")
# 版本号:00 / 01
_VERSION_RE = re.compile(r"^0[01]$")

_MAX_TRACEPARENT_LEN = 256
_MAX_TRACESTATE_LEN = 512

# 隐私字段 — 含这些 key 的 tracestate 整段拒绝
_PRIVACY_KEYS = frozenset(
    {
        "tenant_id",
        "user_id",
        "email",
        "password",
        "secret",
        "token",
        "authorization",
    }
)


class DefaultW3CValidator(W3CTraceContextValidator):
    """W3C 入站不可信校验默认实现。"""

    def parse_traceparent(self, raw: str) -> TraceparentParts | None:
        if not raw or len(raw) > _MAX_TRACEPARENT_LEN:
            return None
        parts = raw.split("-")
        if len(parts) != 4:
            return None
        version, trace_id, span_id, flags = parts
        if not _VERSION_RE.match(version):
            return None
        if not _HEX_32_RE.match(trace_id):
            return None
        if not _HEX_16_RE.match(span_id):
            return None
        if not _HEX_2_RE.match(flags):
            return None
        return TraceparentParts(
            version=version,
            trace_id=trace_id,
            span_id=span_id,
            flags=flags,
        )

    def parse_tracestate(self, raw: str) -> Mapping[str, str]:
        if not raw or len(raw) > _MAX_TRACESTATE_LEN:
            return {}
        result: dict[str, str] = {}
        for pair in raw.split(","):
            if not pair.strip():
                continue
            if "=" not in pair:
                continue
            key, _, value = pair.partition("=")
            key = key.strip()
            value = value.strip()
            if key in _PRIVACY_KEYS:
                # 隐私字段 — 整段拒绝;返回空标记给上层
                return {}
            if not _TRACESTATE_KEY_RE.match(key):
                continue
            if not _TRACESTATE_VALUE_RE.match(value):
                continue
            result[key] = value
        return result

    def validate(self, *, traceparent: str | None, tracestate: str | None) -> W3CValidationResult:
        if traceparent is None:
            return W3CValidationResult.reject("traceparent missing")
        parts = self.parse_traceparent(traceparent)
        if parts is None:
            return W3CValidationResult.reject("traceparent format invalid")
        state = self.parse_tracestate(tracestate or "")
        return W3CValidationResult(
            valid=True,
            traceparent=parts,
            tracestate=state,
        )


__all__ = ["DefaultW3CValidator"]
