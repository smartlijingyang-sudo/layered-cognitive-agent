"""Build a team_strategies FactoryRegistry from plugin factories (no boot).

Used by strategy unit tests that previously called ``build_default_registries()``.
Production spawn resolves the same factories from the booted plugin tree.
"""

from __future__ import annotations

from lca.contracts.mechanisms.factory_registry import FactoryRegistry
from lca.contracts.models.team.team_coordination import (
    STRATEGY_KEY_DEBATE,
    STRATEGY_KEY_FAN_OUT,
    STRATEGY_KEY_GRAPH,
    STRATEGY_KEY_LEAD,
    STRATEGY_KEY_PEER_RELAY,
    STRATEGY_KEY_PEER_SWARM,
    STRATEGY_KEY_PIPELINE,
)
from lca.plugins.strategies.debate import build_debate_strategy
from lca.plugins.strategies.fan_out import build_fan_out_strategy
from lca.plugins.strategies.graph import build_graph_strategy
from lca.plugins.strategies.lead import build_lead_strategy
from lca.plugins.strategies.peer_relay import build_peer_relay_strategy
from lca.plugins.strategies.peer_swarm import build_peer_swarm_strategy
from lca.plugins.strategies.pipeline import build_pipeline_strategy
from tests.support.graph_node_executors import build_default_graph_node_executor_registry


def build_strategy_registry() -> FactoryRegistry:
    """Fresh FactoryRegistry with all seven strategy factories registered."""
    reg: FactoryRegistry = FactoryRegistry("team_strategies")
    reg.register(STRATEGY_KEY_LEAD, build_lead_strategy)
    reg.register(STRATEGY_KEY_PIPELINE, build_pipeline_strategy)
    reg.register(STRATEGY_KEY_FAN_OUT, build_fan_out_strategy)
    reg.register(STRATEGY_KEY_PEER_RELAY, build_peer_relay_strategy)
    reg.register(STRATEGY_KEY_PEER_SWARM, build_peer_swarm_strategy)
    reg.register(STRATEGY_KEY_DEBATE, build_debate_strategy)
    graph_node_executors = build_default_graph_node_executor_registry()
    reg.register(
        STRATEGY_KEY_GRAPH,
        lambda assembly: build_graph_strategy(assembly, node_executors=graph_node_executors),
    )
    return reg
