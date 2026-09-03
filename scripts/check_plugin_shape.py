"""CI gate: enforce single-Manifest convention for ``lca/plugins/``.

Phase A of the unified-plugin-shape plan. 与 ADR-0110 contract 面正交,只校验
目录级与文件级形态规范,不动 ``@plugin(...)`` 装饰器签名。

扫描四个维度:
1. **effects 未声明** —— ``@plugin(...)`` 调用缺 ``effects=`` 关键字。
   AST 扫:与 ``codegen_plugin_metadata.py`` 的元数据提取共享,确保基线一致。
2. **双形态残留** —— ``lca/plugins/events/{sinks,publishers,subscribers}/*/manifest.py``
   里同时导出 ``event_plugin_spec = EventPluginSpec(...)`` 与 ``plugin_spec: dict``。
   ``codegen`` 只扫含 ``@plugin`` 的文件;events 双形态 plugin 没 ``@plugin`` 自然漏,
   本脚本独立扫该目录。
3. **同 id 镜像** —— 多个文件声明相同 ``@plugin(id=...)``,违反单一入口原则。
4. **位置逃逸**(PR-9)—— ``@plugin`` 装饰器只允许在 ``lca/plugins/`` 与
   ``lca_kernel/events/manifest.py``(kernel 元插件,合法位置)。其他位置出现
   ``@plugin`` 装饰器即视为位置逃逸。

输出:人类可读 + ``--json`` 模式。返回 exit code:有违例 → 1,否则 0。
豁免通过 ``--root`` 之外的白名单(本脚本不读 ``legacy_blacklist.txt``;豁免仅做
目录范围过滤,例如 ``--root lca/plugins/observability`` 只扫该子树)。

Usage:
  python scripts/check_plugin_shape.py [--root PATH] [--json]
  python scripts/check_plugin_shape.py --baseline       # 写基线快照到 docs/notes/

Reference: docs/notes/implemented/seam/2026-09-03-plugin-shape-baseline.md
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = ROOT / "lca" / "plugins"

# Phase B 双形态残留扫描范围:events 三类子目录。双形态 plugin 在
# ``<kind>/<name>/manifest.py`` 里集中导出 ``event_plugin_spec`` + ``plugin_spec: dict``。
DUAL_FORM_KIND_DIRS = ("sinks", "publishers", "subscribers")


@dataclass
class ShapeViolation:
    """单一形态违例记录。"""

    kind: str  # "missing_effects" | "dual_form_residue" | "duplicate_id" | "location_escape"
    plugin_id: str  # 缺 id 时为 "<unknown>"
    file: str
    line: int
    detail: str


@dataclass
class ShapeReport:
    """汇总报告。"""

    root: str
    total_plugins: int
    violations: list[ShapeViolation] = field(default_factory=list)
    by_kind: dict[str, int] = field(default_factory=dict)


# ── AST helpers(独立实现,不依赖 codegen_plugin_metadata)──────────────────


def _find_plugin_decorators(tree: ast.Module) -> list[ast.Call]:
    """遍历模块所有 ``@plugin(...)`` 装饰器调用。"""
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else (func.attr if isinstance(func, ast.Attribute) else None)
            )
            if name == "plugin":
                out.append(decorator)
    return out


def _kw_literal_str(call: ast.Call, key: str) -> str | None:
    """取关键字参数的字符串字面值。"""
    for kw in call.keywords:
        if kw.arg == key and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
            return kw.value.value
    return None


def _has_module_level_assign(tree: ast.Module, target_name: str) -> bool:
    """模块顶层是否有 ``target_name`` 赋值(AnnAssign / Assign)。"""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target_name:
                    return True
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == target_name
        ):
            return True
    return False


# ── 扫描维度 ─────────────────────────────────────────────────────────────


def _scan_missing_effects(root: Path) -> tuple[int, list[ShapeViolation]]:
    """扫描所有 ``@plugin(...)`` 里缺 ``effects=`` 关键字的 plugin。"""
    total = 0
    violators: list[ShapeViolation] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for decorator in _find_plugin_decorators(tree):
            total += 1
            if _kw_literal_str(decorator, "effects") is not None:
                continue
            plugin_id = _kw_literal_str(decorator, "id") or "<unknown>"
            line = getattr(decorator, "lineno", 0)
            violators.append(
                ShapeViolation(
                    kind="missing_effects",
                    plugin_id=plugin_id,
                    file=str(path.relative_to(ROOT)),
                    line=line,
                    detail="@plugin(...) 缺 effects= 关键字",
                )
            )
    return total, violators


def _scan_dual_form_residue(root: Path) -> list[ShapeViolation]:
    """扫描 ``lca/plugins/events/{sinks,publishers,subscribers}/*/manifest.py``
    顶层同时声明 ``event_plugin_spec`` 与 ``plugin_spec``(任一即触发)。

    该扫描独立于 ``@plugin`` 入口:events 双形态 plugin 当前没有 ``@plugin`` 装饰器,
    ``codegen_plugin_metadata.py`` 看不到它们。
    """
    out: list[ShapeViolation] = []
    events_root = root / "events"
    if not events_root.is_dir():
        return out
    for kind_dir in DUAL_FORM_KIND_DIRS:
        kind_path = events_root / kind_dir
        if not kind_path.is_dir():
            continue
        for manifest in sorted(kind_path.rglob("manifest.py")):
            if "__pycache__" in manifest.parts:
                continue
            try:
                tree = ast.parse(manifest.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            has_event_spec = _has_module_level_assign(tree, "event_plugin_spec")
            has_plugin_spec_dict = _has_module_level_assign(tree, "plugin_spec")
            if not (has_event_spec or has_plugin_spec_dict):
                continue
            kinds: list[str] = []
            if has_event_spec:
                kinds.append("event_plugin_spec = EventPluginSpec(...)")
            if has_plugin_spec_dict:
                kinds.append("plugin_spec: dict = {...}")
            line = _find_module_level_line(tree, "event_plugin_spec")
            out.append(
                ShapeViolation(
                    kind="dual_form_residue",
                    plugin_id=manifest.parent.name,
                    file=str(manifest.relative_to(ROOT)),
                    line=line,
                    detail="双形态残留: " + "; ".join(kinds),
                )
            )
    return out


def _find_module_level_line(tree: ast.Module, target_name: str) -> int:
    """取 ``target_name`` 在模块顶层的行号(用于报错位置)。"""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target_name:
                    return getattr(node, "lineno", 0)
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == target_name
        ):
            return getattr(node, "lineno", 0)
    return 0


def _scan_duplicate_ids(root: Path) -> list[ShapeViolation]:
    """扫描同 ``@plugin(id=...)`` 出现在多个文件 —— 违反单一入口原则。"""
    id_to_files: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for decorator in _find_plugin_decorators(tree):
            plugin_id = _kw_literal_str(decorator, "id")
            if plugin_id:
                id_to_files[plugin_id].append((path, getattr(decorator, "lineno", 0)))
    out: list[ShapeViolation] = []
    for plugin_id, locations in id_to_files.items():
        if len(locations) <= 1:
            continue
        for path, line in locations:
            out.append(
                ShapeViolation(
                    kind="duplicate_id",
                    plugin_id=plugin_id,
                    file=str(path.relative_to(ROOT)),
                    line=line,
                    detail=f"id={plugin_id!r} 在 {len(locations)} 个文件出现",
                )
            )
    return out


# 位置逃逸扫描白名单:唯一允许 ``@plugin`` 在 ``lca/plugins/`` 之外的合法位置。
# 当前白名单:
# - ``lca_kernel/events/manifest.py`` —— kernel 元插件(PR-9 行明示保留)。
LOCATION_ALLOWED_EXCEPTIONS: tuple[str, ...] = ("lca_kernel/events/manifest.py",)


def _is_under_plugins(path: Path) -> bool:
    """``path`` 是否在 ``lca/plugins/`` 之下(白名单主目录)。"""
    try:
        rel = path.relative_to(ROOT / "lca" / "plugins")
    except ValueError:
        return False
    return not rel.parts or rel.parts[0] != ".."


def _scan_location_escape(root: Path) -> list[ShapeViolation]:
    """扫描 ``@plugin`` 装饰器出现在 ``lca/plugins/`` 与白名单之外的位置。

    扫描范围:整个仓库的 .py 文件,但仅 ``@plugin`` 装饰器所在文件需被定位。
    唯一例外:``lca_kernel/events/manifest.py``(kernel 元插件,PR-9 行显式豁免)。
    """
    out: list[ShapeViolation] = []
    for path in sorted(root.parent.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if path.name == "__init__.py":
            continue
        if _is_under_plugins(path):
            continue
        rel = path.relative_to(root.parent)
        rel_str = str(rel)
        if rel_str in LOCATION_ALLOWED_EXCEPTIONS:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for decorator in _find_plugin_decorators(tree):
            plugin_id = _kw_literal_str(decorator, "id") or "<unknown>"
            line = getattr(decorator, "lineno", 0)
            out.append(
                ShapeViolation(
                    kind="location_escape",
                    plugin_id=plugin_id,
                    file=rel_str,
                    line=line,
                    detail="@plugin 装饰器只能位于 lca/plugins/ 或 lca_kernel/events/manifest.py",
                )
            )
    return out


# ── 主入口 ───────────────────────────────────────────────────────────────


def scan(root: Path) -> ShapeReport:
    """执行四维扫描,返回汇总。"""
    total, missing_effects = _scan_missing_effects(root)
    dual_form = _scan_dual_form_residue(root)
    duplicates = _scan_duplicate_ids(root)
    location_escape = _scan_location_escape(root)
    by_kind: dict[str, int] = {
        "missing_effects": len(missing_effects),
        "dual_form_residue": len(dual_form),
        "duplicate_id": len(duplicates),
        "location_escape": len(location_escape),
    }
    return ShapeReport(
        root=str(root),
        total_plugins=total,
        violations=missing_effects + dual_form + duplicates + location_escape,
        by_kind=by_kind,
    )


def emit_human(report: ShapeReport) -> None:
    """人类可读输出:违例按 kind 分组,每组按 file:line 排序。"""
    if not report.violations:
        print(
            f"plugin-shape: all {report.total_plugins} plugins follow single-Manifest convention."
        )
        return
    print(
        f"plugin-shape: scanned {report.total_plugins} plugins under {report.root}; "
        f"{len(report.violations)} violations "
        f"(missing_effects={report.by_kind['missing_effects']}, "
        f"dual_form_residue={report.by_kind['dual_form_residue']}, "
        f"duplicate_id={report.by_kind['duplicate_id']}, "
        f"location_escape={report.by_kind['location_escape']})",
        file=sys.stderr,
    )
    grouped: dict[str, list[ShapeViolation]] = defaultdict(list)
    for v in report.violations:
        grouped[v.kind].append(v)
    kind_labels = {
        "missing_effects": "缺少 effects=",
        "dual_form_residue": "双形态残留",
        "duplicate_id": "同 id 镜像",
        "location_escape": "位置逃逸",
    }
    for kind in ("missing_effects", "dual_form_residue", "duplicate_id", "location_escape"):
        items = grouped.get(kind, [])
        if not items:
            continue
        print(f"\n[{kind_labels[kind]}] ({len(items)} 个)", file=sys.stderr)
        for v in items:
            print(
                f"  {v.plugin_id:<48} {v.file}:{v.line}  {v.detail}",
                file=sys.stderr,
            )
    print(
        "\n跟踪: docs/notes/implemented/seam/2026-09-03-plugin-shape-baseline.md; "
        "delete-when: missing_effects → Phase C 全部补齐; "
        "dual_form_residue → Phase B 全部清除; "
        "duplicate_id → Phase C 镜像合并完毕; "
        "location_escape → PR-9 全部归位。",
        file=sys.stderr,
    )


def emit_json(report: ShapeReport) -> None:
    """机器可读 JSON:供 notes-check / lca-ops audit-plugin-shape 串联。"""
    print(
        json.dumps(
            {
                "root": report.root,
                "total_plugins": report.total_plugins,
                "by_kind": report.by_kind,
                "violations": [
                    {
                        "kind": v.kind,
                        "id": v.plugin_id,
                        "file": v.file,
                        "line": v.line,
                        "detail": v.detail,
                    }
                    for v in report.violations
                ],
            },
            indent=2,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="write JSON snapshot to docs/notes/baselines/plugin-shape.json",
    )
    args = parser.parse_args(argv)

    report = scan(args.root)

    if args.baseline:
        baseline_path = ROOT / "docs" / "notes" / "baselines" / "plugin-shape.json"
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(
                {
                    "root": report.root,
                    "total_plugins": report.total_plugins,
                    "by_kind": report.by_kind,
                    "violations": [
                        {
                            "kind": v.kind,
                            "id": v.plugin_id,
                            "file": v.file,
                            "line": v.line,
                            "detail": v.detail,
                        }
                        for v in report.violations
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"baseline written: {baseline_path}")
        return 0

    if args.json:
        emit_json(report)
    else:
        emit_human(report)
    return 1 if report.violations else 0


if __name__ == "__main__":
    sys.exit(main())
