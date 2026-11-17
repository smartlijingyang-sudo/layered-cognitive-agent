"""Mangli 企业级工具实现与插件声明（符合 Tool 协议与 C10 执行窄门）。"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from lca.contracts.atoms.control.slot import ControlSlot
from lca.contracts.atoms.functional.group import FunctionalGroup
from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.atoms.scope.scope import Scope
from lca.contracts.harness.composition.plugin_contract import (
    ArchitectureContract,
    AuthorityContract,
    EvidenceContract,
    LifecycleContract,
    PluginContract,
    PluginIdentity,
)
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.contracts.protocols.declarative.declarative_2.declarative_plugin import (
    OwnershipDeclaration,
)
from lca.harness.plugin_api import PluginContext, PluginKind, plugin
from lca.infrastructure.file.store import FileStore

IDENTIFIER = "mangli-enterprise-tools"

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name="mangli_workspace_export",
            description="将分析产物或生成文件导出至工作区沙箱，并生成企业端专属文件下载凭证",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "导出目标文件名（例如 report.csv 或 summary.txt）"
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": "导出的文本或报告正文内容",
                    },
                },
                "required": ["path", "content"],
            },
            is_idempotent=False,
            default_timeout_ms=30_000,
            effects="write",
            namespace="workspace",
        ),
    ),
    meta=ToolMeta(
        avatar="📦",
        title="mangli_workspace_export",
        description="Mangli workspace file export tool",
    ),
)


class MangliWorkspaceExportTool(Tool):
    """企业工作区文件导出工具，严格遵循 LCA Tool(Protocol) 契约规范。"""

    name: ClassVar[str] = "mangli_workspace_export"
    namespace: ClassVar[str] = "workspace"
    description: ClassVar[str] = (
        "将分析产物或生成文件导出至工作区沙箱，并生成企业端专属文件下载凭证"
    )
    parameters: ClassVar[dict[str, Any]] = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": (
                    "导出目标文件名（例如 report.csv 或 summary.txt）"
                ),
            },
            "content": {
                "type": "string",
                "description": "导出的文本或报告正文内容",
            },
        },
        "required": ["path", "content"],
    }
    is_idempotent: ClassVar[bool] = False
    effect_kind: ClassVar[Literal["ephemeral", "persistent", "stateful_once"]] = (
        "persistent"
    )
    default_timeout_s: ClassVar[int] = 30

    def __init__(
        self,
        file_store: FileStore | None = None,
        user_id: str = "",
        project_id: str = "",
        session_id: str = "",
    ) -> None:
        self.file_store = file_store
        self.user_id = user_id
        self.project_id = project_id
        self.session_id = session_id

    async def execute(self, args: dict[str, Any]) -> Observation:
        start = time.monotonic()
        path_str = str(args.get("path", "")).strip()
        content = args.get("content", "")

        if not path_str:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error="path 参数不能为空",
                latency_ms=int((time.monotonic() - start) * 1000),
            )

        filename = Path(path_str).name
        data_bytes = (
            content.encode("utf-8")
            if isinstance(content, str)
            else bytes(content)
        )

        attachment_id = ""
        download_url = ""

        if self.file_store is not None:
            stored = self.file_store.put(
                data=data_bytes,
                name=filename,
                mime_type="text/plain",
                origin="agent_created",
            )
            attachment_id = stored.attachment_id
            download_url = f"/files/{attachment_id}"

        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "status": "ok",
                "attachment_id": attachment_id,
                "download_url": download_url,
                "path": path_str,
                "size_bytes": len(data_bytes),
                "project_id": self.project_id,
            },
            error=None,
            latency_ms=int((time.monotonic() - start) * 1000),
        )


class Config(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool = True


@plugin(
    id="mangli-enterprise-tools",
    layer="L1",
    kind=PluginKind.PROVIDER,
    effects="none",
    provides=["mangli_enterprise_tools"],
    requires=["tools"],
    description="Mangli 企业级工具集合插件",
    contract=PluginContract(
        identity=PluginIdentity(version="v1"),
        architecture=ArchitectureContract(
            group=FunctionalGroup.G7_EXECUTION,
            control_slots=(ControlSlot.OBSERVE_WILDCARD,),
        ),
        lifecycle=LifecycleContract(allowed_scopes=(Scope.RUN,)),
        authority=AuthorityContract(grants=("tool.invoke",)),
        observability=EvidenceContract(
            descriptors=("mangli-enterprise-tools.served",)
        ),
    ),
    ownership=OwnershipDeclaration(
        reads=("tool.invoke",),
        emits=("mangli-enterprise-tools.served",),
        state_mutation="forbidden",
    ),
)
async def setup(ctx: PluginContext, config: Config) -> None:
    if not config.enabled:
        return

    try:
        tools_service = ctx.require("tools")
    except (KeyError, LookupError):
        return

    def _factory(bindings: Any) -> list[Tool]:
        file_store = getattr(bindings, "file_store", None)
        return [MangliWorkspaceExportTool(file_store=file_store)]

    tools_service.register_factory("mangli_enterprise", _factory)


__all__ = [
    "IDENTIFIER",
    "MANIFEST",
    "MangliWorkspaceExportTool",
    "setup",
]
