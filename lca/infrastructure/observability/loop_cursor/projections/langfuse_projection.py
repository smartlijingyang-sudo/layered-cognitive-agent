"""Langfuse LLM-as-judge 出口 — LoopProjectionDefinition 实现(ADR-0172 D1)。

按 step 评分(score)。**若 langfuse SDK 未安装,本出口降级为 no-op
accumulator**:不在 import 时崩溃,apply 仍然累加最小 score 描述符到
内部 state;view 返回该列表;host 可在外部 flush 时落盘或决定是否
仅在 SDK 可用时上传。

设计要点:
- try/except ImportError 在模块级进行;``_LANGFUSE_AVAILABLE`` 标志。
- reducer state 是 dict[str, Any](``{"scores": list[dict[str, Any]]}``)。
- 凭证严禁通过 ``os.environ`` 直接读(ADR-0172 D5);``LangfuseProjection``
  仅持有可选 ``_client`` 引用,由 ``register_default_exporters`` 注入。
"""

from __future__ import annotations

from typing import Any

from lca.contracts.observability.loop_cursor import CursorSnapshot
from lca.infrastructure.observability.spine.event_record import EventRecord

# llm.request.header payload 字段(ADR-0168.1 §D4 RequestHeader)
_FIELD_STEP_ID = "step_id"
_FIELD_MODEL = "model"

# Langfuse SDK 可选 import(ADR-0172 D5)
try:
    from langfuse import Langfuse as _LangfuseClient  # type: ignore[import-not-found]

    _LANGFUSE_AVAILABLE = True
except ImportError:  # pragma: no cover - 由缺失依赖触发
    _LangfuseClient = None  # type: ignore[assignment]
    _LANGFUSE_AVAILABLE = False


class LangfuseProjection:
    """Langfuse evaluator — scores each step。

    apply 在每次 ``llm.request.header`` 时累加一条 score 描述符;
    reducer 阶段纯函数,真正的 SDK 上传由 view() 返回后由 host / 上层
    触发(由配置控制是否实际 flush 到 Langfuse API)。
    """

    key: str = "langfuse"
    version: int = 1

    def __init__(self, client: Any | None = None) -> None:
        """允许外部注入 client(profile YAML 解析期);缺省 = no-op。"""
        self._client = client if client is not None else _LangfuseClient

    def init(self) -> dict[str, Any]:
        """Seed state: scores 列表 + sdk_available flag。"""
        return {"scores": [], "sdk_available": _LANGFUSE_AVAILABLE}

    def apply(
        self,
        state: dict[str, Any],
        snapshot: CursorSnapshot,
        record: EventRecord,
    ) -> dict[str, Any]:
        """每条 ``llm.request.header`` 累加一条 score。"""
        if record.execution_point != "llm.request.header":
            return state
        scores = list(state.get("scores", []))
        payload = record.payload if isinstance(record.payload, dict) else {}
        scores.append(
            {
                "step_id": payload.get(_FIELD_STEP_ID) or snapshot.step_id,
                "model": payload.get(_FIELD_MODEL),
                "sequence": record.sequence,
                "score": None,  # 由 view/flush 阶段填入(LLM-as-judge)
            }
        )
        return {
            "scores": scores,
            "sdk_available": state.get("sdk_available", _LANGFUSE_AVAILABLE),
        }

    def view(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        """返回 scores 列表。"""
        return list(state.get("scores", []))

    def restore(self, state: dict[str, Any]) -> dict[str, Any]:
        """Checkpoint replay 入口;重置 scores。"""
        return {"scores": [], "sdk_available": _LANGFUSE_AVAILABLE}


__all__ = ["LangfuseProjection"]


def langfuse_sdk_available() -> bool:
    """返回 langfuse SDK 是否可用(测试 seam)。"""
    return _LANGFUSE_AVAILABLE
