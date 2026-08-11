"""Computer tool specs — names, schemas, and handler registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from lca.contracts.models.core.sandbox import DEFAULT_SANDBOX_TIMEOUT_S
from lca.layer0_infra.computer.runtime import ComputerOpResult, ComputerRuntime
from lca.layer0_infra.tools.computer.handlers import (
    _op_edit_file,
    _op_execute_code,
    _op_export_file,
    _op_get_command_output,
    _op_glob_files,
    _op_grep_content,
    _op_kill_command,
    _op_list_files,
    _op_move_files,
    _op_read_file,
    _op_run_command,
    _op_search_files,
    _op_write_file,
)

EXECUTE_CODE = "execute_code"
RUN_COMMAND = "run_command"
LIST_FILES = "list_files"
READ_FILE = "read_file"
WRITE_FILE = "write_file"
EDIT_FILE = "edit_file"
SEARCH_FILES = "search_files"
MOVE_FILES = "move_files"
GREP_CONTENT = "grep_content"
GLOB_FILES = "glob_files"
GET_COMMAND_OUTPUT = "get_command_output"
KILL_COMMAND = "kill_command"
EXPORT_FILE = "export_file"

OpFn = Callable[[ComputerRuntime, dict[str, Any]], Awaitable[ComputerOpResult]]


@dataclass(frozen=True)
class ComputerToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: OpFn
    is_idempotent: bool = False
    default_timeout_s: int = DEFAULT_SANDBOX_TIMEOUT_S


_COMPUTER_TOOL_SPECS: tuple[ComputerToolSpec, ...] = (
    ComputerToolSpec(
        name=EXECUTE_CODE,
        description="在隔离沙箱中执行代码。工作区 /mnt/data。参数: description, language, code。",
        parameters={
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "language": {"type": "string", "enum": ["python", "javascript", "typescript"]},
                "code": {"type": "string"},
            },
            "required": ["description", "language", "code"],
        },
        handler=_op_execute_code,
    ),
    ComputerToolSpec(
        name=RUN_COMMAND,
        description="在沙箱执行 shell 命令。参数: description, command, background, timeout。",
        parameters={
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "command": {"type": "string"},
                "background": {"type": "boolean"},
                "timeout": {"type": "number"},
            },
            "required": ["description", "command"],
        },
        handler=_op_run_command,
    ),
    ComputerToolSpec(
        name=LIST_FILES,
        description="列出沙箱目录。参数 directoryPath。",
        parameters={
            "type": "object",
            "properties": {"directoryPath": {"type": "string"}},
            "required": ["directoryPath"],
        },
        handler=_op_list_files,
        is_idempotent=True,
    ),
    ComputerToolSpec(
        name=READ_FILE,
        description="读取沙箱文件。参数 path, startLine, endLine。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "startLine": {"type": "number"},
                "endLine": {"type": "number"},
            },
            "required": ["path"],
        },
        handler=_op_read_file,
        is_idempotent=True,
    ),
    ComputerToolSpec(
        name=WRITE_FILE,
        description="写入沙箱文件。参数 path, content, createDirectories。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "createDirectories": {"type": "boolean"},
            },
            "required": ["path", "content"],
        },
        handler=_op_write_file,
    ),
    ComputerToolSpec(
        name=EDIT_FILE,
        description="精确替换文件内容。参数 path, search, replace, all。",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "search": {"type": "string"},
                "replace": {"type": "string"},
                "all": {"type": "boolean"},
            },
            "required": ["path", "search", "replace"],
        },
        handler=_op_edit_file,
    ),
    ComputerToolSpec(
        name=SEARCH_FILES,
        description="搜索沙箱文件。参数 directory, keyword, fileType。",
        parameters={
            "type": "object",
            "properties": {
                "directory": {"type": "string"},
                "keyword": {"type": "string"},
                "fileType": {"type": "string"},
            },
            "required": ["directory"],
        },
        handler=_op_search_files,
        is_idempotent=True,
    ),
    ComputerToolSpec(
        name=MOVE_FILES,
        description="移动/重命名文件。参数 operations。",
        parameters={
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "destination": {"type": "string"},
                        },
                        "required": ["source", "destination"],
                    },
                },
            },
            "required": ["operations"],
        },
        handler=_op_move_files,
    ),
    ComputerToolSpec(
        name=GREP_CONTENT,
        description="正则搜索内容。参数 pattern, directory。",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "directory": {"type": "string"},
                "filePattern": {"type": "string"},
                "recursive": {"type": "boolean"},
            },
            "required": ["pattern", "directory"],
        },
        handler=_op_grep_content,
        is_idempotent=True,
    ),
    ComputerToolSpec(
        name=GLOB_FILES,
        description="Glob 匹配文件。参数 pattern, directory。",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "directory": {"type": "string"},
            },
            "required": ["pattern"],
        },
        handler=_op_glob_files,
        is_idempotent=True,
    ),
    ComputerToolSpec(
        name=GET_COMMAND_OUTPUT,
        description="获取后台命令输出。参数 commandId。",
        parameters={
            "type": "object",
            "properties": {"commandId": {"type": "string"}},
            "required": ["commandId"],
        },
        handler=_op_get_command_output,
        is_idempotent=True,
    ),
    ComputerToolSpec(
        name=KILL_COMMAND,
        description="终止后台命令。参数 commandId。",
        parameters={
            "type": "object",
            "properties": {"commandId": {"type": "string"}},
            "required": ["commandId"],
        },
        handler=_op_kill_command,
    ),
    ComputerToolSpec(
        name=EXPORT_FILE,
        description="导出沙箱文件供下载。参数 path。",
        parameters={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        handler=_op_export_file,
        is_idempotent=True,
    ),
)
