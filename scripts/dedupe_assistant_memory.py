#!/usr/bin/env python3
"""一次性去重脚本：把 semantic.json 中同一事实的重复活跃记录标记 superseded，
并重建 USER.md 为活跃 identity/preference 记录的投影（ADR-0247）。

用法:
    uv run python scripts/dedupe_assistant_memory.py <assistant_home>

只做可审计标记（不删除数据）；保留权威度最高的一条，其余不再参与检索。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lca.infrastructure.memory.migration import dedupe_semantic_memory
from lca.plugins.assistant.profile.profile import render_user_profile


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assistant_home", type=Path, help="assistant Home 目录")
    args = parser.parse_args(argv)

    home = args.assistant_home
    if not home.is_dir():
        print(f"assistant home 不存在: {home}", file=sys.stderr)
        return 2

    from lca.contracts.atoms.enums.enums import MemoryCategory, MemoryLayer
    from lca.infrastructure.memory.assistant_memory import AssistantMemory

    changed = dedupe_semantic_memory(home)
    mem = AssistantMemory(home)
    identity_pref = [
        r
        for r in mem.query(MemoryLayer.SEMANTIC)
        if r.category in {MemoryCategory.IDENTITY, MemoryCategory.PREFERENCE}
    ]
    if identity_pref:
        user_md = render_user_profile(identity_pref)
        (home / "USER.md").write_text(user_md, encoding="utf-8")
    print(
        f"semantic.json: {changed} 条重复记录标记为 superseded;"
        f" USER.md 已重建（{len(identity_pref)} 条活跃身份/偏好事实）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
