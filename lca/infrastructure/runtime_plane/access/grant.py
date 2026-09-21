"""Default CapabilityGrant construction for a paired user machine.

ADR-0246 §3.2 puts grant issuance in the control plane. Until a signing
control plane exists, this module is the single construction point, and the
default scope is data rather than branches so an operator can read and change
it in one place.

The default shape follows the industry pattern recorded in the
``machine-path-authorization-belongs-to-capability-grant`` Agent Note. Reads
reach the working root and the user's home directory. Writes stay inside the
working root; a path that is merely readable still needs consent to modify.
Commands run without approval only when every subcommand is a known read-only
one.
"""

from __future__ import annotations

from lca.contracts.models.core.execution.local_exec import CapabilityGrant
from lca.contracts.models.core.state.plane import PlaneRef

#: Commands that only observe. Matched on the first token of every subcommand.
#: Deliberately excludes anything with a write or exec flag: ``find`` has
#: ``-delete``, ``git`` has ``push`` and ``rm``, ``env`` prints credentials.
DEFAULT_READ_ONLY_COMMANDS: tuple[str, ...] = (
    "ls",
    "cat",
    "echo",
    "pwd",
    "head",
    "tail",
    "grep",
    "wc",
    "which",
    "diff",
    "stat",
    "du",
    "cd",
    "uname",
    "whoami",
    "hostname",
    "date",
    "dir",
    "type",
    "where",
    "findstr",
    "tasklist",
    "netstat",
    "ver",
    "systeminfo",
)


def readable_prefixes(plane: PlaneRef) -> tuple[str, ...]:
    """The default read scope: working root plus the user's home directory.

    Empty entries are dropped so an unresolved plane yields an empty grant,
    which denies by default rather than silently widening.
    """
    ordered = [plane.root, plane.home]
    seen: list[str] = []
    for entry in ordered:
        if entry and entry not in seen:
            seen.append(entry)
    return tuple(seen)


def default_machine_grant(
    plane: PlaneRef,
    *,
    operation: str,
    job_id: str,
    idempotency_key: str,
    subject_user_id: str,
    expires_at: int,
    approval_id: str | None = None,
    request_digest: str = "",
    command_allowlist: tuple[str, ...] = DEFAULT_READ_ONLY_COMMANDS,
) -> CapabilityGrant:
    """Build the per-job grant for one operation on a paired machine."""
    return CapabilityGrant(
        job_id=job_id,
        idempotency_key=idempotency_key,
        subject_user_id=subject_user_id,
        subject_machine_id=plane.id,
        operation=operation,
        path_prefixes=readable_prefixes(plane),
        command_class=None,
        command_allowlist=command_allowlist,
        expires_at=expires_at,
        approval_id=approval_id,
        request_digest=request_digest,
    )


__all__ = ["DEFAULT_READ_ONLY_COMMANDS", "default_machine_grant", "readable_prefixes"]
