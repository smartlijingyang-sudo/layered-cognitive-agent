"""声明式计划使用的稳定共享词汇。

本模块只定义跨插件声明、阶段图和执行 wire shape 共用的版本、错误码与
受限词表。它不承载具体计划数据或运行时行为。
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
    PHASE_EXECUTOR = "phase-executor"
    CONTRIBUTION = "contribution"
    EFFECT_HANDLER = "effect-handler"
    OBSERVER = "observer"
    COMPOSITE = "composite"
    DRIVER = "driver"


class ContributionRole(str, Enum):
    PREPARE = "prepare"
    GOVERN = "govern"
    TRANSFORM = "transform"
    OBSERVE = "observe"
    FINALIZE = "finalize"


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
AGGREGATIONS = frozenset({"all-allow", "deny-on-any-deny", "first-terminal", "ordered-rewrite"})
ALLOWED_EFFECTS = frozenset({"none", "tools", "memory", "network", "filesystem", "world"})


__all__ = [
    "AGGREGATIONS",
    "ALLOWED_EFFECTS",
    "CARDINALITIES",
    "DECLARATIVE_PLAN_VERSION",
    "PLUGIN_SPEC_VERSION",
    "ContributionRole",
    "DeclarativeValidationError",
    "PluginSpecKind",
    "RelationType",
    "SemanticPhase",
]
