"""Wire tool call classification — the anti-corruption layer's observable contract.

Every case drives ``ToolCall`` the way a Decision producer does and asserts a
literal verdict, so a drift between the manifest's wire names and the policy's
operation names fails here rather than at runtime.
"""

from __future__ import annotations

from lca.contracts.models.core.execution.decision import ToolCall
from lca.contracts.models.core.execution.local_exec import AccessReason, AccessVerdict
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.access.classify import (
    call_paths,
    decide_tool_call,
    machine_operation,
    tool_calls_need_approval,
)

_ROOT = "F:\\下载"
_HOME = "C:\\Users\\li"
_CLASH_CONFIG = (
    "C:\\Users\\li\\AppData\\Roaming\\io.github.clash-verge-rev.clash-verge-rev\\verge.yaml"
)
_SSH_KEY = "C:\\Users\\li\\.ssh\\id_rsa"


def _machine() -> PlaneRef:
    return PlaneRef(
        id="m-lipcmain",
        label="lipcmain",
        kind=PlaneKind.MACHINE,
        root=_ROOT,
        outputs_dir=f"{_ROOT}\\outputs",
        platform="Windows",
        home=_HOME,
    )


def _sandbox() -> PlaneRef:
    return PlaneRef(
        id="sb-1",
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root="/mnt/data",
        outputs_dir="/mnt/data/outputs",
    )


def _call(tool_name: str, **arguments: object) -> ToolCall:
    return ToolCall(call_id="call-1", tool_name=tool_name, arguments=dict(arguments))


def test_wire_names_map_to_policy_operations() -> None:
    assert machine_operation("local_readFile") == "read_file"
    assert machine_operation("local_listFiles") == "list_files"
    assert machine_operation("local_runCommand") == "run_command"
    assert machine_operation("local_moveFiles") == "move_files"
    assert machine_operation("local_killCommand") == "kill_command"


def test_non_machine_tools_are_not_this_layer_opinion() -> None:
    assert machine_operation("search") is None
    assert machine_operation("askUserQuestion") is None
    assert machine_operation("readFile") is None


def test_call_paths_reads_camel_and_snake_keys() -> None:
    assert call_paths("list_files", {"directoryPath": "C:\\a"}) == ["C:\\a"]
    assert call_paths("list_files", {"directory_path": "C:\\a"}) == ["C:\\a"]
    assert call_paths("read_file", {"path": "C:\\a\\b.txt"}) == ["C:\\a\\b.txt"]


def test_call_paths_collects_both_move_endpoints() -> None:
    arguments = {"operations": [{"source": "C:\\a.txt", "destination": "C:\\b.txt"}]}
    assert call_paths("move_files", arguments) == ["C:\\a.txt", "C:\\b.txt"]


def test_call_paths_is_empty_for_commands() -> None:
    assert call_paths("run_command", {"command": "tasklist"}) == []


def test_decide_tool_call_returns_none_without_a_machine_plane() -> None:
    assert decide_tool_call("local_readFile", {"path": _CLASH_CONFIG}, plane=None) is None
    assert decide_tool_call("search", {"query": "x"}, plane=_machine()) is None


def test_original_failing_read_is_allowed() -> None:
    decision = decide_tool_call("local_readFile", {"path": _CLASH_CONFIG}, plane=_machine())
    assert decision is not None
    assert decision.verdict is AccessVerdict.ALLOW
    assert decision.reason is AccessReason.IN_GRANT


def test_credential_read_needs_approval() -> None:
    decision = decide_tool_call("local_readFile", {"path": _SSH_KEY}, plane=_machine())
    assert decision is not None
    assert decision.verdict is AccessVerdict.NEEDS_APPROVAL
    assert decision.reason is AccessReason.CREDENTIAL_PATH


def test_credential_write_is_denied() -> None:
    decision = decide_tool_call(
        "local_writeFile", {"path": _SSH_KEY, "content": "x"}, plane=_machine()
    )
    assert decision is not None
    assert decision.verdict is AccessVerdict.DENY
    assert decision.reason is AccessReason.CREDENTIAL_PATH


def test_write_inside_working_root_is_allowed() -> None:
    decision = decide_tool_call(
        "local_writeFile",
        {"path": "F:\\下载\\outputs\\report.md", "content": "x"},
        plane=_machine(),
    )
    assert decision is not None
    assert decision.verdict is AccessVerdict.ALLOW


def test_read_only_command_is_allowed_but_compound_is_not() -> None:
    allowed = decide_tool_call("local_runCommand", {"command": "tasklist"}, plane=_machine())
    blocked = decide_tool_call(
        "local_runCommand", {"command": "tasklist && del C:\\a.txt"}, plane=_machine()
    )
    assert allowed is not None and allowed.verdict is AccessVerdict.ALLOW
    assert blocked is not None and blocked.verdict is AccessVerdict.NEEDS_APPROVAL
    assert blocked.reason is AccessReason.COMMAND_NOT_ALLOWED


def test_sandbox_plane_is_not_gated_by_this_layer() -> None:
    assert (
        tool_calls_need_approval([_call("local_readFile", path="/etc/passwd")], _sandbox()) is False
    )


def test_batch_pauses_when_any_call_needs_approval() -> None:
    calls = [
        _call("local_readFile", path=_CLASH_CONFIG),
        _call("local_readFile", path=_SSH_KEY),
    ]
    assert tool_calls_need_approval(calls, _machine()) is True


def test_batch_of_allowed_calls_does_not_pause() -> None:
    calls = [
        _call("local_readFile", path=_CLASH_CONFIG),
        _call("local_listFiles", directoryPath=_ROOT),
        _call("local_runCommand", command="tasklist"),
    ]
    assert tool_calls_need_approval(calls, _machine()) is False


def test_non_machine_tools_never_pause_through_this_layer() -> None:
    assert tool_calls_need_approval([_call("search", query="x")], _machine()) is False


def test_malformed_input_is_not_an_error() -> None:
    assert tool_calls_need_approval(None, _machine()) is False
    assert tool_calls_need_approval("local_readFile", _machine()) is False
    assert tool_calls_need_approval([object()], _machine()) is False
    assert tool_calls_need_approval([_call("local_readFile")], _machine()) is False


def test_no_plane_means_no_opinion() -> None:
    assert tool_calls_need_approval([_call("local_readFile", path=_SSH_KEY)], None) is False
