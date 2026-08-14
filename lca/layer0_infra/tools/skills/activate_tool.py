"""activate_skill — inject SKILL.md into agent context."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import Tool
from lca.contracts.protocols.operational_skills import (
    SkillNotFoundError,
    SkillPackage,
    SkillPackageStore,
)
from lca.layer0_infra.search.service import any_search_provider_available
from lca.layer0_infra.search.skill_policy import is_redundant_cli_search_skill
from lca.layer0_infra.skills.activation_scope import register_activated

ACTIVATE_SKILL_TOOL = "activate_skill"

_REDIRECT_WEB_SEARCH_MESSAGE = (
    "TAVILY_API_KEY 已配置：实时搜索请使用 web_search 工具（LobeHub Web Browsing 对齐），"
    "勿激活 Tavily CLI skill。"
)


class SkillActivateTool(Tool):
    name = ACTIVATE_SKILL_TOOL
    description = (
        "激活已安装的操作 skill，将其 SKILL.md 操作指南注入当前上下文。"
        "Office 文档（.docx/.xlsx/.pptx）优先 activate_skill('officecli')，"
        "再 run_command 调用预装 officecli CLI（--json）。"
        "PDF 用 anthropics-skills-pdf；纯表分析可用 pandas 无需 skill。"
        "参数: skill_id（安装时的 identifier 或 import 返回的 skill_id）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "已安装 skill 的 skill_id 或 name"},
        },
        "required": ["skill_id"],
    }
    is_idempotent = True
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(self, store: SkillPackageStore) -> None:
        self._store = store

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        raw = str(args.get("skill_id") or "").strip()
        package = self._resolve_package(raw)
        if package is None:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"未找到 skill: {raw!r}；请先 import_skill",
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        if any_search_provider_available() and is_redundant_cli_search_skill(
            skill_id=package.skill_id,
            name=package.name,
        ):
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=_REDIRECT_WEB_SEARCH_MESSAGE,
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        register_activated(package.skill_id, package.name)
        from lca.layer0_infra.sandbox.surface import current_surface, skill_preamble

        body = skill_preamble(current_surface()) + package.content
        summary = (package.summary or "").strip()
        state = {
            "success": True,
            "hasResources": bool(package.resource_paths),
            "source": "agent",
            "id": package.skill_id,
            "name": package.name,
            "skill_id": package.skill_id,
            "title": package.name,
            "content": body,
        }
        if summary:
            state["description"] = summary
        if package.resource_paths:
            state["resources"] = list(package.resource_paths)
        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"text": body, "skill_id": package.skill_id, "state": state},
            content_type=ContentType.TEXT,
            latency_ms=latency_ms,
        )

    def _resolve_package(self, raw: str) -> SkillPackage | None:
        try:
            return self._store.get(raw)
        except SkillNotFoundError:
            pass
        raw_lower = raw.lower()
        for entry in self._store.list_installed():
            if entry.name.lower() == raw_lower:
                return self._store.get(entry.skill_id)
        return None
