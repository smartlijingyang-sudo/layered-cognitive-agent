"""L3 Agent — CognitiveAgent + TeamHandle + TeamStrategy."""

from lca.layer3_agent.cognitive_agent import CognitiveAgent
from lca.layer3_agent.orchestration_registry import TeamStrategyRegistry
from lca.layer3_agent.team_handle import TeamHandle

__all__ = [
    "CognitiveAgent",
    "TeamHandle",
    "TeamStrategyRegistry",
]
