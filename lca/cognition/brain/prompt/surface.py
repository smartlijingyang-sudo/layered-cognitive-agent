"""PromptSurface — unified tools + sandbox prompt SSOT (ADR-0196)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from lca.cognition.brain.prompt.sandbox_prompt import build_cloud_sandbox_prompt
from lca.contracts.observability.canonical_digest import canonical_digest
from lca.contracts.protocols.runtime.infra.infra import Tool

_EMPTY_TOOLS = "（无可用工具）"


@dataclass(frozen=True, slots=True)
class PromptSurfaceRender:
    tools_xml: str
    sandbox_block: str
    tool_count: int
    include_full_sandbox: bool

    @property
    def body(self) -> str:
        parts = [self.tools_xml]
        if self.sandbox_block:
            parts.append(self.sandbox_block)
        return "\n".join(part for part in parts if part)

    @property
    def digest(self) -> str:
        return canonical_digest(self.body, length=16)


class PromptSurface:
    """Facade for model-visible tool catalog and environment blocks."""

    @classmethod
    def default(cls) -> PromptSurface:
        return cls()

    def render_tools_xml(self, tools: Sequence[Tool]) -> str:
        lines = tuple(
            f'<tool name="{tool.name}">{tool.description or tool.name}</tool>' for tool in tools
        )
        return "\n".join(lines) if lines else _EMPTY_TOOLS

    def render_sandbox_block(self, tools: Sequence[Tool]) -> str:
        if not tools:
            return ""
        return build_cloud_sandbox_prompt(list(tools))

    def render_tools_block(self, tools: Sequence[Tool]) -> PromptSurfaceRender:
        tools_xml = self.render_tools_xml(tools)
        include_full = bool(tools)
        sandbox_block = self.render_sandbox_block(tools)
        return PromptSurfaceRender(
            tools_xml=tools_xml,
            sandbox_block=sandbox_block,
            tool_count=len(tuple(tools)),
            include_full_sandbox=include_full,
        )


__all__ = ["PromptSurface", "PromptSurfaceRender"]
