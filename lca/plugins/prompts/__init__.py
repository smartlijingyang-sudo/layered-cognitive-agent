"""Brain Prompt SSOT — three seam plugins and one large primitive plugin.

DSH-style Service Definition / Service Provider / Primitive grouping:

- :mod:`lca.plugins.prompts.registry` — closed PromptSectionRegistry (Tier-1 SEAM)
- :mod:`lca.plugins.prompts.template_provider` — PromptTemplateProvider (Tier-1 PROVIDER)
- :mod:`lca.plugins.prompts.sections` — all 17 section plugins in one Cordis module (Tier-1 PRIMITIVE)
- :mod:`lca.plugins.prompts.assembler` — Profile-selected PromptAssembler (Tier-1 PRIMITIVE)
- :mod:`lca.plugins.prompts.selector` — Profile-selected PromptTemplateSelector (Tier-1 PRIMITIVE)
"""

from lca.plugins.prompts import (
    assembler,
    registry,
    sections,
    selector,
    template_provider,
)
from lca.plugins.prompts.registry import (
    Config as RegistryConfig,
)
from lca.plugins.prompts.registry import (
    PromptSectionRegistryError,
    _RegistryImpl,
)

__all__ = [
    "PromptSectionRegistryError",
    "RegistryConfig",
    "_RegistryImpl",
    "assembler",
    "registry",
    "sections",
    "selector",
    "template_provider",
]
