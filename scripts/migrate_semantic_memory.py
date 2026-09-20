#!/usr/bin/env python3
"""一次性迁移脚本：旧 semantic.json 原文记录标记 superseded + 清理小写 user.md。

用法:
    uv run python scripts/migrate_semantic_memory.py <assistant_home>

只做可审计标记（不删除数据）；迁移后旧原文不再参与记忆检索。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from lca.infrastructure.memory.migration import (
    clean_lowercase_user_md,
    migrate_semantic_memory,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("assistant_home", type=Path, help="assistant Home 目录")
    args = parser.parse_args(argv)

    home = args.assistant_home
    if not home.is_dir():
        print(f"assistant home 不存在: {home}", file=sys.stderr)
        return 2

    migrated = migrate_semantic_memory(home)
    cleaned = clean_lowercase_user_md(home)
    print(
        f"semantic.json: {migrated} 条旧原文记录标记为 superseded;"
        f" user.md 清理: {'是' if cleaned else '否'}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
