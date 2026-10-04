"""deactivate_skill — remove a skill from the run-scoped activation set."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.enums.enums import ContentType
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.semantic.keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.policy.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.protocols import Tool
from lca.contracts.protocols.memory.operational_skills import (
    SkillNotFoundError,
    SkillPackageStore,
)
from lca.infrastructure.skills.activation.scope import unregister_activated
from lca.infrastructure.tools.contract.render.render import FieldSpec, RenderContract, contract
from lca.infrastructure.tools.contract.schema.schema import COMMON

DEACTIVATE_SKILL_TOOL = "deactivate_skill"


@contract(
    RenderContract(
        tool_name="deactivate_skill",
        identifier="lobe-skills",
        api_name="deactivateSkill",
        args=(COMMON["skill_id"].rename("name"),),
        state=(
            COMMON["name"],
            FieldSpec("deactivated", "deactivated", "boolean", "observation", required=False),
            FieldSpec("was_active", "was_active", "boolean", "observation", required=False),
            COMMON["content"],
        ),
        content_field="content",
    )
)
class SkillDeactivateTool(Tool):
    name = DEACTIVATE_SKILL_TOOL
    namespace: ClassVar[str] = "skill"
    description = (
        "停用已激活的操作 skill：清除本 run 的激活状态，后续 run_skill_script 会拒绝该 skill，"
        "释放每 run 激活预算。诚实边界：只清激活状态；历史 tool result 里已注入的 SKILL.md "
        "全文清不掉（历史 append-only），靠 compaction 兜底。参数: skill_id（skill_id 或 name）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "已激活 skill 的 skill_id 或 name"},
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
        removed = unregister_activated(package.skill_id)
        body = (
            f"已停用 skill：{package.name} ({package.skill_id})；后续 exec 会被拒绝"
            if removed
            else f"skill 未激活，无需停用：{package.name} ({package.skill_id})"
        )
        state = {
            "success": True,
            "source": "agent",
            "id": package.skill_id,
            "name": package.name,
            "skill_id": package.skill_id,
            "title": package.name,
            "deactivated": removed,
            "was_active": removed,
            "content": body,
        }
        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"text": body, "skill_id": package.skill_id, **state},
            content_type=ContentType.TEXT,
            latency_ms=latency_ms,
        )

    def _resolve_package(self, raw: str):
        try:
            return self._store.get(raw)
        except SkillNotFoundError:
            pass
        raw_lower = raw.lower()
        for entry in self._store.list_installed():
            if entry.name.lower() == raw_lower:
                return self._store.get(entry.skill_id)
        return None
