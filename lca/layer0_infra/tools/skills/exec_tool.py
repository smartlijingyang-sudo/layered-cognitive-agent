"""run_skill_script — execScript with skill bundle mounted in sandbox."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.sandbox import DEFAULT_SANDBOX_TIMEOUT_S
from lca.contracts.protocols import Sandbox, Tool
from lca.contracts.protocols.operational_skills import SkillNotFoundError, SkillPackageStore
from lca.layer0_infra.file_store import FileStore, LocalFileStore, get_default_file_store
from lca.layer0_infra.skills.activation_scope import resolve_skill_for_exec
from lca.layer0_infra.skills.exec_bootstrap import build_skill_exec_code, skill_mount_files
from lca.layer0_infra.tools.sandbox_observation import build_observation
from lca.layer0_infra.tools.tool_invocation_scope import get_current_tool_invocation_id

RUN_SKILL_SCRIPT_TOOL = "run_skill_script"


class SkillExecTool(Tool):
    name = RUN_SKILL_SCRIPT_TOOL
    description = (
        "在沙箱中执行 skill 捆绑脚本/命令：自动挂载 skill 资源目录为 cwd，"
        "可选安装 requirements.txt。需先 activate_skill。"
        "参数: command（shell 命令）、skill_id（可选，默认最近激活）、"
        "install_requirements（可选，默认 true）、timeout_s。"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要在 skill 目录下执行的 shell 命令"},
            "skill_id": {"type": "string", "description": "可选；默认取最近 activate 的 skill"},
            "install_requirements": {"type": "boolean", "default": True},
            "timeout_s": {"type": "integer", "default": DEFAULT_SANDBOX_TIMEOUT_S},
        },
        "required": ["command"],
    }
    is_idempotent = False
    default_timeout_s = DEFAULT_SANDBOX_TIMEOUT_S

    def __init__(
        self,
        *,
        sandbox: Sandbox,
        store: SkillPackageStore,
        file_store: FileStore | LocalFileStore | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._store = store
        self._file_store: FileStore = (
            file_store if file_store is not None else get_default_file_store()
        )

    def validate(self, args: dict[str, Any]) -> str | None:
        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            return "command 必须是非空字符串"
        return None

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        command = str(args["command"]).strip()
        skill_id_arg = str(args.get("skill_id") or "").strip() or None
        install_req = bool(args.get("install_requirements", True))
        timeout_raw = args.get("timeout_s", DEFAULT_SANDBOX_TIMEOUT_S)
        try:
            timeout_s = int(timeout_raw)
        except (TypeError, ValueError):
            timeout_s = DEFAULT_SANDBOX_TIMEOUT_S

        try:
            activated = resolve_skill_for_exec(skill_id_arg)
            resources = self._store.resource_files(activated.skill_id)
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

        code = build_skill_exec_code(
            skill_id=activated.skill_id,
            command=command,
            install_requirements=install_req,
        )
        mounts = skill_mount_files(activated.skill_id, resources)
        invocation_id = get_current_tool_invocation_id() or new_id("skl")
        result = await self._sandbox.run(
            code=code,
            language="python",
            files=mounts or None,
            timeout_s=timeout_s,
            invocation_id=invocation_id,
        )

        obs = build_observation(self._file_store, result, invocation_id, start)
        if isinstance(obs.payload, dict):
            obs.payload["skill_id"] = activated.skill_id
            obs.payload["command"] = command
        return obs
