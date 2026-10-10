"""import_skill — network install into local skill cache."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool
from lca.contracts.protocols.assistant.skill_overlay import SkillSource
from lca.contracts.protocols.memory.operational_skills import (
    SkillImporter,
    SkillImportError,
    SkillPackage,
)
from lca.infrastructure.tools.contract.render.render import RenderContract, contract
from lca.infrastructure.tools.contract.schema.schema import COMMON

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
    namespace: ClassVar[str] = "skill"
    description = (
        "从网络安装操作 skill。"
        "支持 market identifier、Market 下载地址、GitHub 目录、ZIP、裸 SKILL.md。"
        "当前 run 绑定了助理时，安装进该助理 Home，然后用 activate_skill。"
        "没有绑定助理时，安装进全局技能库。"
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

    def __init__(
        self,
        importer: SkillImporter,
        *,
        home: tuple[object, str] | None = None,
    ) -> None:
        self._importer = importer
        self._home = home

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
            if self._home is not None:
                package = await self._publish_home(package, ident=ident, url=url)
        except (SkillImportError, ValueError) as exc:
            latency_ms = int((time.monotonic() - start) * 1000)
            from lca.infrastructure.observability.meta_event_emit import emit_skill_install_failed

            emit_skill_install_failed(reason=str(exc), source=ident or url)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=str(exc),
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        from lca.infrastructure.observability.meta_event_emit import emit_skill_loaded

        emit_skill_loaded(
            skill_id=package.skill_id,
            content_hash=package.content_hash,
            invocation="tool:import_skill",
        )
        where = "当前助理" if self._home is not None else "全局技能库"
        text = (
            f"已安装 skill「{package.name}」({package.skill_id}) 到{where}，"
            f"资源 {len(package.resource_paths)} 个。"
            f"请调用 activate_skill 加载操作指南。"
        )
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"content": text, "skill_id": package.skill_id, "name": package.name},
            content_type=ContentType.TEXT,
            latency_ms=latency_ms,
        )

    async def _publish_home(
        self,
        package: SkillPackage,
        *,
        ident: str,
        url: str,
    ) -> SkillPackage:
        """把已拉下的包交到助理 Home。activate 只读这一份。"""
        overlay, assistant_id = self._home or (None, "")
        install = getattr(overlay, "install", None)
        if not callable(install) or not assistant_id:
            return package
        root = getattr(getattr(self._importer, "store", None), "root", None)
        pkg_dir = Path(root) / package.skill_id if root is not None else None
        if pkg_dir is not None and (pkg_dir / "SKILL.md").is_file():
            source = SkillSource(local_path=str(pkg_dir.resolve()))
        elif url.startswith(("http://", "https://")):
            source = SkillSource(url=url)
        elif ident:
            from lca.infrastructure.skills.settings.settings import get_skill_settings

            base = get_skill_settings().market_base_url.rstrip("/")
            source = SkillSource(url=f"{base}/api/v1/skills/{ident}/download")
        else:
            return package
        await install(assistant_id, source, actor="agent")
        return package
