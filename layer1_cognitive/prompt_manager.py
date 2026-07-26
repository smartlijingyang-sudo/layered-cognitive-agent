"""SimplePromptManager —— Prompt 模板集中管理与版本化。"""

from __future__ import annotations

from typing import Any

from contracts.protocols import PromptManager


class SimplePromptManager(PromptManager):
    """基于 str.format() 的模板渲染器。"""

    def __init__(self) -> None:
        self._templates: dict[str, str] = {}

    def register_template(self, name: str, template: str, version: str = "1.0") -> None:
        self._templates[name] = template

    def render(self, template_name: str, variables: dict[str, Any]) -> str:
        return self._templates[template_name].format(**variables)
