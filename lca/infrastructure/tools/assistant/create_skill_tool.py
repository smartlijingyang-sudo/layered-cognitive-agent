"""create_assistant_skill — install a skill into the bound assistant Home (ADR-0187)."""

from __future__ import annotations

import shutil
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool
from lca.contracts.protocols.assistant.skill_overlay import SkillSource
from lca.infrastructure.observability.facade.run.ambit import current_assistant_id
from lca.infrastructure.skills.disk.store import sanitize_skill_id
from lca.infrastructure.skills.frontmatter.frontmatter import skill_title, split_frontmatter

if TYPE_CHECKING:
    from lca.contracts.protocols.assistant.skill_overlay import AssistantSkillOverlay

CREATE_ASSISTANT_SKILL_TOOL = "create_assistant_skill"


class AssistantCreateSkillTool(Tool):
    """Create/install a skill under ``{assistant_home}/skills/<skill_id>/``."""

    name = CREATE_ASSISTANT_SKILL_TOOL
    description = (
        "为当前绑定的助理创建并安装一个操作 skill（写入助理 Home 的 skills/ 目录，"
        "后续对话会自动加载）。"
        "参数: skill_md（SKILL.md 全文，含 YAML frontmatter）、"
        "skill_id（可选，默认从 frontmatter name 推导）、"
        "sandbox_path（可选，沙箱/工作区内已写好的 SKILL.md 文件，或包含 SKILL.md "
        "与 resources/ 的目录，与 skill_md 二选一；传目录时 resources/ 等附属文件会一并安装）。"
        "安装后请 activate_skill 加载操作指南。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "skill_md": {
                "type": "string",
                "description": "SKILL.md 完整内容（含 frontmatter）",
            },
            "skill_id": {
                "type": "string",
                "description": "可选 skill_id；缺省从 frontmatter name 推导",
            },
            "sandbox_path": {
                "type": "string",
                "description": "可选：沙箱内 SKILL.md 文件路径，或包含 SKILL.md + resources/ 的目录路径（与 skill_md 二选一）",
            },
        },
    }
    is_idempotent = False
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(self, *, overlay: AssistantSkillOverlay, assistant_id: str) -> None:
        self._overlay = overlay
        self._assistant_id = assistant_id

    def validate(self, args: dict[str, Any]) -> str | None:
        skill_md = str(args.get("skill_md") or "").strip()
        sandbox_path = str(args.get("sandbox_path") or "").strip()
        if not skill_md and not sandbox_path:
            return "skill_md 与 sandbox_path 至少提供一个"
        if skill_md and sandbox_path:
            return "skill_md 与 sandbox_path 只能提供一个"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        error = self.validate(args)
        if error is not None:
            return self._fail(start, error)

        skill_md = str(args.get("skill_md") or "").strip()
        sandbox_path = str(args.get("sandbox_path") or "").strip()
        explicit_id = str(args.get("skill_id") or "").strip()

        staging = Path(tempfile.mkdtemp(prefix="lca-create-skill-"))
        try:
            if skill_md:
                (staging / "SKILL.md").write_text(skill_md, encoding="utf-8")
            else:
                resolved = _resolve_workspace_path(sandbox_path)
                if resolved is None:
                    return self._fail(start, f"无法解析沙箱路径: {sandbox_path}")
                if resolved.is_dir():
                    shutil.copytree(resolved, staging, dirs_exist_ok=True)
                    if not (staging / "SKILL.md").is_file():
                        return self._fail(start, f"沙箱目录缺少 SKILL.md: {sandbox_path}")
                elif resolved.is_file():
                    (staging / "SKILL.md").write_text(
                        resolved.read_text(encoding="utf-8"),
                        encoding="utf-8",
                    )
                else:
                    return self._fail(start, f"沙箱路径不存在: {sandbox_path}")

            skill_md = (staging / "SKILL.md").read_text(encoding="utf-8")
            try:
                meta, _ = split_frontmatter(skill_md)
                skill_id = sanitize_skill_id(explicit_id or skill_title(meta, "assistant-skill"))
            except ValueError as exc:
                return self._fail(start, str(exc))

            if explicit_id:
                # The installer names the package from SKILL.md frontmatter, so an
                # `skill_id` argument that disagrees with it would be silently
                # dropped; refuse instead of installing under a different id.
                declared_id = sanitize_skill_id(skill_title(meta, "assistant-skill"))
                if skill_id != declared_id:
                    return self._fail(
                        start,
                        f"skill_id {skill_id!r} 与 SKILL.md frontmatter 的 "
                        f"name {declared_id!r} 不一致 — 二者必须相同",
                    )

            receipt = await self._overlay.install(
                self._assistant_id,
                SkillSource(local_path=str(staging)),
                actor="agent",
            )
        except Exception as exc:
            return self._fail(start, f"安装失败: {exc}")
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        text = (
            f"已为助理安装 skill「{receipt.skill_id}」到 {receipt.install_path}。"
            f"请调用 activate_skill 加载操作指南。"
        )
        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "content": text,
                "skill_id": receipt.skill_id,
                "name": receipt.skill_id,
                "install_path": receipt.install_path,
            },
            content_type=ContentType.TEXT,
            latency_ms=latency_ms,
        )

    def _fail(self, start: float, message: str) -> Observation:
        return Observation(
            observation_id=new_id("obs"),
            success=False,
            payload=None,
            error=message,
            latency_ms=int((time.monotonic() - start) * 1000),
            extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
        )


def _resolve_workspace_path(sandbox_path: str) -> Path | None:
    """Resolve a sandbox-relative path against the current run workspace root."""
    from lca.infrastructure.observability.facade.run.ambit import current_workspace

    workspace = current_workspace()
    if workspace is None:
        return None
    root = Path(getattr(workspace, "root", "") or getattr(workspace, "path", "") or "")
    if not root:
        return None
    return root / sandbox_path.lstrip("/")


def assistant_create_skill_tool_from_run(
    run: object | None,
    *,
    overlay: AssistantSkillOverlay,
) -> AssistantCreateSkillTool | None:
    """Materialize the tool when the run bind dict carries ``assistant_id``."""
    bind = run if isinstance(run, dict) else {}
    explicit = str(bind.get("assistant_id") or "").strip()
    assistant_id = explicit or current_assistant_id().strip()
    if not assistant_id:
        return None
    return AssistantCreateSkillTool(overlay=overlay, assistant_id=assistant_id)


__all__ = [
    "CREATE_ASSISTANT_SKILL_TOOL",
    "AssistantCreateSkillTool",
    "assistant_create_skill_tool_from_run",
]
