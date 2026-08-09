"""read_skill_reference — load bundled skill resource files."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.enums import ContentType
from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.budget import DEFAULT_TOOL_TIMEOUT_S
from lca.contracts.models.core.decision import Observation
from lca.contracts.protocols import Tool
from lca.contracts.protocols.operational_skills import SkillNotFoundError, SkillPackageStore

READ_SKILL_REFERENCE_TOOL = "read_skill_reference"


class SkillReadReferenceTool(Tool):
    name = READ_SKILL_REFERENCE_TOOL
    description = (
        "读取已安装 skill 的附属资源文件（模板/参考文档/脚本说明等）。"
        "需先 activate_skill。参数: skill_id、path（skill 包内相对路径）。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "skill_id": {"type": "string"},
            "path": {"type": "string", "description": "如 REFERENCE.md 或 scripts/foo.py"},
        },
        "required": ["skill_id", "path"],
    }
    is_idempotent = True
    default_timeout_s = DEFAULT_TOOL_TIMEOUT_S

    def __init__(self, store: SkillPackageStore) -> None:
        self._store = store

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        skill_id = str(args.get("skill_id") or "").strip()
        path = str(args.get("path") or "").strip()
        try:
            content = self._store.read_resource(skill_id, path)
        except SkillNotFoundError as exc:
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
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={"text": content, "path": path, "skill_id": skill_id},
            content_type=ContentType.TEXT,
            latency_ms=latency_ms,
        )
