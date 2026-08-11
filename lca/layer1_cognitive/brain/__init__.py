"""L1 Brain —— ModularBrain + Reasoner + Critic + Synthesizer。"""

from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import PromptReasoner
from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer

__all__ = [
    "ConcatSynthesizer",
    "ModularBrain",
    "PromptReasoner",
    "SimpleCritic",
]
