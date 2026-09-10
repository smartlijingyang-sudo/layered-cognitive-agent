"""跨节点 port 上下文(ADR-0218 §3.5 内部数据结构)。

职责:**只**保存节点间共享的 port_values,提供 input 投影。
- 不感知 NodeExecutor / PhaseResult
- 不调 factory / scope

D5 消费点:NodeGraphDriver.run() 主循环每轮节点前查 / 节点后写。

边界:
- 内部 dict,不导出
- merge:dict.update,key 冲突后写覆盖前(outer input 优先于前节点 output)
"""

from __future__ import annotations

from typing import Any, Mapping

from lca.contracts.protocols.declarative.declarative_1.node_executor import (
    NodeInput,
)


class PortContext:
    """节点间 port 共享上下文。

    - ``set_outer_input(ports)``:outer drive 传入的初始 input(若有)
    - ``merge_output(node_id, port_values)``:节点跑完后 merge 进 context
    - ``build_input(node_id, declared_ports)``:节点跑前,从 context 抽 declared_ports
      构造 NodeInput(缺则填空 dict)

    缺省策略:缺 port 不报错,填空 dict;plugin 自己处理空值。
    """

    __slots__ = ("_ports",)

    def __init__(self) -> None:
        self._ports: dict[str, Any] = {}

    def set_outer_input(self, ports: Mapping[str, Any]) -> None:
        """outer drive 传入的初始 input,key 直接进 context。"""
        self._ports.update(dict(ports))

    def merge_output(self, port_values: Mapping[str, Any]) -> None:
        """节点 output merge 进 context(outer input 优先,不覆盖)。"""
        for k, v in port_values.items():
            self._ports.setdefault(k, v)

    def build_input(self, declared_ports: tuple[str, ...]) -> NodeInput:
        """从 context 抽 declared_ports 构造 NodeInput。"""
        port_values = {p: self._ports.get(p) for p in declared_ports}
        return NodeInput(port_values=port_values)


__all__ = ["PortContext"]
