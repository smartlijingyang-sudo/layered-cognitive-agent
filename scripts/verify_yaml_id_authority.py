#!/usr/bin/env python3
"""PR-5 等价性门禁：yaml id 与 class-path 双形态解析后的鉴权集合全等。

设计（PR-5 acceptance 文档化）：

事件 yaml ``publishers:`` / ``subscribers:`` / ``consumer_rules`` 在迁移后
接受 id 形态（catalog 解析）与 class-path 形态（importlib 解析）并存。本脚
本对每个 category 比对「预迁移 class-path 解析集合」与「现状解析集合」，
断言两边完全一致：

- 预迁移集合：对 HEAD 版本 yaml 用 catalog-less 解析（强制 class-path），
  得到 ``frozenset[type]``；
- 现状集合：对工作树版本 yaml 用带 catalog 的解析（id 优先），得到
  ``frozenset[type]``；
- 两者差异 → 退出 1。

实现要点：

- catalog 由 :mod:`lca_kernel.events.test_catalog` 提供（与生产 catalog
  等价：枚举 ``lca.plugins.events`` 下所有带 marker 的组件）。
- ``EventRegistry`` 接受 catalog 参数；缺省 = class-path only；注入 catalog
  后 = id 形态生效。
- 不修改任何 yaml / 代码；脚本只读 HEAD 与工作树。

delete-when：PR-5 双轨迁移期结束、class-path 形态全删后，本脚本转为「id
唯一形态」单测（仅断言工作树解析成功）。详见
``2026-09-04-plugin-universe-single-entry`` PR-5。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml  # noqa: E402

from lca_kernel.events.registry import EventRegistry  # noqa: E402
from lca_kernel.events.test_catalog import build_test_catalog  # noqa: E402

CONFIG_FILES = (
    "lca_kernel/events/config/observability/spine.yaml",
    "lca_kernel/events/config/business/team.yaml",
)


def _load_yaml_text(rel_path: str, *, head: bool) -> str:
    if head:
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
    return (ROOT / rel_path).read_text(encoding="utf-8")


def _resolve_registry(text: str, *, catalog: dict[str, type]) -> EventRegistry:
    """解析一段 yaml 文本为 EventRegistry（catalog 可空）。"""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "events.yaml").write_text(text, encoding="utf-8")
        registry = EventRegistry.load(tmp_path, catalog=catalog) if catalog else EventRegistry.load(tmp_path)
    return registry


def _token_set(registry: EventRegistry, *, key: str) -> dict[str, frozenset[type]]:
    """把 registry 的 publishers / subscribers 转换为 ``{category: types}`` 字符串集合。"""
    out: dict[str, frozenset[type]] = {}
    src = registry.publishers if key == "publishers" else registry.subscribers
    for cat, types in src.items():
        out[cat.value] = frozenset(types)
    return out


def main() -> int:
    catalog = build_test_catalog()
    print(f"catalog: {len(catalog)} entries")
    failures: list[str] = []
    for rel in CONFIG_FILES:
        head_text = _load_yaml_text(rel, head=True)
        work_text = _load_yaml_text(rel, head=False)

        # 预迁移（HEAD）解析：class-path only（catalog 缺位 → 仅 class-path 形态可用）。
        head_registry = _resolve_registry(head_text, catalog={})
        # 现状解析：带 catalog（id 形态生效，class-path 兼容保留）。
        work_registry = _resolve_registry(work_text, catalog=catalog)

        for role in ("publishers", "subscribers"):
            head_set = _token_set(head_registry, key=role)
            work_set = _token_set(work_registry, key=role)

            for cat in sorted(head_set.keys() | work_set.keys()):
                h = head_set.get(cat, frozenset())
                w = work_set.get(cat, frozenset())
                if h != w:
                    h_paths = sorted(f"{c.__module__}.{c.__qualname__}" for c in h)
                    w_paths = sorted(f"{c.__module__}.{c.__qualname__}" for c in w)
                    failures.append(
                        f"{rel} {cat} {role}: HEAD={h_paths} 工作树={w_paths}"
                    )

        print(f"{rel}: 鉴权集合全等" if not any(f.startswith(rel) for f in failures) else f"{rel}: 存在差异（见下）")

    if failures:
        print("FAILED: yaml id 与 class-path 双形态解析集合不一致", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print("OK: yaml id 双形态解析集合与预迁移 class-path 集合全等")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())