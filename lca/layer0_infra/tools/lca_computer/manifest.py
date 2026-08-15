"""lca-computer manifest — declarative tool identity + API surface.

LobeHub alignment:
  - ``MACHINE_MANIFEST``   → ``lobe-local-system``   (12 file/shell/code APIs)
  - ``CLOUD_SANDBOX_MANIFEST`` → ``lobe-cloud-sandbox`` (13 + exportFile)

Shared API modules live under ``apis/``.
"""

from __future__ import annotations

from collections.abc import Iterable

from lca.contracts.models.core.tool import ToolApi, ToolManifest, ToolMeta
from lca.layer0_infra.tools.lca_computer.apis import edit_file as _edit_file
from lca.layer0_infra.tools.lca_computer.apis import execute_code as _execute_code
from lca.layer0_infra.tools.lca_computer.apis import export_file as _export_file
from lca.layer0_infra.tools.lca_computer.apis import get_command_output as _get_command_output
from lca.layer0_infra.tools.lca_computer.apis import glob_files as _glob_files
from lca.layer0_infra.tools.lca_computer.apis import grep_content as _grep_content
from lca.layer0_infra.tools.lca_computer.apis import kill_command as _kill_command
from lca.layer0_infra.tools.lca_computer.apis import list_files as _list_files
from lca.layer0_infra.tools.lca_computer.apis import move_files as _move_files
from lca.layer0_infra.tools.lca_computer.apis import read_file as _read_file
from lca.layer0_infra.tools.lca_computer.apis import run_command as _run_command
from lca.layer0_infra.tools.lca_computer.apis import search_files as _search_files
from lca.layer0_infra.tools.lca_computer.apis import write_file as _write_file
from lca.layer0_infra.tools.lca_computer.types import SANDBOX_ONLY_APIS, ApiName

LOCAL_SYSTEM_ID = "lobe-local-system"
CLOUD_SANDBOX_ID = "lobe-cloud-sandbox"

# Backward compat — callers that imported IDENTIFIER meant cloud-sandbox face.
IDENTIFIER = CLOUD_SANDBOX_ID

_MACHINE_META = ToolMeta(
    avatar="📁",
    title="Local Computer",
    description="在本地机器上访问文件与执行 shell 命令",
)

_CLOUD_META = ToolMeta(
    avatar="📦",
    title="Cloud Sandbox",
    description="在云端沙箱中访问文件、执行命令与运行代码",
)

_ALL_API_SPECS: dict[ApiName, tuple[str, bool]] = {
    ApiName.LIST_FILES: (_list_files.DESCRIPTION, _list_files.IS_IDEMPOTENT),
    ApiName.READ_FILE: (_read_file.DESCRIPTION, _read_file.IS_IDEMPOTENT),
    ApiName.WRITE_FILE: (_write_file.DESCRIPTION, _write_file.IS_IDEMPOTENT),
    ApiName.EDIT_FILE: (_edit_file.DESCRIPTION, _edit_file.IS_IDEMPOTENT),
    ApiName.SEARCH_FILES: (_search_files.DESCRIPTION, _search_files.IS_IDEMPOTENT),
    ApiName.MOVE_FILES: (_move_files.DESCRIPTION, _move_files.IS_IDEMPOTENT),
    ApiName.GREP_CONTENT: (_grep_content.DESCRIPTION, _grep_content.IS_IDEMPOTENT),
    ApiName.GLOB_FILES: (_glob_files.DESCRIPTION, _glob_files.IS_IDEMPOTENT),
    ApiName.RUN_COMMAND: (_run_command.DESCRIPTION, _run_command.IS_IDEMPOTENT),
    ApiName.GET_COMMAND_OUTPUT: (
        _get_command_output.DESCRIPTION,
        _get_command_output.IS_IDEMPOTENT,
    ),
    ApiName.KILL_COMMAND: (_kill_command.DESCRIPTION, _kill_command.IS_IDEMPOTENT),
    ApiName.EXECUTE_CODE: (_execute_code.DESCRIPTION, _execute_code.IS_IDEMPOTENT),
    ApiName.EXPORT_FILE: (_export_file.DESCRIPTION, _export_file.IS_IDEMPOTENT),
}

_PARAM_BUILDERS = {
    ApiName.LIST_FILES: _list_files.parameters,
    ApiName.READ_FILE: _read_file.parameters,
    ApiName.WRITE_FILE: _write_file.parameters,
    ApiName.EDIT_FILE: _edit_file.parameters,
    ApiName.SEARCH_FILES: _search_files.parameters,
    ApiName.MOVE_FILES: _move_files.parameters,
    ApiName.GREP_CONTENT: _grep_content.parameters,
    ApiName.GLOB_FILES: _glob_files.parameters,
    ApiName.RUN_COMMAND: _run_command.parameters,
    ApiName.GET_COMMAND_OUTPUT: _get_command_output.parameters,
    ApiName.KILL_COMMAND: _kill_command.parameters,
    ApiName.EXECUTE_CODE: _execute_code.parameters,
    ApiName.EXPORT_FILE: _export_file.parameters,
}


def _apis_for(names: Iterable[ApiName]) -> tuple[ToolApi, ...]:
    out: list[ToolApi] = []
    for name in names:
        desc, idempotent = _ALL_API_SPECS[name]
        out.append(
            ToolApi(
                name=name,
                description=desc,
                parameters=_PARAM_BUILDERS[name](),
                is_idempotent=idempotent,
            )
        )
    return tuple(out)


_MACHINE_API_NAMES: tuple[ApiName, ...] = tuple(
    api for api in ApiName if api not in SANDBOX_ONLY_APIS
)

MACHINE_MANIFEST = ToolManifest(
    identifier=LOCAL_SYSTEM_ID,
    type="builtin",
    api=_apis_for(_MACHINE_API_NAMES),
    executors=("client", "server"),
    meta=_MACHINE_META,
)

CLOUD_SANDBOX_MANIFEST = ToolManifest(
    identifier=CLOUD_SANDBOX_ID,
    type="builtin",
    api=_apis_for(ApiName),
    executors=("client", "server"),
    meta=_CLOUD_META,
)

# Legacy alias — cloud-sandbox full face (13 APIs).
MANIFEST = CLOUD_SANDBOX_MANIFEST
