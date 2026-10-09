"""RA-095 (b): pin the read-path-only wiring scope of the file_ref_args seam.

The seam's contract is honest: only ``SandboxComputer.read_file`` routes its
path argument through ``resolve_path_arg`` (via
``_resolve_read_path_arg_or_passthrough``). All other guest-path entries
(``write_file`` / ``edit_file`` / ``list_files`` / ``search_files`` /
``move_files``) go straight to ``normalize_sandbox_path``.

This test pins that scope. Widening it to a universal choke point (RA-095
choice (a)) is a conscious, security-reviewed decision — not drift — so it
must update this pin, the module docstring of ``file_ref_args.py``, and the
helper's read-path-only contract.
"""

from __future__ import annotations

import inspect

from lca.infrastructure.computer.sandbox import computer as computer_mod
from lca.infrastructure.computer.sandbox.computer import SandboxComputer

_SEAM_HELPER = "_resolve_read_path_arg_or_passthrough"

# Every SandboxComputer guest entry that takes a path argument.
_PATH_ENTRIES = (
    "read_file",
    "write_file",
    "edit_file",
    "list_files",
    "search_files",
    "move_files",
)


def _wired_entries() -> list[str]:
    wired: list[str] = []
    for name in _PATH_ENTRIES:
        if _SEAM_HELPER in inspect.getsource(getattr(SandboxComputer, name)):
            wired.append(name)
    return wired


def test_only_read_file_flows_through_the_seam() -> None:
    assert _wired_entries() == ["read_file"]


def test_seam_helper_passthrough_for_plain_paths() -> None:
    # UnresolvedFileRefError -> passthrough (ADR-0121): plain workspace paths
    # and unknown attachment ids are untouched even with no file store bound.
    helper = computer_mod._resolve_read_path_arg_or_passthrough
    assert helper("outputs/x.png") == "outputs/x.png"
    assert helper("/files/unknown-aid") == "/files/unknown-aid"
