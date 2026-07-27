"""L1 Brain —— ModularBrain(MAP五模块) + Reasoner + Critic + DecisionParser + Synthesizer。"""

from lca.layer1_cognitive.brain.critic import SimpleCritic
from lca.layer1_cognitive.brain.decision_parser import SimpleDecisionParser
from lca.layer1_cognitive.brain.modular_brain import ModularBrain
from lca.layer1_cognitive.brain.reasoner import SimpleReasoner
from lca.layer1_cognitive.brain.synthesizer import ConcatSynthesizer

__all__ = [
    "ConcatSynthesizer",
    "ModularBrain",
    "SimpleCritic",
    "SimpleDecisionParser",
    "SimpleReasoner",
]
