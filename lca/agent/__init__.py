"""L3 Agent — CognitiveAgent + TeamHandle + TeamStrategy."""

from lca.agent.cognitive_agent import CognitiveAgent
from lca.agent.orchestration_registry import TeamStrategyRegistry
from lca.agent.team_handle import TeamHandle

__all__ = [
    "CognitiveAgent",
    "TeamHandle",
    "TeamStrategyRegistry",
]
