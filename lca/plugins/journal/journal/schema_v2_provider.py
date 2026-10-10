"""schema-v2.0.0 provider —— ADR-0096 MVA-1.

实现已下沉 ``lca.contracts.observability.schemas.envelope_v2_schema``；
本模块为兼容 re-export（既有测试引用此路径）。
"""

from __future__ import annotations

from lca.contracts.observability.schemas.envelope_v2_schema import (
    EnvelopeV2Schema as EnvelopeV2Schema,
)

__all__ = ["EnvelopeV2Schema"]
