"""Convergence helpers — delivery evidence fold and control plane (ADR-0196)."""

from lca.cognition.convergence.constants import (
    MIN_SUBSTANTIVE_STDOUT_CHARS,
    TASK_CLASS_MANIFEST_KIND,
)
from lca.cognition.convergence.delivery_synth import synthesize_delivery_response
from lca.cognition.convergence.evidence import build_delivery_evidence
from lca.cognition.convergence.material import collect_delivery_material
from lca.cognition.convergence.policy import DefaultConvergencePolicy
from lca.cognition.convergence.predicates import delivery_satisfied
from lca.cognition.convergence.producer_tools import PRODUCER_TOOL_NAMES, is_producer_tool
from lca.cognition.convergence.runtime import ConvergenceRuntime
from lca.cognition.convergence.task_class import classify_task, resolve_task_class

__all__ = [
    "MIN_SUBSTANTIVE_STDOUT_CHARS",
    "PRODUCER_TOOL_NAMES",
    "TASK_CLASS_MANIFEST_KIND",
    "ConvergenceRuntime",
    "DefaultConvergencePolicy",
    "build_delivery_evidence",
    "classify_task",
    "collect_delivery_material",
    "delivery_satisfied",
    "is_producer_tool",
    "resolve_task_class",
    "synthesize_delivery_response",
]
