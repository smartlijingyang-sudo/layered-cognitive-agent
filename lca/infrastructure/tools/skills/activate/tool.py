"""activate_skill — inject SKILL.md into agent context."""

from __future__ import annotations

import time
from pathlib import PurePosixPath
from typing import Any, ClassVar

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool
from lca.contracts.protocols.memory.operational_skills import (
    SkillNotFoundError,
    SkillPackage,
    SkillPackageStore,
)
from lca.infrastructure.search.service.service import any_search_provider_available
from lca.infrastructure.search.skill.policy import is_redundant_cli_search_skill
from lca.infrastructure.skills.activation.scope import register_activated
from lca.infrastructure.tools.contract.render.render import FieldSpec, RenderContract, contract
from lca.infrastructure.tools.contract.schema.schema import COMMON

ACTIVATE_SKILL_TOOL = "activate_skill"

_REDIRECT_WEB_SEARCH_MESSAGE = (
    "TAVILY_API_KEY 已配置：实时搜索请使用 web_search 工具（LobeHub Web Browsing 对齐），"
    "勿激活 Tavily CLI skill。"
)


_SCRIPT_SUFFIXES = frozenset({".py", ".sh", ".bash", ".js", ".mjs"})
_DOC_SUFFIXES = frozenset({".md", ".txt"})
_SKIP_NAMES = frozenset({"license", "license.txt", "licence.txt"})


def usable_skill_resources(package: SkillPackage) -> tuple[str, ...]:
    """Paths the agent may read or run.

    Frontmatter ``references`` wins. Market packages often omit that field
    and only list ``resource_paths`` (including xsd / license noise).
    """
    if package.references:
        return package.references
    return tuple(path for path in package.resource_paths if _is_agent_usable(path))


def _is_agent_usable(rel: str) -> bool:
    posix = rel.replace("\\", "/")
    name = posix.rsplit("/", 1)[-1].lower()
    if name in _SKIP_NAMES:
        return False
    if "/schemas/" in f"/{posix.lower()}/":
        return False
    suffix = PurePosixPath(name).suffix.lower()
    return suffix in _SCRIPT_SUFFIXES or suffix in _DOC_SUFFIXES


def _script_paths(paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        path
        for path in paths
        if PurePosixPath(path.replace("\\", "/")).suffix.lower() in _SCRIPT_SUFFIXES
    )


def build_skill_references_section(package: SkillPackage) -> str:
    """SKILL.md 之后的包内索引：可读文档 + 可运行脚本。

    不把脚本正文塞进 prompt。模型用 ``run_skill_script`` 在 skill 工作目录执行。
    """
    version = (package.version or "").strip() or "?"
    usable = usable_skill_resources(package)
    scripts = _script_paths(usable)
    docs = tuple(path for path in usable if path not in scripts)
    lines: list[str] = [
        f"<skill_references skill_id={package.skill_id!r} version={version!r}>",
    ]
    if docs:
        lines.append("包内可读文档（read_skill_reference_once，不要重复读同一路径）:")
        for rel in docs:
            lines.append(f"- {rel}")
    elif not scripts:
        lines.append(
            "(无可用 references — SKILL.md 正文已是完整指南,"
            "不要调 read_skill_reference_once;读不存在的路径会被节流熔断)"
        )
    if scripts:
        lines.append(
            "包内脚本（在 skill 工作目录用 run_skill_script 执行，不要把源码抄进 executeCode）:"
        )
        for rel in scripts:
            lines.append(f"- {rel}")
        lines.append(
            f'例: run_skill_script({{"command": "python {scripts[0]}", '
            f'"skill_id": {package.skill_id!r}}})'
        )
    lines.append("</skill_references>")
    return "\n".join(lines)


@contract(
    RenderContract(
        tool_name="activate_skill",
        identifier="lobe-skills",
        api_name="activateSkill",
        args=(COMMON["skill_id"].rename("name"),),
        state=(
            COMMON["name"],
            COMMON["title"],
            FieldSpec("description", "description", "string", "observation", required=False),
            COMMON["has_resources"],
            COMMON["content"],
        ),
        content_field="content",
    )
)
class SkillActivateTool(Tool):
    name = ACTIVATE_SKILL_TOOL
    description = (
        "激活已安装的操作 skill，将其 SKILL.md 操作指南注入当前上下文。"
        "包内 scripts/ 用 run_skill_script 在 skill 工作目录执行，不要把脚本抄进 executeCode。"
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
        from lca.infrastructure.observability.meta_event_emit import emit_skill_activated

        emit_skill_activated(
            skill_id=package.skill_id,
            name=package.name,
            content_hash=package.content_hash,
            source="tool:activate_skill",
        )
        from lca.infrastructure.observability.meta_event_emit import emit_context_injected

        emit_context_injected(
            source=f"skill:{package.skill_id}",
            content_ref=f"skill:{package.skill_id}@{package.content_hash}",
        )
        from lca.infrastructure.sandbox.surface.surface import skill_preamble

        body = skill_preamble() + package.content
        # ADR-0214 §7.4: SKILL.md 正文后追加 references 索引,引导它走
        # ``read_skill_reference_once`` 而不是凭 body 暗示的路径去试读。
        body = body + "\n\n" + build_skill_references_section(package)
        summary = (package.summary or "").strip()
        # ADR-0102: payload is the Tool's wire-shape view, flattened so the
        # RenderContract reader (``project_tool_state``) can pick fields
        # directly from the top level.  Use snake_case python keys the
        # ``activate_skill`` contract expects (``has_resources``).
        # ``text`` stays at the top because the contract's content_field
        # is ``"content"`` and we want ``text`` available for the inline
        # fallback / extra consumers.
        state = {
            "success": True,
            "has_resources": bool(package.resource_paths),
            "source": "agent",
            "id": package.skill_id,
            "name": package.name,
            "skill_id": package.skill_id,
            "title": package.name,
            "content": body,
        }
        if summary:
            state["description"] = summary
        usable = usable_skill_resources(package)
        if usable:
            state["references"] = list(usable)
        if package.resource_paths:
            state["resources"] = list(package.resource_paths)
        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"text": body, "skill_id": package.skill_id, **state},
            content_type=ContentType.TEXT,
            latency_ms=latency_ms,
        )

    def _resolve_package(self, raw: str) -> SkillPackage | None:
        try:
            return self._store.get(raw)
        except SkillNotFoundError:
            # INTENTIONAL: 精确 ID 未命中 → 落到 case-insensitive 名字 fallback;
            # 这是用户输入容错的预期路径,不是错误。
            pass
        raw_lower = raw.lower()
        for entry in self._store.list_installed():
            if entry.name.lower() == raw_lower:
                return self._store.get(entry.skill_id)
        return None
