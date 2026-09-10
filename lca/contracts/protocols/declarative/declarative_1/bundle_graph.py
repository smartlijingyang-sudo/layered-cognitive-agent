"""Bundle Graph Schema v2 — 纯图描述 DTO。

ADR-0217 / Note `docs/notes/implemented/contract/2026-09-10-bundle-graph-schema-v2.md`.

本模块职责:**只定义 bundle 图描述的数据契约**,不解析、不执行、不读 yaml。
- 解析职责:`lca.harness.declarative.compile.subgraph_resolver._compile_bundle_graph`
- 节点执行职责:`NodeExecutor`(本目录下独立模块)
- factory 解析职责:`lca.contracts.protocols.declarative.declarative_1.factory_resolver`

DTO 用 `dataclass(frozen=True, slots=True)`,与同目录 `declarative_fault_tolerance.py` /
`declarative_graph.py` 风格一致。校验通过 `__post_init__`,违反时抛
`DeclarativeValidationError`(PG-005-bundle-graph 错误码)。

yaml 字段 ↔ DTO 字段映射:
  - `from:` / `to:` 在 `BundleGraphEdge.from_kwargs` 入口被规范化到
    `source` / `target`,DTO 自身只暴露 source/target
  - 其它字段保持 1:1
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

from lca.contracts.protocols.declarative.declarative_1.declarative_common import (
    DeclarativeValidationError,
)

BUNDLE_GRAPH_VERSION = "bundle-graph/v1"

EdgeKind = Literal["control", "data"]


@dataclass(frozen=True, slots=True)
class BundleGraphNode:
    """bundle 内单个节点声明。

    字段都对应 yaml 中 `nodes[].<key>`,D5 消费点见 ADR-0217 §2:
      id       : 边 source/target 锚点 + interpreter 寻址 key
      region   : FactoryResolver 反查上下文(可空,fallback 到 BundleGraphSpec.region)
      factory  : 业务语义名,如 `think.reason`;FactoryResolver 解析到 NodeExecutor
      purpose  : 节点职责描述,写入 phase_graph.node.start/end payload(purpose)
      inputs   : 节点声明性输入端口,非空;subgraph 边缘端口对齐用
      outputs  : 节点声明性输出端口,非空;同上
      config   : 节点级图配置,只放图级参数(max_visits / cooldown 等),不向 plugin 注入
    """

    id: str
    region: str | None
    factory: str
    purpose: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise DeclarativeValidationError("PG-005-bundle-graph", "node.id must be non-empty")
        if not self.factory:
            raise DeclarativeValidationError(
                "PG-005-bundle-graph", f"node[{self.id!r}].factory must be non-empty"
            )
        if not self.purpose:
            raise DeclarativeValidationError(
                "PG-005-bundle-graph", f"node[{self.id!r}].purpose must be non-empty"
            )
        if not self.inputs:
            raise DeclarativeValidationError(
                "PG-005-bundle-graph", f"node[{self.id!r}].inputs must be non-empty"
            )
        if not self.outputs:
            raise DeclarativeValidationError(
                "PG-005-bundle-graph", f"node[{self.id!r}].outputs must be non-empty"
            )


@dataclass(frozen=True, slots=True)
class BundleGraphEdge:
    """bundle 内单条边声明。

    字段对应 yaml 中 `edges[].<key>`:
      source  : 起点 node id(必须命中 nodes[].id)
      target  : 终点 node id
      kind    : control(默认,走 when) | data(走端口对齐)
      when    : bool-expr DSL(复用 phase.edge.standard.when)

    yaml `from:` / `to:` 通过 `from_kwargs` 入口归一化,本 DTO 只暴露 source/target。
    """

    source: str
    target: str
    kind: EdgeKind = "control"
    when: str = "true"

    def __post_init__(self) -> None:
        if not self.source:
            raise DeclarativeValidationError("PG-005-bundle-graph", "edge.source must be non-empty")
        if not self.target:
            raise DeclarativeValidationError("PG-005-bundle-graph", "edge.target must be non-empty")
        if self.kind not in ("control", "data"):
            raise DeclarativeValidationError(
                "PG-005-bundle-graph",
                f"edge.kind must be 'control' or 'data', got {self.kind!r}",
            )

    @classmethod
    def from_kwargs(cls, **kwargs: Any) -> "BundleGraphEdge":
        """从 yaml 关键字构造,支持 `from`/`to` 别名 → `source`/`target`。"""
        if "from" in kwargs and "source" not in kwargs:
            kwargs["source"] = kwargs.pop("from")
        if "to" in kwargs and "target" not in kwargs:
            kwargs["target"] = kwargs.pop("to")
        return cls(**kwargs)


@dataclass(frozen=True, slots=True)
class BundleGraphSpec:
    """bundle 整体图描述。"""

    id: str
    region: str | None
    purpose: str | None
    nodes: tuple[BundleGraphNode, ...]
    edges: tuple[BundleGraphEdge, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.id:
            raise DeclarativeValidationError("PG-005-bundle-graph", "bundle.id must be non-empty")
        if not self.nodes:
            raise DeclarativeValidationError("PG-005-bundle-graph", "bundle.nodes must be non-empty")
        # node.id 唯一性
        seen: set[str] = set()
        for n in self.nodes:
            if n.id in seen:
                raise DeclarativeValidationError(
                    "PG-005-bundle-graph",
                    f"duplicate node id {n.id!r} in bundle {self.id!r}",
                )
            seen.add(n.id)
        # edge.source/target 必须命中 node.id
        ids = seen
        for e in self.edges:
            if e.source not in ids:
                raise DeclarativeValidationError(
                    "PG-005-bundle-graph",
                    f"edge.source {e.source!r} not in nodes {sorted(ids)!r}",
                )
            if e.target not in ids:
                raise DeclarativeValidationError(
                    "PG-005-bundle-graph",
                    f"edge.target {e.target!r} not in nodes {sorted(ids)!r}",
                )


# FactoryResolutionError 实际定义在 factory_resolver 模块;此处 re-export
# 保持历史 import 路径 `from ...bundle_graph import FactoryResolutionError` 不破。
from lca.contracts.protocols.declarative.declarative_1.factory_resolver import (  # noqa: E402
    FactoryResolutionError as FactoryResolutionError,
)

__all__ = [
    "BUNDLE_GRAPH_VERSION",
    "BundleGraphEdge",
    "BundleGraphNode",
    "BundleGraphSpec",
    "EdgeKind",
    "FactoryResolutionError",
]
