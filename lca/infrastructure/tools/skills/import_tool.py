"""import_skill — network install into local skill cache."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import Tool
from lca.contracts.protocols.memory.operational_skills import SkillImporter, SkillImportError
from lca.infrastructure.tools.contract.render import RenderContract, contract
from lca.infrastructure.tools.contract.schema import COMMON

IMPORT_SKILL_TOOL = "import_skill"


@contract(
    RenderContract(
        tool_name="import_skill",
        identifier="lobe-skill-store",
        api_name="importSkill",
        args=(
            COMMON["identifier"].optional(),
            COMMON["url"].optional(),
            COMMON["kind"].optional(),
        ),
        state=(
            COMMON["name"],
            COMMON["content"],
        ),
        content_field="content",
    )
)
class SkillImportTool(Tool):
    name = IMPORT_SKILL_TOOL
    description = (
        "从网络安装操作 skill 到本地技能库（与角色身份无关）。"
        "支持：market identifier、lobehub.com/skills/…/skill.md、"
        "GitHub 目录链接、ZIP URL、裸 SKILL.md URL。"
        "参数: identifier（Market ID，与 url 二选一）或 url + kind（auto/url/zip）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "identifier": {
                "type": "string",
                "description": "LobeHub Market skill identifier，如 anthropics-skills-pdf",
            },
            "url": {"type": "string", "description": "GitHub / ZIP / SKILL.md URL"},
            "kind": {
                "type": "string",
                "enum": ["auto", "url", "zip"],
                "default": "auto",
            },
        },
    }
    is_idempotent = False
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(self, importer: SkillImporter) -> None:
        self._importer = importer

    def validate(self, args: dict[str, Any]) -> str | None:
        ident = str(args.get("identifier") or "").strip()
        url = str(args.get("url") or "").strip()
        if not ident and not url:
            return "identifier 与 url 至少提供一个"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        ident = str(args.get("identifier") or "").strip()
        url = str(args.get("url") or "").strip()
        kind = str(args.get("kind") or "auto")
        try:
            if ident:
                package = await self._importer.import_from_market(ident)
            else:
                package = await self._importer.import_from_url(url, kind=kind)
        except (SkillImportError, ValueError) as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(exc),
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        text = (
            f"已安装 skill「{package.name}」({package.skill_id})，"
            f"资源 {len(package.resource_paths)} 个。"
            f"请调用 activate_skill 加载操作指南。"
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"text": text, "skill_id": package.skill_id, "name": package.name},
            content_type=ContentType.TEXT,
            latency_ms=latency_ms,
        )
