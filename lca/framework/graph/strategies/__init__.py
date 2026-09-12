"""Strategy implementations for the unified graph kernel.

Each module registers one :class:`NodeStrategy` subclass against the
default :class:`StrategyRegistry` at import time. The kernel resolves
strategies by binding kind; strategies themselves are stateless.
"""
from lca.framework.graph.strategies.agent_consult_strategy import AgentConsultStrategy
from lca.framework.graph.strategies.agent_fanout_strategy import AgentFanoutStrategy
from lca.framework.graph.strategies.gate_chain_strategy import GateChainStrategy
from lca.framework.graph.strategies.node_executor_strategy import NodeExecutorStrategy
from lca.framework.graph.strategies.observe_strategy import ObserveStrategy
from lca.framework.graph.strategies.parallel_strategy import ParallelStrategy
from lca.framework.graph.strategies.subgraph_strategy import SubgraphStrategy
from lca.framework.graph.strategies.terminate_strategy import TerminateStrategy
from lca.framework.graph.strategies.transform_strategy import (
    TransformStrategy,
    identity_transform,
)

__all__ = [
    "AgentConsultStrategy",
    "AgentFanoutStrategy",
    "GateChainStrategy",
    "NodeExecutorStrategy",
    "ObserveStrategy",
    "ParallelStrategy",
    "SubgraphStrategy",
    "TerminateStrategy",
    "TransformStrategy",
    "identity_transform",
]
