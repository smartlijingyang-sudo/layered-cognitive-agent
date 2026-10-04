"""retire_skill / unretire_skill — skill lifecycle review (minimal).

Retiring hides a skill from default search and blocks script execution;
the package stays on disk so it can be restored with unretire_skill.
"""

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
from lca.infrastructure.tools.contract.render.render import RenderContract, contract
from lca.infrastructure.tools.contract.schema.schema import COMMON

RETIRE_SKILL_TOOL = "retire_skill"
UNRETIRE_SKILL_TOOL = "unretire_skill"


def _resolve_package(store: SkillPackageStore, raw: str):
    try:
        return store.get(raw)
    except SkillNotFoundError:
        pass
    raw_lower = raw.lower()
    for entry in store.list_installed():
        if entry.name.lower() == raw_lower:
            return store.get(entry.skill_id)
    return None


class _ReviewBase(Tool):
    namespace: ClassVar[str] = "skill"
    is_idempotent = True
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string", "description": "skill 的 skill_id 或 name"},
        },
        "required": ["skill_id"],
    }

    _retired_value: ClassVar[bool]

    def __init__(self, store: SkillPackageStore) -> None:
        self._store = store

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        raw = str(args.get("skill_id") or "").strip()
        package = _resolve_package(self._store, raw)
        if package is None:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"未找到 skill: {raw!r}",
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        try:
            updated = self._store.update_package_meta(
                package.skill_id, retired=self._retired_value
            )
        except NotImplementedError:
            latency_ms = int((time.monotonic() - start) * 1000)
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error="当前 skill store 只读，不支持退役操作",
                latency_ms=latency_ms,
                extra={FAILURE_KIND: FAILURE_KIND_VALIDATION},
            )
        verb = "已退役" if self._retired_value else "已恢复"
        body = f"{verb} skill：{updated.name} ({updated.skill_id})"
        state = {
            "success": True,
            "source": "agent",
            "id": updated.skill_id,
            "name": updated.name,
            "skill_id": updated.skill_id,
            "retired": updated.retired,
            "usage_count": updated.usage_count,
            "content": body,
        }
        latency_ms = int((time.monotonic() - start) * 1000)
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"text": body, **state},
            content_type=ContentType.TEXT,
            latency_ms=latency_ms,
        )


@contract(
    RenderContract(
        tool_name="retire_skill",
        identifier="lobe-skills",
        api_name="retireSkill",
        args=(COMMON["skill_id"].rename("name"),),
        state=(COMMON["name"], COMMON["content"]),
        content_field="content",
    )
)
class SkillRetireTool(_ReviewBase):
    name = RETIRE_SKILL_TOOL
    description = (
        "退役一个 skill：默认搜索不再列出它，run_skill_script 拒绝执行它。"
        "包保留在磁盘上，可用 unretire_skill 恢复。参数: skill_id（skill_id 或 name）。"
    )
    _retired_value: ClassVar[bool] = True


@contract(
    RenderContract(
        tool_name="unretire_skill",
        identifier="lobe-skills",
        api_name="unretireSkill",
        args=(COMMON["skill_id"].rename("name"),),
        state=(COMMON["name"], COMMON["content"]),
        content_field="content",
    )
)
class SkillUnretireTool(_ReviewBase):
    name = UNRETIRE_SKILL_TOOL
    description = (
        "恢复一个已退役的 skill：重新参与搜索与执行。参数: skill_id（skill_id 或 name）。"
    )
    _retired_value: ClassVar[bool] = False
