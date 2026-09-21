"""Machine-plane access policy — verdicts for the real failing scenario.

Every case calls ``decide_access`` the way the local-exec port will and asserts
a literal verdict, so a regression in the tables shows up as a changed value.
"""

from __future__ import annotations

import time

from lca.contracts.models.core.execution.local_exec import (
    AccessReason,
    AccessScope,
    AccessVerdict,
    access_scope_of,
)
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.access import (
    DEFAULT_READ_ONLY_COMMANDS,
    decide_access,
    default_access_scope,
    default_machine_grant,
    is_credential_path,
    readable_prefixes,
    subcommands,
)

_EXPIRES = int(time.time()) + 3600

#: The plane from run_5fd426ea0367, where a clash config read failed the run.
_WINDOWS_ROOT = "F:\\下载"
_WINDOWS_HOME = "C:\\Users\\li"
_CLASH_CONFIG = (
    "C:\\Users\\li\\AppData\\Roaming\\io.github.clash-verge-rev.clash-verge-rev\\verge.yaml"
)


def _windows_plane() -> PlaneRef:
    return PlaneRef(
        id="m-lipcmain",
        label="lipcmain",
        kind=PlaneKind.MACHINE,
        root=_WINDOWS_ROOT,
        outputs_dir=f"{_WINDOWS_ROOT}\\outputs",
        platform="Windows",
        home=_WINDOWS_HOME,
    )


def _posix_plane() -> PlaneRef:
    return PlaneRef(
        id="m-dev",
        label="dev",
        kind=PlaneKind.MACHINE,
        root="/home/lca/work",
        outputs_dir="/home/lca/work/outputs",
        platform="linux",
        home="/home/lca",
    )


def _scope(plane: PlaneRef, operation: str, **overrides: object) -> AccessScope:
    scope = default_access_scope(plane, operation)
    return scope.model_copy(update=overrides) if overrides else scope


def _verdict(operation: str, plane: PlaneRef, **kwargs: object) -> AccessVerdict:
    scope = kwargs.pop("scope", None) or _scope(plane, operation)
    return decide_access(operation, scope=scope, plane=plane, **kwargs).verdict  # type: ignore[arg-type]


def test_default_read_scope_is_working_root_plus_home() -> None:
    assert readable_prefixes(_windows_plane()) == (_WINDOWS_ROOT, _WINDOWS_HOME)


def test_access_scope_of_projects_only_the_authorization_fields() -> None:
    grant = default_machine_grant(
        _windows_plane(),
        operation="read_file",
        job_id="job-1",
        idempotency_key="idem-1",
        subject_user_id="u-1",
        expires_at=_EXPIRES,
        approval_id="ap-1",
        request_digest="d-1",
    )
    scope = access_scope_of(grant)
    assert scope.operation == "read_file"
    assert scope.path_prefixes == (_WINDOWS_ROOT, _WINDOWS_HOME)
    assert scope.command_allowlist == DEFAULT_READ_ONLY_COMMANDS
    assert scope.command_class is None
    assert set(AccessScope.model_fields) == {
        "operation",
        "path_prefixes",
        "command_allowlist",
        "command_class",
    }


def test_read_of_home_config_is_allowed() -> None:
    """The run_5fd426ea0367 failure: a clash config under the user's home."""
    assert _verdict("read_file", _windows_plane(), paths=[_CLASH_CONFIG]) is AccessVerdict.ALLOW


def test_read_outside_grant_needs_approval() -> None:
    assert (
        _verdict("read_file", _windows_plane(), paths=["D:\\other\\notes.md"])
        is AccessVerdict.NEEDS_APPROVAL
    )


def test_read_of_secret_inside_home_needs_approval() -> None:
    decision = decide_access(
        "read_file",
        scope=_scope(_windows_plane(), "read_file"),
        plane=_windows_plane(),
        paths=["C:\\Users\\li\\.ssh\\id_rsa"],
    )
    assert decision.verdict is AccessVerdict.NEEDS_APPROVAL
    assert decision.reason is AccessReason.CREDENTIAL_PATH


def test_read_via_parent_segment_escape_needs_approval() -> None:
    assert (
        _verdict("read_file", _windows_plane(), paths=["F:\\下载\\..\\secret.txt"])
        is AccessVerdict.NEEDS_APPROVAL
    )


def test_read_of_temp_path_is_allowed() -> None:
    assert (
        _verdict("read_file", _windows_plane(), paths=["C:\\Users\\li\\AppData\\Local\\Temp\\x"])
        is AccessVerdict.ALLOW
    )


def test_write_inside_working_root_is_allowed() -> None:
    assert (
        _verdict("write_file", _windows_plane(), paths=["F:\\下载\\outputs\\report.md"])
        is AccessVerdict.ALLOW
    )


def test_write_inside_home_but_outside_working_root_needs_approval() -> None:
    assert (
        _verdict("write_file", _windows_plane(), paths=["C:\\Users\\li\\notes.md"])
        is AccessVerdict.NEEDS_APPROVAL
    )


def test_write_to_credential_path_is_denied() -> None:
    decision = decide_access(
        "edit_file",
        scope=_scope(_windows_plane(), "edit_file"),
        plane=_windows_plane(),
        paths=["C:\\Users\\li\\.aws\\credentials"],
    )
    assert decision.verdict is AccessVerdict.DENY
    assert decision.reason is AccessReason.CREDENTIAL_PATH


def test_move_takes_the_stricter_of_source_and_destination() -> None:
    assert (
        _verdict(
            "move_files",
            _windows_plane(),
            paths=["F:\\下载\\a.txt", "C:\\Users\\li\\b.txt"],
        )
        is AccessVerdict.NEEDS_APPROVAL
    )


def test_posix_read_inside_home_is_allowed() -> None:
    assert (
        _verdict("read_file", _posix_plane(), paths=["/home/lca/.config/app.toml"])
        is AccessVerdict.ALLOW
    )


def test_posix_parent_escape_needs_approval() -> None:
    assert (
        _verdict("read_file", _posix_plane(), paths=["/home/lca/work/../../etc/passwd"])
        is AccessVerdict.NEEDS_APPROVAL
    )


def test_read_only_command_is_allowed() -> None:
    command = 'tasklist /FI "IMAGENAME eq clash*"'
    assert _verdict("run_command", _windows_plane(), command=command) is AccessVerdict.ALLOW


def test_compound_command_hiding_a_write_needs_approval() -> None:
    command = "tasklist && del C:\\Users\\li\\notes.md"
    assert (
        _verdict("run_command", _windows_plane(), command=command) is AccessVerdict.NEEDS_APPROVAL
    )


def test_command_outside_allowlist_needs_approval() -> None:
    assert (
        _verdict("run_command", _windows_plane(), command="curl http://127.0.0.1:9090")
        is AccessVerdict.NEEDS_APPROVAL
    )


def test_empty_allowlist_needs_approval() -> None:
    scope = _scope(_windows_plane(), "run_command", command_allowlist=())
    assert (
        _verdict("run_command", _windows_plane(), command="tasklist", scope=scope)
        is AccessVerdict.NEEDS_APPROVAL
    )


def test_job_continuation_is_allowed() -> None:
    assert _verdict("get_command_output", _windows_plane()) is AccessVerdict.ALLOW
    assert _verdict("kill_command", _windows_plane()) is AccessVerdict.ALLOW


def test_sandbox_plane_is_not_gated_twice() -> None:
    sandbox = PlaneRef(
        id="sb-1",
        label="Onlyboxes",
        kind=PlaneKind.SANDBOX,
        root="/mnt/data",
        outputs_dir="/mnt/data/outputs",
    )
    decision = decide_access(
        "write_file",
        scope=_scope(sandbox, "write_file"),
        plane=sandbox,
        paths=["/etc/passwd"],
    )
    assert decision.verdict is AccessVerdict.ALLOW
    assert decision.reason is AccessReason.NOT_A_MACHINE


def test_scope_for_another_operation_is_denied() -> None:
    scope = _scope(_windows_plane(), "read_file")
    decision = decide_access(
        "write_file", scope=scope, plane=_windows_plane(), paths=["F:\\下载\\a.txt"]
    )
    assert decision.verdict is AccessVerdict.DENY
    assert decision.reason is AccessReason.OPERATION_NOT_GRANTED


def test_unclassified_operation_defaults_to_consent() -> None:
    assert (
        _verdict("export_file", _windows_plane(), paths=["F:\\下载\\a.txt"])
        is AccessVerdict.NEEDS_APPROVAL
    )


def test_secret_detection_matches_names_extensions_and_dirs() -> None:
    assert is_credential_path("C:\\Users\\li\\.ssh\\id_rsa")
    assert is_credential_path("/home/lca/project/.env")
    assert is_credential_path("/home/lca/certs/server.pem")
    assert is_credential_path("/home/lca/.aws/credentials")
    assert not is_credential_path("F:\\下载\\notes.md")
    assert not is_credential_path("/home/lca/project/README.md")


def test_subcommands_split_on_every_separator() -> None:
    assert subcommands("tasklist && dir") == ("tasklist", "dir")
    assert subcommands("ls | wc -l") == ("ls", "wc -l")
    assert subcommands("a; b\nc") == ("a", "b", "c")
    assert subcommands("tasklist") == ("tasklist",)
