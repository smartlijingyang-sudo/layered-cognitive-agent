"""Retired: LLM adapters are owned solely by ``lca.plugins.seams.think.llm_resolver``.

This module remains importable so old bundle/test references fail loudly
instead of silently registering mock/deepseek providers.
"""

from __future__ import annotations

raise ImportError(
    "lca.plugins.providers.think.llm is retired; use lca.plugins.seams.think.llm_resolver "
    "(id=lca-llm-resolver) as the sole LLM credential and adapter owner."
)
