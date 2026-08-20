"""Tier-2 Provider plugins.

Each Tier-1 Definition seam (tools / sandbox / memory / …) has a provider
plugin here that registers implementations. LLM is an exception: credentials
and the chat adapter are owned solely by ``lca.plugins.llm_resolver``.
"""
