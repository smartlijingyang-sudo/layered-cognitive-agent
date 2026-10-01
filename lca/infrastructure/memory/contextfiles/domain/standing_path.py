"""Standing-file write guard: which paths writeFile must never touch.

The assistant's identity and memory have a single producer path: ``memory_add``
and ``memory_extract`` project into ``semantic.json`` and the standing files.
A generic ``writeFile`` overwriting ``USER.md`` / ``SOUL.md`` bypasses that
projection and can replace an identity profile with arbitrary tool output
(``run_ab78aeb6eabf`` overwrote ``memory/USER.md`` with a template). This
guard rejects those paths before any backend writes them.
"""

from __future__ import annotations

from pathlib import Path

from lca.infrastructure.memory.contextfiles.domain.layout import packaged_layout
from lca.infrastructure.path.locator import expand_user_path, get_lca_home

_SEMANTIC_REL = ("memory", "semantic.json")


def is_standing_write_path(path: str | Path) -> bool:
    """True when ``path`` names an assistant standing file or semantic memory.

    Only paths inside authoritative ``get_lca_home()`` or an assistant directory
    (``.../.lca/assistants/...``) count. A workspace file that happens to share
    a basename with a standing file stays writable, even if in a workspace ``.lca/`` subfolder.
    """
    raw_str = str(path).replace("\\", "/")
    expanded = expand_user_path(path).resolve()
    lca_home = get_lca_home().resolve()

    try:
        is_under_lca_home = expanded.is_relative_to(lca_home)
    except (ValueError, AttributeError):
        is_under_lca_home = False

    segments = [s for s in raw_str.split("/") if s]
    has_lca_assistants = any(
        segments[i] == ".lca" and i + 1 < len(segments) and segments[i + 1] == "assistants"
        for i in range(len(segments) - 1)
    )

    if not is_under_lca_home and not has_lca_assistants:
        return False

    if len(segments) >= 2 and segments[-2:] == list(_SEMANTIC_REL):
        return True

    basename = segments[-1].lower() if segments else ""
    return basename in {name.split("/")[-1].lower() for name in packaged_layout().standing_files}


def standing_write_block_message() -> str:
    """Reason returned to the model when it targets a standing file."""
    return (
        "writeFile 不能覆盖助手自身的 standing 记忆文件（SOUL / IDENTITY / USER / "
        "MEMORY 等）。用户身份与偏好请用 memory_add 写入；人格文件由用户或 "
        "revise_profile 管理。"
    )


def refuses_standing_path(path: str | Path) -> bool:
    """Alias kept short for call sites that only need the verdict."""
    return is_standing_write_path(path)


__all__ = ["is_standing_write_path", "refuses_standing_path", "standing_write_block_message"]
