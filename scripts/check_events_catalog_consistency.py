#!/usr/bin/env python3
"""CI gate: 事件 yaml publishers token 与 plugin catalog 一致性(ADR-0181+1)。

加载 ``lca_kernel/events/config/**/*.yaml`` + 真实 plugin catalog
（通过 :func:`lca_kernel.events.test_catalog.build_test_catalog` 收集
所有已知 marker plugin），跑 :meth:`EventRegistry.validate_publisher_authorization`。
任一 publisher token 既不在 catalog 也非可 import 的 class-path →
脚本以非零退出码失败并打印可定位的诊断信息。

用法::

    uv run python scripts/check_events_catalog_consistency.py
    # 或:  ./scripts/check_events_catalog_consistency.py

退出码:
- 0: 所有 publisher token 解析成功
- 1: 至少一条 publisher token 解析失败（print 含 category + token + 计数）
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lca_kernel.events.errors import (  # noqa: E402
    UnknownPluginIdError,
)
from lca_kernel.events.registry import EventRegistry  # noqa: E402
from lca_kernel.events.test_catalog import build_test_catalog  # noqa: E402

_CONFIG_DIR = _ROOT / "lca_kernel" / "events" / "config"


def main() -> int:
    if not _CONFIG_DIR.is_dir():
        print(f"FAIL: events config dir not found: {_CONFIG_DIR}")
        return 1
    catalog = build_test_catalog()
    registry = EventRegistry.load(_CONFIG_DIR, catalog=catalog)
    registry.refresh()
    try:
        registry.validate_publisher_authorization()
    except UnknownPluginIdError as exc:
        print("FAIL: yaml publisher token 解析失败（ADR-0181+1 一致性 CI 门禁）")
        print(f"  source: {exc.source}")
        print(f"  first_miss_token: {exc.plugin_id}")
        print(f"  catalog entries: {len(catalog)}")
        print(
            "  修复: 把 yaml 里下划线短形式 token 改为 plugin manifest 的点分 id，"
            "或补 register_marker。"
        )
        return 1
    print(
        f"PASS: events catalog consistency OK "
        f"({len(registry.specs)} specs, {len(catalog)} catalog entries)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
