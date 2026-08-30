"""EnvelopeV2 + JournalSchema Protocol —— ADR-0096 §5.1.

EnvelopeV2 = ``lca.journal/2`` envelope 的 Pydantic v2 表示,
所有字段显式类型化,``schema_version`` 必填(I2 不变量)。
"""

from __future__ import annotations

from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict

from lca.contracts.models.observability.journal import JournalRecord

SCHEMA_VERSION: Literal["v2.0.0"] = "v2.0.0"


class EnvelopeV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["v2.0.0"]
    event_id: str
    trace_id: str
    run_id: str
    run_seq: int
    plan_ref: str = ""
    occurred_at: float
    descriptor: dict[str, Any]
    payload: dict[str, Any]  # ADR §5.1: 字段名从 data → payload
    scope: dict[str, Any] = {}
    causation: dict[str, Any] = {}
    evidence: list[dict[str, Any]] = []


class JournalSchema(Protocol):
    """Seam contract: 一个 envelope schema 实现。"""

    version: str

    def serialize(self, record: JournalRecord) -> dict[str, Any]: ...

    def deserialize(self, data: dict[str, Any]) -> JournalRecord: ...
