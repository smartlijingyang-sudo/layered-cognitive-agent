"""assistant.catalog 包：plugin 入口 + 聚焦子模块。

``plugin`` 是插件入口（bundle ``$module`` 与既有 importers 指向它）；
``handlers`` / ``soul`` / ``plan_overlay`` / ``manifest`` / ``events``
承载拆出的实现。
"""

from lca.plugins.domain.assistant.catalog.plugin import (
    AssistantAlreadyExists,
    AssistantCatalogError,
    AssistantCatalogImpl,
    AssistantDigestMismatch,
    Config,
    PlanOverlayValidationError,
    SoulValidationError,
    setup,
)

__all__ = [
    "AssistantAlreadyExists",
    "AssistantCatalogError",
    "AssistantCatalogImpl",
    "AssistantDigestMismatch",
    "Config",
    "PlanOverlayValidationError",
    "SoulValidationError",
    "setup",
]
