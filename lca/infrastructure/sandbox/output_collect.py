"""Shared helpers for harvesting sandbox outputs (ADR-0046).

Adapters own provider-specific list/read; this module only normalizes paths,
applies size/count caps, and builds ``SandboxFile`` rows with diagnostics.
"""

from __future__ import annotations

import mimetypes
from pathlib import PurePosixPath

from lca.contracts.models.core.sandbox import (
    SANDBOX_MAX_GENERATED_FILE_BYTES,
    SANDBOX_MAX_GENERATED_FILES,
    SandboxFile,
)

_DEFAULT_MIME = "application/octet-stream"


def entry_basename(name_or_path: str) -> str:
    """Last path segment of a guest path or bare filename."""
    return PurePosixPath(name_or_path).name


def try_append_generated_file(
    out: list[SandboxFile],
    diagnostics: list[str],
    *,
    name: str,
    data: bytes,
) -> bool:
    """Append one harvested file if under caps.

    Returns ``False`` when the max-file count is already reached (caller should
    stop iterating). Oversize files are skipped with a diagnostic and return
    ``True`` so remaining entries can still be considered.
    """
    clean = entry_basename(name)
    if not clean:
        return True
    if len(out) >= SANDBOX_MAX_GENERATED_FILES:
        diagnostics.append(
            f"[lca] skipped output {clean!r}: max generated files "
            f"({SANDBOX_MAX_GENERATED_FILES}) reached\n"
        )
        return False
    size = len(data)
    if size > SANDBOX_MAX_GENERATED_FILE_BYTES:
        diagnostics.append(
            f"[lca] skipped output {clean!r}: size {size} exceeds "
            f"{SANDBOX_MAX_GENERATED_FILE_BYTES} bytes\n"
        )
        return True
    mime, _ = mimetypes.guess_type(clean)
    out.append(
        SandboxFile(
            name=clean,
            mime_type=mime or _DEFAULT_MIME,
            data=data,
        )
    )
    return True


def files_from_output_map(
    outputs: dict[str, bytes],
    diagnostics: list[str] | None = None,
) -> list[SandboxFile]:
    """Convert path→bytes map (Mock virtual FS) into capped ``SandboxFile`` list."""
    diags = diagnostics if diagnostics is not None else []
    out: list[SandboxFile] = []
    for path, data in outputs.items():
        name = entry_basename(path)
        if not try_append_generated_file(out, diags, name=name, data=data):
            break
    return out
