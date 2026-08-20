"""System Prompt Service Definition plugin — Tier-1.

The full SystemPromptService (with section assembler) is out of scope for
this minimal stub. Real implementation lives in lca/layer0_infra/system_prompt/service.py.
"""

from __future__ import annotations

from typing import Any

from lca.plugins._cordis_adapter import plugin


class _MinimalSystemPromptService:
    """Minimal stub — replaced by full implementation in Chunk 2."""

    def assemble(self, role: str, **kwargs: object) -> str:
        return f"base_prompt_for({role})"


@plugin(
    name="lca-system-prompt-service",
    provides=["system_prompt"],
    layer="service",
    side_effects="none",
    policy_class="control",
    description="Minimal SystemPromptService stub — section assembler deferred.",
    test_suite="tests/test_plugin_alignment.py::test_tier1_plugin_shape",
)
async def setup(ctx: Any, config: Any) -> None:
    ctx.provide("system_prompt", _MinimalSystemPromptService())
