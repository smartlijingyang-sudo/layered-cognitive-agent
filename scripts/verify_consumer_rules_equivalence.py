#!/usr/bin/env python3
"""ADR-0183 PR-6 等价性门禁：consumer_rules 前缀规则 vs 旧逐 category 授权。

对 spine.yaml / team.yaml 各 category 比对「git HEAD 版本的有效订阅授权
集合」与「工作树版本的有效订阅授权集合」，断言全等：

- 有效授权集合 = 逐 category ``subscribers`` ∪ 顶层 ``consumer_rules``
  前缀命中规则的 subscribers 并集（:mod:`lca_kernel.events.config_parser`）。
  HEAD 是逐 category 形态时，其有效集合即逐条 subscribers；工作树是前缀
  规则形态时，即规则求并结果。两端同构比对，脚本在形态迁移前后均可重跑。
- 追加 typed 校验：``EventRegistry.load`` 物化的每 category 订阅集合与
  工作树字符串级集合一致（class 全路径对齐）。

全等 → exit 0；任何差异 → 打印 diff，exit 1。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from lca_kernel.events.config_parser import (  # noqa: E402
    SubscriberRule,
    subscribers_from_rules,
)

CONFIG_FILES = (
    "lca_kernel/events/config/observability/spine.yaml",
    "lca_kernel/events/config/business/team.yaml",
)


def parse_rules_string_level(data: dict, source: str) -> tuple[SubscriberRule[str], ...]:
    """字符串级解析顶层 consumer_rules（不 import 业务类，纯文本比对）。"""
    entries = data.get("consumer_rules")
    if entries is None:
        return ()
    if not isinstance(entries, list):
        raise ValueError(f"{source}: consumer_rules 必须是 list")
    out: list[SubscriberRule[str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("prefix"), str):
            raise ValueError(f"{source}: 规则必须是含字符串 prefix 的 mapping")
        out.append(
            SubscriberRule(
                prefix=entry["prefix"],
                subscribers=frozenset(str(s) for s in entry.get("subscribers") or ()),
            )
        )
    return tuple(out)


def effective_auth(yaml_text: str, source: str) -> dict[str, frozenset[str]]:
    """yaml 文本 → {category: 有效订阅授权集合}。"""
    data = yaml.safe_load(yaml_text)
    if not isinstance(data, dict) or "events" not in data:
        raise ValueError(f"{source}: 缺 events 段")
    rules = parse_rules_string_level(data, source)
    auth: dict[str, frozenset[str]] = {}
    for entry in data["events"]:
        category = str(entry["category"])
        per_category = frozenset(str(s) for s in entry.get("subscribers") or ())
        auth[category] = per_category | subscribers_from_rules(category, rules)
    return auth


def head_version(rel_path: str) -> str:
    proc = subprocess.run(  # noqa: S603 — cmd 为本脚本硬编码
        ["git", "show", f"HEAD:{rel_path}"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git show HEAD:{rel_path} 失败: {proc.stderr.strip()}")
    return proc.stdout


def main() -> int:
    failures: list[str] = []
    for rel in CONFIG_FILES:
        old_auth = effective_auth(head_version(rel), source=f"HEAD:{rel}")
        new_text = (ROOT / rel).read_text(encoding="utf-8")
        new_auth = effective_auth(new_text, source=rel)

        for cat in sorted(old_auth.keys() | new_auth.keys()):
            old_set = old_auth.get(cat)
            new_set = new_auth.get(cat)
            if old_set != new_set:
                failures.append(
                    f"{rel} {cat}: HEAD={sorted(old_set or ())} 工作树={sorted(new_set or ())}"
                )
        print(
            f"{rel}: {len(old_auth)} categories，授权集合全等"
            if not any(f.startswith(rel) for f in failures)
            else f"{rel}: 存在差异（见下）"
        )

    # typed 校验：EventRegistry.load 物化集合 == 工作树字符串级集合
    from lca_kernel.events.registry import EventRegistry

    worktree_auth: dict[str, frozenset[str]] = {}
    for rel in CONFIG_FILES:
        worktree_auth.update(effective_auth((ROOT / rel).read_text(encoding="utf-8"), source=rel))
    registry = EventRegistry.load(ROOT / "lca_kernel" / "events" / "config")
    for spec in registry.specs:
        cat = spec.category.value
        typed_paths = {
            f"{c.__module__}.{c.__qualname__}" for c in registry.subscribers[spec.category]
        }
        if typed_paths != worktree_auth.get(cat, frozenset()):
            failures.append(
                f"registry 物化不一致 {cat}: registry={sorted(typed_paths)} "
                f"yaml={sorted(worktree_auth.get(cat, frozenset()))}"
            )
    print(
        f"EventRegistry.load: {len(registry.specs)} specs，"
        f"{len(registry.consumer_rules)} 条前缀规则"
    )

    if failures:
        print("FAILED: consumer_rules 等价性校验未通过", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK: 前缀规则授权集合与旧逐 category 授权全等")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
