"""L1 Brain —— ModularBrain + Reasoner + Critic + Synthesizer。"""

from lca.cognition.brain.critic import SimpleCritic
from lca.cognition.brain.modular_brain import ModularBrain
from lca.cognition.brain.reasoner import PromptReasoner
from lca.cognition.brain.synthesizer import ConcatSynthesizer

__all__ = [
    "ConcatSynthesizer",
    "ModularBrain",
    "PromptReasoner",
    "SimpleCritic",
]
