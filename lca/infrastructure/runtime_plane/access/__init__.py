"""Public exports for ``access`` — the machine-plane authorization boundary."""

from lca.infrastructure.runtime_plane.access.classify import (
    call_paths,
    decide_tool_call,
    machine_calls_need_approval,
    machine_operation,
    tool_calls_need_approval,
)
from lca.infrastructure.runtime_plane.access.grant import (
    DEFAULT_READ_ONLY_COMMANDS,
    default_access_scope,
    default_machine_grant,
    readable_prefixes,
)
from lca.infrastructure.runtime_plane.access.policy import (
    EXEC_OPERATIONS,
    JOB_CONTINUATION_OPERATIONS,
    READ_ONLY_COMMAND_CLASS,
    READ_OPERATIONS,
    WRITE_OPERATIONS,
    classify_path,
    decide_access,
    is_credential_path,
    subcommands,
)

__all__ = [
    "DEFAULT_READ_ONLY_COMMANDS",
    "EXEC_OPERATIONS",
    "JOB_CONTINUATION_OPERATIONS",
    "READ_ONLY_COMMAND_CLASS",
    "READ_OPERATIONS",
    "WRITE_OPERATIONS",
    "call_paths",
    "classify_path",
    "decide_access",
    "decide_tool_call",
    "default_access_scope",
    "default_machine_grant",
    "is_credential_path",
    "machine_calls_need_approval",
    "machine_operation",
    "readable_prefixes",
    "subcommands",
    "tool_calls_need_approval",
]
