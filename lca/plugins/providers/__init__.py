"""Tier-2 Provider plugins.

Each Tier-1 Definition plugin (e.g. lca.plugins.llm_service) has a corresponding
Tier-2 Provider plugin here (e.g. lca.plugins.providers.llm) that registers
multiple provider implementations and selects the active one via config.

Single plugin per seam — factory pattern. Plugin file ≤ 50 lines.
"""
