"""委派目标解析的唯一入口。

该模块只负责把 ``DelegationSpec`` 解析为传输端口和目标身份，
不参与超时计算、消息发送或结果编排。这样 DelegateOperation 与
HandoffOperation 共享同一套目标选择语义，动作模块只保留各自的
执行职责。
"""

from __future__ import annotations

from lca.contracts.models.core.decision import DelegationSpec
from lca.contracts.models.core.lifecycle import AgentCard
from lca.contracts.models.core.result import ToolExecutionError
from lca.contracts.protocols import AgentTransport, TransportRegistryProtocol


def resolve_delegation_target(
    spec: DelegationSpec,
    transport_registry: TransportRegistryProtocol,
) -> tuple[AgentTransport, AgentCard | str]:
    """解析委派协议与目标身份；目标缺失时返回领域错误。"""
    transport = transport_registry.resolve(spec.protocol)
    agent_card: AgentCard | str | None = (
        spec.target_agent_card or spec.target_agent_id or spec.target_role
    )
    if agent_card is None:
        raise ToolExecutionError("委派动作缺少目标（agent_card / agent_id / role 均为空）")
    return transport, agent_card
