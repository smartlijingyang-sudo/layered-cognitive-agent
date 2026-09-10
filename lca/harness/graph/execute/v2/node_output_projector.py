"""NodeOutput → PhaseResult 投影 (ADR-0218 §3.2 Adapter)。

职责:**只**做 NodeOutput 到 PhaseResult 的无脑映射。
- 不做业务判断,不做 if 分支(除 None 兜底)
- yaml `node.config.result_kind` / `payload_port` 决定映射规则
- 产出 PhaseResult 喂老 DSL 评估 `edges[].when`(DSL 不动)

D5 消费点:NodeGraphDriver.run() 主循环每轮调一次。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from lca.contracts.protocols.declarative.declarative_1.declarative_execution import (
    PhaseResult,
)
from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeOutput,
)


@dataclass(frozen=True, slots=True)
class NodeOutputSchema:
    """yaml `node.config` 投影:NodeOutput → PhaseResult 的映射规则。

    字段:
      result_kind:PhaseResult.result_kind(DSL 评估 stage/decision/failed 区分)。
        默认 `think_stage`,与老 PhaseExecutor 默认对齐。
      payload_port:NodeOutput.port_values 中哪个 key 映射到 PhaseResult.payload。
        缺省 = None → 整个 port_values 不映射(PhaseResult.payload = None)。
    """

    result_kind: str = "think_stage"
    payload_port: str | None = None


def project_node_output(
    node_output: NodeOutput,
    schema: NodeOutputSchema,
) -> PhaseResult:
    """NodeOutput → PhaseResult 投影(无脑映射,无业务分支)。

    D5 消费:interpreter DSL 评估 edges[].when 时的 `result` 字段。

    边界:
    - 不调 executor,不读 yaml,不感知 outer state
    - `payload_port` 不在 port_values 里 → payload=None(显式 None,不等同于"未命中")
    - `next_hint` 投影到 `PhaseResult.next_hints["next_hint"]` — DSL 可读
    """
    payload: object | None = None
    if schema.payload_port is not None:
        payload = node_output.port_values.get(schema.payload_port)

    next_hints: dict[str, object] = {}
    if node_output.next_hint is not None:
        next_hints["next_hint"] = node_output.next_hint

    return PhaseResult(
        result_kind=schema.result_kind,
        payload=payload,
        next_hints=next_hints,
    )


def schema_from_node_config(config: Mapping[str, object]) -> NodeOutputSchema:
    """从 yaml `node.config` 抽 NodeOutputSchema。

    字段读取优先级:
      result_kind  ← config["result_kind"] | config.get("result_kind", "think_stage")
      payload_port ← config["payload_port"] | None
    """
    result_kind_raw = config.get("result_kind", "think_stage")
    result_kind = str(result_kind_raw) if result_kind_raw is not None else "think_stage"
    payload_port_raw = config.get("payload_port")
    payload_port = str(payload_port_raw) if payload_port_raw is not None else None
    return NodeOutputSchema(result_kind=result_kind, payload_port=payload_port)


__all__ = [
    "NodeOutputSchema",
    "project_node_output",
    "schema_from_node_config",
]
