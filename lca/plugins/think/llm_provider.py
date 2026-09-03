"""Retired: LLM adapters are owned solely by ``lca.plugins.think.llm_resolver_seam``.

This module remains importable so old bundle/test references fail loudly
instead of silently registering mock/deepseek providers.
"""

from __future__ import annotations

raise ImportError(
    "lca.plugins.think.llm_provider is retired; use lca.plugins.think.llm_resolver_seam "
    "(id=lca-llm-resolver) as the sole LLM credential and adapter owner."
)
