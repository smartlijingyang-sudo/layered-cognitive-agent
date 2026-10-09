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
        "writeFile 不能覆盖助手自身的 standing 文件（SOUL / IDENTITY / USER / "
        "MEMORY 等）。修改助手自身的名字/人格/身份，请用 agent 命名空间的 "
        "update_assistant_profile / update_assistant_soul 工具（或由用户经 "
        "revise_profile 修改）；记录用户（人类）的身份与偏好，请用 memory_add。"
    )


def refuses_standing_path(path: str | Path) -> bool:
    """Alias kept short for call sites that only need the verdict."""
    return is_standing_write_path(path)


def is_skill_package_write_path(path: str | Path) -> bool:
    """True when ``path`` targets a file inside an assistant Home's ``skills/`` package.

    已安装技能包的唯一生产路径是 ``create_assistant_skill``（安装）/
    ``edit_assistant_skill``（编辑）：staging → 内容闸 → 记录 digest →
    revision 快照。通用 ``writeFile`` / ``editFile`` 直写会绕过其中每一步
    （``run_755719d1a9d5`` 实测：5 次 writeFile 替换 SKILL.md，
    ``artifact_state`` 仍为 ``verified``），因此这些路径必须拒绝。

    作用域与 ``is_standing_write_path`` 一致：只看 ``get_lca_home()`` 之下
    或 ``.lca/assistants/`` 树内的 ``assistants/<id>/skills/<skill_id>/...``。
    工作区的同名文件（如 ``{home}/workspace/SKILL.md``）保持可写——
    ``workspace`` 不是 home 的直接 ``skills`` 子目录，模式匹配不上。
    读路径不受影响（守卫只挂在写调用点）。
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

    # assistants/<assistant_id>/skills/<skill_id>[/...]
    return any(
        segments[i] == "assistants" and segments[i + 2] == "skills"
        for i in range(len(segments) - 3)
    )


def skill_package_write_block_message() -> str:
    """Reason returned to the model when it targets an installed skill package."""
    return (
        "writeFile 不能直接改写助理 Home 里已安装的技能包"
        "（{home}/skills/<skill_id>/ 下的任何文件）。"
        "技能内容的生产路径只有两条：create_assistant_skill（安装）与 "
        "edit_assistant_skill（编辑）——它们走 staging → 内容闸 → 记录 digest → "
        "revision 快照。要安装或修改技能请用这两个工具，不要用 writeFile / "
        "editFile 直写。"
    )


__all__ = [
    "is_skill_package_write_path",
    "is_standing_write_path",
    "refuses_standing_path",
    "skill_package_write_block_message",
    "standing_write_block_message",
]
