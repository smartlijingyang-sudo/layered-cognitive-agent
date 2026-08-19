"""System Prompt Service Definition plugin — Tier-1.

The full SystemPromptService (with section assembler) is out of scope for
this minimal stub. Real implementation lives in lca/layer0_infra/system_prompt/service.py.
"""
from __future__ import annotations

from cordis import plugin


class _MinimalSystemPromptService:
    """Minimal stub — replaced by full implementation in Chunk 2."""

    def assemble(self, role: str, **kwargs: object) -> str:
        return f"base_prompt_for({role})"


@plugin(name="lca-system-prompt-service")
async def setup(ctx, config) -> None:
    ctx.provide("system_prompt", _MinimalSystemPromptService())
