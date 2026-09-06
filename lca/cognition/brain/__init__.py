"""L1 Brain —— ModularBrain + Reasoner + Critic + Synthesizer。"""

from lca.cognition.brain.pipeline.modular_brain import ModularBrain
from lca.cognition.brain.reasoner.critic import SimpleCritic
from lca.cognition.brain.reasoner.reasoner import PromptReasoner
from lca.cognition.brain.reasoner.synthesizer import ConcatSynthesizer

__all__ = [
    "ConcatSynthesizer",
    "ModularBrain",
    "PromptReasoner",
    "SimpleCritic",
]
