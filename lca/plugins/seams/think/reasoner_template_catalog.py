"""Profile-selected built-in template catalog for PromptReasoner factories."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field

from lca.cognition.brain.prompts import load_builtin_prompt
from lca.contracts.capabilities import REASONER_TEMPLATE_CATALOG
from lca.contracts.protocols.think.cognition import ReasonerTemplateCatalog
from lca.harness.plugin_api import PluginContext, PluginKind, plugin

_REQUIRED_TEMPLATES: frozenset[str] = frozenset(
    {"react_prompt", "hierarchical_prompt", "routing_prompt"}
)


@dataclass(frozen=True, slots=True)
class BuiltinReasonerTemplateCatalog(ReasonerTemplateCatalog):
    """Load an explicitly selected, complete set of bundled reasoner templates."""

    template_names: tuple[str, ...]

    def templates(self) -> Mapping[str, str]:
        """Return a fresh immutable-by-convention mapping for each factory build."""

        return {name: load_builtin_prompt(name) for name in self.template_names}


class Config(BaseModel):
    """Names of bundled templates selected by the active profile."""

    model_config = ConfigDict(extra="forbid")
    template_names: tuple[str, ...] = Field(
        default=("react_prompt", "hierarchical_prompt", "routing_prompt")
    )

    def model_post_init(self, __context: object) -> None:
        missing = _REQUIRED_TEMPLATES - set(self.template_names)
        if missing:
            raise ValueError(
                f"reasoner template catalog is missing required templates: {sorted(missing)}"
            )


@plugin(
    id="lca-reasoner-template-catalog-builtin",
    provides=[REASONER_TEMPLATE_CATALOG.key],
    requires=[],
    implements=[ReasonerTemplateCatalog],
    layer="L1",
    effects="none",
    description="Provide the profile-selected bundled PromptReasoner templates.",
    test_suite="tests/architecture/test_reasoner_template_catalog_capability.py",
    kind=PluginKind.PRIMITIVE,
)
async def setup(ctx: PluginContext, config: Config) -> None:
    """Expose the complete catalog required by modular and simple brain factories."""

    ctx.provide(
        REASONER_TEMPLATE_CATALOG.key, BuiltinReasonerTemplateCatalog(config.template_names)
    )


__all__ = ["BuiltinReasonerTemplateCatalog", "Config", "setup"]
