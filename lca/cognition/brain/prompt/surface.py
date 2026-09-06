"""PromptSurface — unified tools + sandbox prompt SSOT (ADR-0196)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

from lca.cognition.brain.prompt.sandbox_prompt import build_cloud_sandbox_prompt
from lca.cognition.convergence.task_class import classify_task, resolve_task_class
from lca.contracts.models.core.policy.convergence import TaskClass
from lca.contracts.models.core.state.state import AgentState
from lca.contracts.protocols.runtime.infra.infra import Tool

_EMPTY_TOOLS = "（无可用工具）"

_CONCISE_SANDBOX_HINT = (
    "<tool name=\"lobe-cloud-sandbox\">\n"
    "<tool.instructions>\n"
    "Cloud sandbox is available. Prefer a direct text reply when the user asks for "
    "jokes, explanations, or short answers. Use executeCode only when code output "
    "is explicitly required. Write deliverables under /mnt/data/outputs.\n"
    "</tool.instructions>\n"
    "</tool>"
)


@dataclass(frozen=True, slots=True)
class PromptSurfaceRender:
    tools_xml: str
    sandbox_block: str
    task_class: TaskClass
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
        payload = self.body.encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]


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

    def should_include_full_sandbox(self, task_class: TaskClass, tools: Sequence[Tool]) -> bool:
        return bool(tools) and task_class != "informative_text"

    def render_sandbox_block(
        self,
        tools: Sequence[Tool],
        *,
        task_class: TaskClass,
    ) -> str:
        if not tools:
            return ""
        if not self.should_include_full_sandbox(task_class, tools):
            return _CONCISE_SANDBOX_HINT
        return build_cloud_sandbox_prompt(list(tools))

    def render_tools_block(
        self,
        tools: Sequence[Tool],
        *,
        task: str = "",
        state: AgentState | None = None,
    ) -> PromptSurfaceRender:
        task_class = resolve_task_class(state) if state is not None else classify_task(task)
        tools_xml = self.render_tools_xml(tools)
        include_full = self.should_include_full_sandbox(task_class, tools)
        sandbox_block = self.render_sandbox_block(tools, task_class=task_class)
        return PromptSurfaceRender(
            tools_xml=tools_xml,
            sandbox_block=sandbox_block,
            task_class=task_class,
            tool_count=len(tuple(tools)),
            include_full_sandbox=include_full,
        )


__all__ = ["PromptSurface", "PromptSurfaceRender"]
