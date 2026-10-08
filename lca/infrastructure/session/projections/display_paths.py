"""Display-path projection for model-visible tool payloads (ADR-0121).

The model-visible rendering of a tool payload shows workspace-relative
guest paths while receipts and the journal keep guest absolute process
paths. One allowlist of conventional path key names lives here, so every
current and future tool that uses those keys is covered without
per-tool edits. Values under non-allowlisted keys and free text are
never rewritten, which keeps file contents and exotic payloads intact.
"""

from __future__ import annotations

from lca.contracts.models.core.execution.sandbox import SANDBOX_MOUNT_ROOT

DISPLAY_PATH_KEYS = frozenset(
    {"path", "paths", "directoryPath", "directory", "directory_path", "file", "target"}
)

_ROOT = SANDBOX_MOUNT_ROOT.rstrip("/")


def display_path(value: str) -> str:
    """Return the workspace-relative display form of one guest path."""
    if value == _ROOT:
        return "."
    if value.startswith(_ROOT + "/"):
        return value[len(_ROOT) + 1 :]
    return value


def project_display_paths(payload: object) -> object:
    """Rewrite allowlisted path keys in a payload tree to display form."""
    if isinstance(payload, dict):
        return {
            key: (
                display_path(value)
                if key in DISPLAY_PATH_KEYS and isinstance(value, str)
                else project_display_paths(value)
            )
            for key, value in payload.items()
        }
    if isinstance(payload, (list, tuple)):
        return [project_display_paths(item) for item in payload]
    return payload


__all__ = ["DISPLAY_PATH_KEYS", "display_path", "project_display_paths"]
