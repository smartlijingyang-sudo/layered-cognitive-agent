"""Step tree deriver plugin package (ADR-0195 P2-18)."""

from lca.plugins.observability.deriver.step_tree.plugin import (
    StepTreeDeriverCapability,
    setup,
)

__all__ = ["StepTreeDeriverCapability", "setup"]
