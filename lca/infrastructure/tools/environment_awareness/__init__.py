"""environment_awareness tool — lets the reasoner discover execution environments.

The tool reads the execution-environment catalog (SSOT read model) so the
agent can answer "which machines can I operate on" and "where am I running"
even when the current run is bound to a cloud sandbox. It is always included
in the default tool set, independent of the bound plane.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, cast

from lca.contracts.atoms.ids.ids import new_id
from lca.contracts.models.core.execution.decision import Observation
from lca.contracts.models.core.execution.tool import ToolApi, ToolManifest, ToolMeta
from lca.contracts.protocols import Tool
from lca.contracts.protocols.runtime.environment import EnvironmentCatalog
from lca.infrastructure.tools.builder.builder import build_tools_from_manifest

IDENTIFIER = "lca-environment-awareness"
API_NAME = "listEnvironments"

MANIFEST = ToolManifest(
    identifier=IDENTIFIER,
    type="builtin",
    api=(
        ToolApi(
            name=API_NAME,
            description=(
                "列出当前可用的执行环境：当前平面（云端沙箱或绑定的本地电脑）"
                "以及所有已配对成功的设备（含在线状态）。"
                "当用户询问你在哪台机器上运行、有哪些设备/机器可用、"
                "能否操作某台电脑时使用。"
            ),
            parameters={
                "type": "object",
                "properties": {},
            },
            is_idempotent=True,
            effects="read",
        ),
    ),
    meta=ToolMeta(
        avatar="🖥️",
        title="Environments",
        description="List available execution environments",
    ),
)


class EnvironmentAwarenessExecutor:
    """Read environments from the catalog and project them for the model."""

    def __init__(self, catalog: EnvironmentCatalog | None = None) -> None:
        self._catalog = catalog

    async def invoke(self, api_name: str, params: dict[str, Any]) -> Observation:
        if api_name != API_NAME:
            return Observation(
                observation_id=new_id("obs"),
                success=False,
                payload=None,
                error=f"unknown apiName: {api_name}",
                latency_ms=0,
            )
        return await self._list_environments(params)

    async def _list_environments(self, params: dict[str, Any]) -> Observation:
        del params  # no arguments
        start = time.monotonic()
        if self._catalog is None:
            return Observation(
                observation_id=new_id("obs"),
                success=True,
                payload={"current": None, "environments": []},
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        current = self._catalog.current()
        environments = [env.to_dict() for env in self._catalog.list_all()]
        return Observation(
            observation_id=new_id("obs"),
            success=True,
            payload={
                "current": current.to_dict() if current is not None else None,
                "environments": environments,
            },
            latency_ms=int((time.monotonic() - start) * 1000),
        )


def _invoke_via_executor(
    executor: EnvironmentAwarenessExecutor, api_name: str, params: dict[str, Any]
) -> Awaitable[Observation]:
    return executor.invoke(api_name, params)


def build_tools(catalog: EnvironmentCatalog | None = None) -> list[Tool]:
    return build_tools_from_manifest(
        MANIFEST,
        EnvironmentAwarenessExecutor(catalog),
        invoke_fn=cast(
            "Callable[[object, str, dict[str, Any]], Awaitable[Any]]", _invoke_via_executor
        ),
    )


__all__ = ["API_NAME", "IDENTIFIER", "MANIFEST", "build_tools"]
