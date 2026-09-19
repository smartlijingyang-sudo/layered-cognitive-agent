"""SkillExecTool 资源缺失防护测试 —— 引用资源未安装时提前返回清晰错误。"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import patch

import pytest

from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.workspace.activation import ActivatedSkill
from lca.contracts.protocols.memory.operational_skills import SkillPackage
from lca.infrastructure.skills.activation.scope import activated_skills_scope
from lca.infrastructure.tools.skills.exec.tool import SkillExecTool

_RESOURCE = "resources/list_roles.py"


class _MissingResourceStore:
    def get(self, skill_id: str) -> SkillPackage:
        return SkillPackage(
            skill_id="create-assistant",
            name="create-assistant",
            summary="",
            content="# demo",
            resource_paths=(),
            source_url="",
            content_hash="sha256:demo",
            references=(_RESOURCE,),
        )

    def resource_files(self, skill_id: str) -> dict[str, bytes]:
        return {}

    def list_installed(self) -> tuple[object, ...]:
        return ()


class _CompleteResourceStore(_MissingResourceStore):
    def resource_files(self, skill_id: str) -> dict[str, bytes]:
        return {_RESOURCE: b"print('ok')\n"}


def _build_tool(store: Any) -> SkillExecTool:
    return SkillExecTool(sandbox=object(), store=store, file_store=object())


def _run_exec(tool: SkillExecTool) -> Observation:
    with activated_skills_scope(
        [ActivatedSkill(skill_id="create-assistant", name="create-assistant")]
    ):
        return asyncio.run(
            tool.execute(
                {"command": "python resources/list_roles.py", "skill_id": "create-assistant"}
            )
        )


def test_missing_resource_returns_clear_error() -> None:
    obs = _run_exec(_build_tool(_MissingResourceStore()))
    assert obs.success is False
    assert _RESOURCE in (obs.error or "")
    assert "请重新安装该技能后再试" in (obs.error or "")


def test_complete_resources_skip_guard() -> None:
    tool = _build_tool(_CompleteResourceStore())
    with (
        patch(
            "lca.infrastructure.tools.skills.exec.tool.ensure_sandbox_runtime",
            side_effect=RuntimeError("no run scope"),
        ),
        pytest.raises(RuntimeError, match="no run scope"),
    ):
        _run_exec(tool)
