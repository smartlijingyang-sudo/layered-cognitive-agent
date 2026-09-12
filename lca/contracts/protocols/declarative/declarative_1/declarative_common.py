"""声明式计划使用的稳定共享词汇。

ADR-0221: ``PHASE_EXECUTOR`` / ``CONTRIBUTION`` plugin kinds and the
``ContributionRole`` / ``AGGREGATIONS`` vocabularies have been retired.
Every phase node is now a ``PRIMITIVE`` (or ``PROVIDER``) kind; phase
contributions are expressed as additional subgraph nodes inside the
corresponding ``bundles/{phase}_subgraph.yaml``, not as static
plugin-manifest declarations.
"""

from __future__ import annotations

from enum import Enum

PLUGIN_SPEC_VERSION = "lca/plugin-spec/v1"
DECLARATIVE_PLAN_VERSION = "v2"


class DeclarativeValidationError(ValueError):
    """带稳定错误码的编译期声明式计划错误。"""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class SemanticPhase(str, Enum):
    """ADR-0075 允许的封闭语义阶段集合。"""

    PERCEIVE = "perceive"
    THINK = "think"
    ACT = "act"
    REFLECT = "reflect"
    REMEMBER = "remember"
    STOP = "stop"


class PluginSpecKind(str, Enum):
    SEAM = "seam"
    PROVIDER = "provider"
    EFFECT_HANDLER = "effect-handler"
    OBSERVER = "observer"
    COMPOSITE = "composite"
    DRIVER = "driver"


class RelationType(str, Enum):
    BEFORE = "before"
    AFTER = "after"
    CONTAINS = "contains"
    GOVERNS = "governs"
    OBSERVES = "observes"
    REPLACES = "replaces"
    AUGMENTS = "augments"
    CONFLICTS_WITH = "conflicts_with"
    DEPENDS_ON = "depends_on"
    SCOPED_BY = "scoped_by"
    EMITS_TO = "emits_to"


CARDINALITIES = frozenset({"one", "optional", "many", "ordered-many"})
ALLOWED_EFFECTS = frozenset({"none", "tools", "memory", "network", "filesystem", "world"})

__all__ = [
    "ALLOWED_EFFECTS",
    "CARDINALITIES",
    "DECLARATIVE_PLAN_VERSION",
    "PLUGIN_SPEC_VERSION",
    "DeclarativeValidationError",
    "PluginSpecKind",
    "RelationType",
    "SemanticPhase",
]
