"""run_skill_script — execScript with skill bundle mounted (LobeHub-aligned)."""

from __future__ import annotations

import time
from typing import Any, ClassVar

from lca.contracts.atoms.ids import new_id
from lca.contracts.atoms.semantic_keys import FAILURE_KIND, FAILURE_KIND_VALIDATION
from lca.contracts.models.core.decision import Observation
from lca.contracts.models.core.sandbox import DEFAULT_SANDBOX_TIMEOUT_S
from lca.contracts.protocols import Sandbox, Tool
from lca.contracts.protocols.operational_skills import (
    SANDBOX_SKILL_MOUNT_PREFIX,
    SkillNotFoundError,
    SkillPackageStore,
)
from lca.infrastructure.file_store import FileStore, LocalFileStore
from lca.infrastructure.sandbox.runtime_scope import ensure_sandbox_runtime
from lca.infrastructure.skills.activation_scope import resolve_skill_for_exec
from lca.infrastructure.skills.exec_bootstrap import build_skill_exec_code
from lca.infrastructure.tools.contract.render import RenderContract, contract
from lca.infrastructure.tools.contract.schema import COMMON
from lca.infrastructure.tools.run_attachment_scope import get_current_run_attachment_ids
from lca.infrastructure.tools.sandbox_exec_observation import build_exec_observation
from lca.infrastructure.tools.tool_invocation_scope import get_current_tool_invocation_id

RUN_SKILL_SCRIPT_TOOL = "run_skill_script"


@contract(
    RenderContract(
        tool_name="run_skill_script",
        identifier="lobe-skills",
        api_name="execScript",
        args=(
            COMMON["command"],
            COMMON["skill_id"],
            COMMON["description"],
            COMMON["timeout_s"],
        ),
        state=(
            COMMON["execution_env"],
            COMMON["files"],
            COMMON["stdout"],
            COMMON["stderr"],
            COMMON["exit_code"],
            COMMON["error_summary"],
            COMMON["error_kind"],
            COMMON["skill_id"],
            COMMON["command"],
        ),
    )
)
class SkillExecTool(Tool):
    name = RUN_SKILL_SCRIPT_TOOL
    description = (
        "在已激活 skill 的工作目录中执行 shell 命令（execScript）。"
        "需先 activate_skill；附件已挂载到工作根/<文件名>。"
        "分析 Excel/CSV 等：先 activate 对应 skill，再在此执行 skill 文档中的命令或脚本。"
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
        file_store: FileStore | LocalFileStore,
    ) -> None:
        self._sandbox = sandbox
        self._store = store
        self._file_store = file_store

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
        prefix = f"{SANDBOX_SKILL_MOUNT_PREFIX}/{activated.skill_id}"
        mounts = {f"{prefix}/{rel}": data for rel, data in resources.items()}
        invocation_id = get_current_tool_invocation_id() or new_id("skl")

        runtime = await ensure_sandbox_runtime(
            self._sandbox,
            self._file_store,
            attachment_ids=get_current_run_attachment_ids(),
        )
        result = await runtime.execute(
            code,
            language="python",
            timeout_s=timeout_s,
            invocation_id=invocation_id,
            extra_files=mounts or None,
        )

        obs = build_exec_observation(
            self._file_store,
            result,
            invocation_id,
            start,
            tool_name=RUN_SKILL_SCRIPT_TOOL,
        )
        if isinstance(obs.payload, dict):
            obs.payload["skill_id"] = activated.skill_id
            obs.payload["command"] = command
        return obs
