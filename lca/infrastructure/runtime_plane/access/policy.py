"""Machine-plane access policy — the authorization boundary (ADR-0246 §1.1).

One concept: given an operation, the paths it touches, and a
:class:`CapabilityGrant`, decide ``allow`` / ``needs_approval`` / ``deny``.

Pure and total. No I/O, no exceptions, no runtime state. The caller turns the
verdict into an execution, an ADR-0078 HIL pause, or an
``EffectReceipt(error_kind="scope_violation")``.

Consent is a different boundary and is not decided here. ``NEEDS_APPROVAL``
means "hand this to the HIL state machine", never "refuse".

The read/write asymmetry follows the industry shape recorded in the
``machine-path-authorization-belongs-to-capability-grant`` Agent Note: Codex
confines writes to the workspace while reading accessible files, and Claude
Code frees read-only tools inside the working directory but prompts for every
edit. Secret paths are gated on both sides, as Claude Code's ``Read(./.env)``
specifiers and praison's secret-file read gate do.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from lca.contracts.models.core.execution.local_exec import (
    AccessDecision,
    AccessReason,
    AccessVerdict,
    CapabilityGrant,
)
from lca.contracts.models.core.state.plane import PlaneKind, PlaneRef
from lca.infrastructure.runtime_plane.paths.paths import (
    is_temp_path,
    is_within,
    resolve_plane_path,
    within_any,
)

READ_OPERATIONS = frozenset(
    {"read_file", "list_files", "search_files", "grep_content", "glob_files"}
)
WRITE_OPERATIONS = frozenset({"write_file", "edit_file", "move_files"})
EXEC_OPERATIONS = frozenset({"run_command"})
JOB_CONTINUATION_OPERATIONS = frozenset({"get_command_output", "kill_command"})

READ_ONLY_COMMAND_CLASS = "read_only"

#: Credential file names, matched case-insensitively against the basename.
CREDENTIAL_BASENAMES = frozenset(
    {
        ".env",
        ".npmrc",
        ".netrc",
        ".pgpass",
        ".git-credentials",
        "credentials",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
)

#: Credential file extensions, matched case-insensitively.
CREDENTIAL_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".keystore", ".jks")

#: Directory names that hold credentials, matched case-insensitively per segment.
CREDENTIAL_DIR_SEGMENTS = frozenset({".ssh", ".aws", ".gnupg", ".kube", ".docker"})


class _PathClass:
    """Where a resolved path sits relative to the grant and the working root."""

    CREDENTIAL = "credential"
    TEMP = "temp"
    WORKING_ROOT = "working_root"
    IN_GRANT = "in_grant"
    OUTSIDE = "outside"


#: Verdict per path class for read operations.
_READ_VERDICT: dict[str, tuple[AccessVerdict, AccessReason]] = {
    _PathClass.CREDENTIAL: (AccessVerdict.NEEDS_APPROVAL, AccessReason.CREDENTIAL_PATH),
    _PathClass.TEMP: (AccessVerdict.ALLOW, AccessReason.TEMP_PATH),
    _PathClass.WORKING_ROOT: (AccessVerdict.ALLOW, AccessReason.IN_GRANT),
    _PathClass.IN_GRANT: (AccessVerdict.ALLOW, AccessReason.IN_GRANT),
    _PathClass.OUTSIDE: (AccessVerdict.NEEDS_APPROVAL, AccessReason.OUTSIDE_GRANT),
}

#: Verdict per path class for write operations. Writes stay inside the working
#: root; a path that is merely readable still needs consent to modify.
_WRITE_VERDICT: dict[str, tuple[AccessVerdict, AccessReason]] = {
    _PathClass.CREDENTIAL: (AccessVerdict.DENY, AccessReason.CREDENTIAL_PATH),
    _PathClass.TEMP: (AccessVerdict.ALLOW, AccessReason.TEMP_PATH),
    _PathClass.WORKING_ROOT: (AccessVerdict.ALLOW, AccessReason.IN_GRANT),
    _PathClass.IN_GRANT: (AccessVerdict.NEEDS_APPROVAL, AccessReason.OUTSIDE_WORKING_ROOT),
    _PathClass.OUTSIDE: (AccessVerdict.NEEDS_APPROVAL, AccessReason.OUTSIDE_GRANT),
}

_SEVERITY: dict[AccessVerdict, int] = {
    AccessVerdict.ALLOW: 0,
    AccessVerdict.NEEDS_APPROVAL: 1,
    AccessVerdict.DENY: 2,
}


def is_credential_path(path: str) -> bool:
    """True when the path names a credential file or sits in a credential dir."""
    segments = [segment for segment in path.replace("\\", "/").split("/") if segment]
    if not segments:
        return False
    basename = segments[-1].lower()
    if basename in CREDENTIAL_BASENAMES:
        return True
    if any(basename.endswith(suffix) for suffix in CREDENTIAL_SUFFIXES):
        return True
    return any(segment.lower() in CREDENTIAL_DIR_SEGMENTS for segment in segments[:-1])


def classify_path(path: str, *, grant: CapabilityGrant, plane: PlaneRef) -> str:
    """Order matters: secret first, so a credential inside the grant still gates."""
    if is_credential_path(path):
        return _PathClass.CREDENTIAL
    if is_temp_path(path, plane.platform):
        return _PathClass.TEMP
    if is_within(path, plane.root, plane.platform):
        return _PathClass.WORKING_ROOT
    if within_any(path, tuple(grant.path_prefixes), plane.platform):
        return _PathClass.IN_GRANT
    return _PathClass.OUTSIDE


#: Shell separators that introduce an independently executed subcommand.
#: Ordered so ``&&`` splits before ``&`` and ``||`` before ``|``.
_COMMAND_SEPARATORS = re.compile(r"&&|\|\||\|&|;|\||&|\n")


def subcommands(command: str) -> tuple[str, ...]:
    """Split a command line into its independently executed subcommands.

    Lexical, not a shell parser. Quoting and escaping can still hide a
    separator, which is why an allowlist verdict is one layer and never the
    only one: the receipt and the HIL boundary still apply.
    """
    return tuple(part.strip() for part in _COMMAND_SEPARATORS.split(command) if part.strip())


def _first_token(subcommand: str) -> str:
    return subcommand.split(None, 1)[0].lower() if subcommand else ""


def _decide_command(command: str, grant: CapabilityGrant) -> AccessDecision:
    operation = "run_command"
    parts = subcommands(command)
    if grant.command_allowlist and parts:
        allowed = {entry.strip().lower() for entry in grant.command_allowlist if entry.strip()}
        if all(_first_token(part) in allowed for part in parts):
            return AccessDecision(
                operation=operation,
                verdict=AccessVerdict.ALLOW,
                reason=AccessReason.COMMAND_CLASS,
                detail="every subcommand is in the grant allowlist",
            )
    if grant.command_class == READ_ONLY_COMMAND_CLASS:
        return AccessDecision(
            operation=operation,
            verdict=AccessVerdict.ALLOW,
            reason=AccessReason.COMMAND_CLASS,
            detail="grant declares a read-only command class",
        )
    return AccessDecision(
        operation=operation,
        verdict=AccessVerdict.NEEDS_APPROVAL,
        reason=AccessReason.COMMAND_NOT_ALLOWED,
        detail="run_command defaults to approval per ADR-0246 §4.3",
    )


def _decide_paths(
    operation: str, paths: Sequence[str], *, grant: CapabilityGrant, plane: PlaneRef
) -> AccessDecision:
    table = _WRITE_VERDICT if operation in WRITE_OPERATIONS else _READ_VERDICT
    strictest = AccessDecision(
        operation=operation,
        verdict=AccessVerdict.ALLOW,
        reason=AccessReason.IN_GRANT,
    )
    for raw in paths:
        resolved = resolve_plane_path(raw, plane)
        verdict, reason = table[classify_path(resolved, grant=grant, plane=plane)]
        if _SEVERITY[verdict] > _SEVERITY[strictest.verdict]:
            strictest = AccessDecision(
                operation=operation,
                verdict=verdict,
                reason=reason,
                path=resolved,
                detail=f"{operation} on {resolved}",
            )
    return strictest


def decide_access(
    operation: str,
    *,
    grant: CapabilityGrant,
    plane: PlaneRef,
    paths: Sequence[str] = (),
    command: str = "",
) -> AccessDecision:
    """The single authorization decision point for one local-exec operation."""
    if plane.kind is not PlaneKind.MACHINE:
        return AccessDecision(
            operation=operation,
            verdict=AccessVerdict.ALLOW,
            reason=AccessReason.NOT_A_MACHINE,
            detail="the sandbox container is the boundary; no second gate",
        )
    if operation in JOB_CONTINUATION_OPERATIONS:
        return AccessDecision(
            operation=operation,
            verdict=AccessVerdict.ALLOW,
            reason=AccessReason.JOB_CONTINUATION,
            detail="acts on a command_id from an already-decided run_command",
        )
    if grant.operation and grant.operation != operation:
        return AccessDecision(
            operation=operation,
            verdict=AccessVerdict.DENY,
            reason=AccessReason.OPERATION_NOT_GRANTED,
            detail=f"grant was issued for {grant.operation!r}",
        )
    if operation in EXEC_OPERATIONS:
        return _decide_command(command, grant)
    if operation not in READ_OPERATIONS and operation not in WRITE_OPERATIONS:
        return AccessDecision(
            operation=operation,
            verdict=AccessVerdict.NEEDS_APPROVAL,
            reason=AccessReason.OUTSIDE_GRANT,
            detail="unclassified operation; default to consent",
        )
    return _decide_paths(operation, paths, grant=grant, plane=plane)


__all__ = [
    "CREDENTIAL_BASENAMES",
    "CREDENTIAL_DIR_SEGMENTS",
    "CREDENTIAL_SUFFIXES",
    "EXEC_OPERATIONS",
    "JOB_CONTINUATION_OPERATIONS",
    "READ_ONLY_COMMAND_CLASS",
    "READ_OPERATIONS",
    "WRITE_OPERATIONS",
    "classify_path",
    "decide_access",
    "is_credential_path",
    "subcommands",
]
