"""CI gate: enforce single-Manifest convention for ``lca/plugins/``.

Phase A of the unified-plugin-shape plan. 与 ADR-0110 contract 面正交,只校验
目录级与文件级形态规范,不动 ``@plugin(...)`` 装饰器签名。

扫描八个维度(Phase A 三维 + PR-1 五维):
1. **effects 未声明** —— ``@plugin(...)`` 调用缺 ``effects=`` 关键字。
   AST 扫:与 ``codegen_plugin_metadata.py`` 的元数据提取共享,确保基线一致。
2. **双形态残留** —— ``lca/plugins/events/{sinks,publishers,subscribers}/*/manifest.py``
   里同时导出 ``event_plugin_spec = EventPluginSpec(...)`` 与 ``plugin_spec: dict``。
   ``codegen`` 只扫含 ``@plugin`` 的文件;events 双形态 plugin 没 ``@plugin`` 自然漏,
   本脚本独立扫该目录。
3. **同 id 镜像** —— 多个文件声明相同 ``@plugin(id=...)``,违反单一入口原则。
4. **plugin 位置** —— ``@plugin`` 装饰器出现在 ``lca/plugins/`` 与
   ``lca_kernel/events/manifest.py`` 之外的位置(只对生产代码生效,test 装饰器
   fixture 豁免)。位置合规是 lca/plugins/ 单入口宇宙的硬约束。
5. **孤儿插件** —— ``lca/plugins/`` 下的 ``@plugin`` 文件没有任何
   ``bundles/*.yaml`` 通过 ``$module:`` 引用它。
6. **死 bundle 引用** —— ``bundles/*.yaml`` 的 ``$module:`` 路径不可 import,
   或 import 后的模块里 ``@plugin(id=...)`` 与 bundle entry 的 ``id:`` 不一致。
7. **plugin in __init__.py** —— ``@plugin(...)`` 出现在 ``__init__.py``,违反
   AGENTS.md §5 的"一个插件一个 .py 文件"硬约束。
8. **同 id 多入口** —— 与维度 3 同一回事(单入口宇宙要求每个 id 只在一个文件
   出现)。作为维度 8 重申。

PR-1 起新维度以基线快照形式落地:``docs/notes/baselines/plugin-shape.json``
记录每维度的当前违例数,gate 仅在"超过基线"(regression) 时返回 1;后续 PR
负责单调下降基线至 0。``--baseline`` 覆写基线。

输出:人类可读 + ``--json`` 模式。返回 exit code:任一维度超出基线 → 1,否则 0。
豁免通过 ``--root`` 之外的白名单(本脚本不读 ``legacy_blacklist.txt``;豁免仅做
目录范围过滤,例如 ``--root lca/plugins/observability`` 只扫该子树)。

Usage:
  python scripts/check_plugin_shape.py [--root PATH] [--json]
  python scripts/check_plugin_shape.py --baseline       # 写基线快照到 docs/notes/

Reference: docs/notes/implemented/seam/2026-09-03-plugin-shape-baseline.md
            docs/notes/proposed/seam/2026-09-04-plugin-universe-single-entry.md (PR-1)
"""

from __future__ import annotations

import argparse
import ast
import importlib
import importlib.util
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = ROOT / "lca" / "plugins"
DEFAULT_BUNDLES_GLOB = ROOT / "bundles" / "*.yaml"
DEFAULT_BASELINE_PATH = ROOT / "docs" / "notes" / "baselines" / "plugin-shape.json"

# Phase B 双形态残留扫描范围:events 三类子目录。双形态 plugin 在
# ``<kind>/<name>/manifest.py`` 里集中导出 ``event_plugin_spec`` + ``plugin_spec: dict``。
DUAL_FORM_KIND_DIRS = ("sinks", "publishers", "subscribers")

# PR-1 第 4 维(plugin_location):@plugin 合法位置白名单。
LEGAL_PLUGIN_LOCATIONS: tuple[str, ...] = (
    "lca/plugins/",
    "lca_kernel/events/manifest.py",
)

# PR-1 全维度 kind 标签(用于 ShapeViolation.kind / report.by_kind 键)。
KIND_MISSING_EFFECTS = "missing_effects"
KIND_DUAL_FORM_RESIDUE = "dual_form_residue"
KIND_DUPLICATE_ID = "duplicate_id"
KIND_PLUGIN_LOCATION = "plugin_location"
KIND_ORPHAN_PLUGIN = "orphan_plugin"
KIND_DEAD_BUNDLE_REF = "dead_bundle_ref"
KIND_PLUGIN_IN_INIT = "plugin_in_init"
ALL_KINDS: tuple[str, ...] = (
    KIND_MISSING_EFFECTS,
    KIND_DUAL_FORM_RESIDUE,
    KIND_DUPLICATE_ID,
    KIND_PLUGIN_LOCATION,
    KIND_ORPHAN_PLUGIN,
    KIND_DEAD_BUNDLE_REF,
    KIND_PLUGIN_IN_INIT,
)


@dataclass
class ShapeViolation:
    """单一形态违例记录。"""

    kind: str
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


def _file_to_module(rel_posix: str) -> str:
    """``lca/plugins/perceive/service.py`` → ``lca.plugins.perceive.service``。"""
    no_ext = rel_posix[:-3] if rel_posix.endswith(".py") else rel_posix
    return no_ext.replace("/", ".")


def _iter_python_files(
    roots: list[Path], exclude_dirs: tuple[str, ...] = (".venv", "vendor", "lobehub-ui")
):
    """遍历生产代码 .py 文件,跳过缓存、virtualenv、vendored 与 UI 子树。

    测试装饰器(@plugin fixture)豁免 location / __init__ 检查,故只扫非 tests/。

    当 ``roots`` 包含 ROOT(repo 根)外的目录时,以该目录为基准计算 ``rel``;
    若多个 roots,使用每个 path 自身所在的 root 作相对基准。
    """
    for root in roots:
        for path in root.rglob("*.py"):
            parts = set(path.parts)
            if "__pycache__" in parts:
                continue
            if any(ex in parts for ex in exclude_dirs):
                continue
            rel = _relative_to_root(path, roots)
            if rel.startswith("tests/"):
                continue
            yield path


def _relative_to_root(path: Path, roots: list[Path] | None = None) -> str:
    """计算 ``path`` 相对其所在 root 的 POSIX 字符串。"""
    candidates = roots if roots is not None else [ROOT]
    for candidate in candidates:
        try:
            return path.relative_to(candidate).as_posix()
        except ValueError:
            continue
    return path.as_posix()


def _parse_tree(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


# ── 扫描维度 ─────────────────────────────────────────────────────────────


def _scan_missing_effects(root: Path) -> tuple[int, list[ShapeViolation]]:
    """扫描所有 ``@plugin(...)`` 里缺 ``effects=`` 关键字的 plugin。"""
    total = 0
    violators: list[ShapeViolation] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        tree = _parse_tree(path)
        if tree is None:
            continue
        for decorator in _find_plugin_decorators(tree):
            total += 1
            if _kw_literal_str(decorator, "effects") is not None:
                continue
            plugin_id = _kw_literal_str(decorator, "id") or "<unknown>"
            line = getattr(decorator, "lineno", 0)
            violators.append(
                ShapeViolation(
                    kind=KIND_MISSING_EFFECTS,
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
            tree = _parse_tree(manifest)
            if tree is None:
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
                    kind=KIND_DUAL_FORM_RESIDUE,
                    plugin_id=manifest.parent.name,
                    file=str(manifest.relative_to(ROOT)),
                    line=line,
                    detail="双形态残留: " + "; ".join(kinds),
                )
            )
    return out


def _collect_plugin_files(root: Path) -> list[tuple[Path, ast.Call, str]]:
    """收集 ``root`` 下所有含 ``@plugin(...)`` 的 (file, decorator_call, plugin_id)。

    ``__init__.py`` 不跳过:orphan 检查只要 file 路径;plugin_in_init 检查要 file==__init__。
    """
    out: list[tuple[Path, ast.Call, str]] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = _parse_tree(path)
        if tree is None:
            continue
        for decorator in _find_plugin_decorators(tree):
            plugin_id = _kw_literal_str(decorator, "id") or "<unknown>"
            out.append((path, decorator, plugin_id))
    return out


def _scan_duplicate_ids(root: Path) -> list[ShapeViolation]:
    """扫描同 ``@plugin(id=...)`` 出现在多个文件 —— 违反单一入口原则。"""
    id_to_files: dict[str, list[tuple[Path, int]]] = defaultdict(list)
    for path, decorator, plugin_id in _collect_plugin_files(root):
        if plugin_id != "<unknown>" and path.name != "__init__.py":
            id_to_files[plugin_id].append((path, getattr(decorator, "lineno", 0)))
    out: list[ShapeViolation] = []
    for plugin_id, locations in id_to_files.items():
        if len(locations) <= 1:
            continue
        for path, line in locations:
            try:
                rel = str(path.relative_to(root))
            except ValueError:
                rel = str(path.relative_to(ROOT))
            out.append(
                ShapeViolation(
                    kind=KIND_DUPLICATE_ID,
                    plugin_id=plugin_id,
                    file=rel,
                    line=line,
                    detail=f"id={plugin_id!r} 在 {len(locations)} 个文件出现",
                )
            )
    return out


def _is_legal_plugin_location(
    rel_posix: str, allowed: tuple[str, ...] = LEGAL_PLUGIN_LOCATIONS
) -> bool:
    return any(rel_posix == legal or rel_posix.startswith(legal) for legal in allowed)


def _scan_plugin_location(
    production_roots: list[Path] | None = None,
    allowed: tuple[str, ...] = LEGAL_PLUGIN_LOCATIONS,
) -> list[ShapeViolation]:
    """维度 4:``@plugin`` 装饰器出现在 ``lca/plugins/`` 与
    ``lca_kernel/events/manifest.py`` 之外。

    test fixture(@plugin(...) 仅在测试里 mock)豁免:tests/ 全子树不扫。

    ``production_roots``:扫哪些根目录;默认 ``[ROOT]``。``allowed``:合法位置白名单
    (测试可注入临时位置如 ``plugins/``)。
    """
    roots = production_roots if production_roots is not None else [ROOT]
    out: list[ShapeViolation] = []
    for path in _iter_python_files(roots):
        tree = _parse_tree(path)
        if tree is None:
            continue
        rel = _relative_to_root(path, roots)
        for decorator in _find_plugin_decorators(tree):
            if _is_legal_plugin_location(rel, allowed):
                continue
            plugin_id = _kw_literal_str(decorator, "id") or "<unknown>"
            line = getattr(decorator, "lineno", 0)
            out.append(
                ShapeViolation(
                    kind=KIND_PLUGIN_LOCATION,
                    plugin_id=plugin_id,
                    file=rel,
                    line=line,
                    detail=f"@plugin 出现在非合法位置(允许: {', '.join(allowed)})",
                )
            )
    return out


def _scan_plugin_in_init(production_roots: list[Path] | None = None) -> list[ShapeViolation]:
    """维度 7:``@plugin(...)`` 出现在 ``__init__.py``,违反 AGENTS.md §5。

    test fixture 豁免。``production_roots`` 同上。
    """
    roots = production_roots if production_roots is not None else [ROOT]
    out: list[ShapeViolation] = []
    for path in _iter_python_files(roots):
        if path.name != "__init__.py":
            continue
        tree = _parse_tree(path)
        if tree is None:
            continue
        rel = _relative_to_root(path, roots)
        for decorator in _find_plugin_decorators(tree):
            plugin_id = _kw_literal_str(decorator, "id") or "<unknown>"
            line = getattr(decorator, "lineno", 0)
            out.append(
                ShapeViolation(
                    kind=KIND_PLUGIN_IN_INIT,
                    plugin_id=plugin_id,
                    file=rel,
                    line=line,
                    detail="@plugin(...) 出现在 __init__.py(违反 AGENTS.md §5)",
                )
            )
    return out


def _load_bundle_references(bundles_glob: Path) -> list[tuple[Path, str, str]]:
    """从 ``bundles/*.yaml`` 收集所有 ``$module`` 引用,返回 (bundle, entry_id, module_path)。

    bundle 解析失败 → 静默跳过(避免 gate 因 yaml 错误误报;yaml 解析由其他工具守)。
    """
    refs: list[tuple[Path, str, str]] = []
    for bundle_path in sorted(bundles_glob.parent.glob(bundles_glob.name)):
        try:
            data = yaml.safe_load(bundle_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        entries = data.get("entries")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            module_path = entry.get("$module")
            entry_id = entry.get("id")
            if isinstance(module_path, str) and isinstance(entry_id, str):
                refs.append((bundle_path, entry_id, module_path))
    return refs


def _scan_orphan_plugins(
    walk_root: Path,
    bundles_glob: Path,
    module_root: Path | None = None,
) -> list[ShapeViolation]:
    """维度 5:``lca/plugins/`` 下的 ``@plugin`` 文件没有被任何 bundle ``$module`` 引用。

    - ``walk_root``:扫描根,递归 rglob ``.py``。
    - ``module_root``:模块路径计算的基准;``path.relative_to(module_root)`` → 模块名。
      默认等于 ``walk_root``(适用于扫描根 = 模块命名空间的根,例如 ``/tmp/xxx`` 含
      ``plugins/orphan.py`` → ``plugins.orphan``)。生产用法 ``module_root=ROOT`` 时
      ``walk_root`` 一般传 ``ROOT/lca/plugins``,``path.relative_to(ROOT)`` 给
      ``lca/plugins/orphan.py`` → ``lca.plugins.orphan``。
    """
    refs = _load_bundle_references(bundles_glob)
    referenced_modules = {module_path for _, _, module_path in refs}
    namespace_root = module_root if module_root is not None else walk_root
    out: list[ShapeViolation] = []
    for path, decorator, plugin_id in _collect_plugin_files(walk_root):
        rel = path.relative_to(namespace_root).as_posix()
        module_path = _file_to_module(rel)
        if module_path in referenced_modules:
            continue
        line = getattr(decorator, "lineno", 0)
        out.append(
            ShapeViolation(
                kind=KIND_ORPHAN_PLUGIN,
                plugin_id=plugin_id,
                file=rel,
                line=line,
                detail=f"module {module_path!r} 未被任何 bundles/*.yaml $module 引用",
            )
        )
    return out


def _scan_dead_bundle_refs(bundles_glob: Path) -> list[ShapeViolation]:
    """维度 6:bundle ``$module`` 不可 import 或 ``@plugin(id=)`` 与 entry ``id:`` 不匹配。

    不修改 sys.path:假设执行 gate 的 Python 进程能 import 仓库内的模块。
    """
    refs = _load_bundle_references(bundles_glob)
    out: list[ShapeViolation] = []
    for bundle_path, entry_id, module_path in refs:
        try:
            bundle_rel = bundle_path.relative_to(ROOT).as_posix()
        except ValueError:
            bundle_rel = bundle_path.as_posix()
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:
            out.append(
                ShapeViolation(
                    kind=KIND_DEAD_BUNDLE_REF,
                    plugin_id=entry_id,
                    file=bundle_rel,
                    line=0,
                    detail=f"$module {module_path!r} import 失败: {type(exc).__name__}: {exc}",
                )
            )
            continue
        tree = (
            ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            if getattr(module, "__file__", None)
            else None
        )
        manifest_id: str | None = None
        if tree is not None:
            for decorator in _find_plugin_decorators(tree):
                cand = _kw_literal_str(decorator, "id")
                if cand:
                    manifest_id = cand
                    break
        if manifest_id is None:
            out.append(
                ShapeViolation(
                    kind=KIND_DEAD_BUNDLE_REF,
                    plugin_id=entry_id,
                    file=bundle_rel,
                    line=0,
                    detail=f"$module {module_path!r} 中未找到 @plugin(id=...)",
                )
            )
            continue
        if manifest_id != entry_id:
            out.append(
                ShapeViolation(
                    kind=KIND_DEAD_BUNDLE_REF,
                    plugin_id=entry_id,
                    file=bundle_rel,
                    line=0,
                    detail=(f"entry id={entry_id!r} 与模块 @plugin(id={manifest_id!r}) 不一致"),
                )
            )
    return out


# ── Baseline IO ──────────────────────────────────────────────────────────


def _read_baseline(path: Path) -> dict[str, int]:
    """读基线 JSON;不存在或损坏 → 返回全 0(退化行为)。"""
    if not path.is_file():
        return dict.fromkeys(ALL_KINDS, 0)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return dict.fromkeys(ALL_KINDS, 0)
    by_kind = data.get("by_kind") if isinstance(data, dict) else None
    if not isinstance(by_kind, dict):
        return dict.fromkeys(ALL_KINDS, 0)
    return {k: int(by_kind.get(k, 0) or 0) for k in ALL_KINDS}


# ── 主入口 ───────────────────────────────────────────────────────────────


def scan(
    root: Path,
    bundles_glob: Path = DEFAULT_BUNDLES_GLOB,
    production_roots: list[Path] | None = None,
    allowed_locations: tuple[str, ...] = LEGAL_PLUGIN_LOCATIONS,
    module_root: Path | None = None,
) -> ShapeReport:
    """执行八维扫描,返回汇总。``production_roots`` / ``allowed_locations`` /
    ``module_root`` 仅供测试注入;生产用法下三项默认 ``module_root=ROOT``(让
    ``lca/plugins/foo.py`` 计算出模块名 ``lca.plugins.foo``)。
    """
    effective_module_root = module_root if module_root is not None else ROOT
    total, missing_effects = _scan_missing_effects(root)
    dual_form = _scan_dual_form_residue(root)
    duplicates = _scan_duplicate_ids(root)
    plugin_location = _scan_plugin_location(production_roots, allowed_locations)
    plugin_in_init = _scan_plugin_in_init(production_roots)
    orphan_plugins = _scan_orphan_plugins(root, bundles_glob, effective_module_root)
    dead_bundle_refs = _scan_dead_bundle_refs(bundles_glob)
    by_kind: dict[str, int] = {
        KIND_MISSING_EFFECTS: len(missing_effects),
        KIND_DUAL_FORM_RESIDUE: len(dual_form),
        KIND_DUPLICATE_ID: len(duplicates),
        KIND_PLUGIN_LOCATION: len(plugin_location),
        KIND_ORPHAN_PLUGIN: len(orphan_plugins),
        KIND_DEAD_BUNDLE_REF: len(dead_bundle_refs),
        KIND_PLUGIN_IN_INIT: len(plugin_in_init),
    }
    return ShapeReport(
        root=str(root),
        total_plugins=total,
        violations=(
            missing_effects
            + dual_form
            + duplicates
            + plugin_location
            + orphan_plugins
            + dead_bundle_refs
            + plugin_in_init
        ),
        by_kind=by_kind,
    )


def _violations_to_payload(violations: list[ShapeViolation]) -> list[dict]:
    return [
        {
            "kind": v.kind,
            "id": v.plugin_id,
            "file": v.file,
            "line": v.line,
            "detail": v.detail,
        }
        for v in violations
    ]


def emit_human(report: ShapeReport, baseline: dict[str, int]) -> None:
    """人类可读输出:违例按 kind 分组,每组按 file:line 排序;附基线对比。"""
    diffs = {k: report.by_kind.get(k, 0) - baseline.get(k, 0) for k in ALL_KINDS}
    if not any(report.by_kind.values()) and not any(diffs.values()):
        print(
            f"plugin-shape: all {report.total_plugins} plugins follow single-Manifest convention."
        )
        return
    print(
        f"plugin-shape: scanned {report.total_plugins} plugins under {report.root}; "
        f"current={report.by_kind} baseline={baseline} regression={diffs}",
        file=sys.stderr,
    )
    grouped: dict[str, list[ShapeViolation]] = defaultdict(list)
    for v in report.violations:
        grouped[v.kind].append(v)
    kind_labels = {
        KIND_MISSING_EFFECTS: "缺少 effects=",
        KIND_DUAL_FORM_RESIDUE: "双形态残留",
        KIND_DUPLICATE_ID: "同 id 镜像",
        KIND_PLUGIN_LOCATION: "@plugin 位置非法",
        KIND_ORPHAN_PLUGIN: "孤儿插件",
        KIND_DEAD_BUNDLE_REF: "死 bundle 引用",
        KIND_PLUGIN_IN_INIT: "@plugin in __init__.py",
    }
    for kind in ALL_KINDS:
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
        "docs/notes/proposed/seam/2026-09-04-plugin-universe-single-entry.md (PR-1).\n"
        "delete-when: missing_effects / dual_form_residue / duplicate_id → Phase C 全部清零; "
        "plugin_location → PR-9 全部归位; "
        "orphan_plugin → PR-3 全部接入 bundle; "
        "dead_bundle_ref → PR-3 全部修正; "
        "plugin_in_init → AGENTS.md §5 范式落地(无存量)。",
        file=sys.stderr,
    )


def emit_json(report: ShapeReport, baseline: dict[str, int]) -> None:
    """机器可读 JSON:供 notes-check / lca-ops audit-plugin-shape 串联。"""
    diffs = {k: report.by_kind.get(k, 0) - baseline.get(k, 0) for k in ALL_KINDS}
    print(
        json.dumps(
            {
                "root": report.root,
                "total_plugins": report.total_plugins,
                "by_kind": report.by_kind,
                "baseline": baseline,
                "regression": diffs,
                "violations": _violations_to_payload(report.violations),
            },
            indent=2,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument(
        "--bundles-glob",
        type=Path,
        default=DEFAULT_BUNDLES_GLOB,
        help="bundles yaml glob (default: bundles/*.yaml)",
    )
    parser.add_argument(
        "--baseline-path",
        type=Path,
        default=DEFAULT_BASELINE_PATH,
        help="baseline JSON 路径",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="写基线快照到 docs/notes/baselines/plugin-shape.json",
    )
    parser.add_argument(
        "--no-baseline-gate",
        action="store_true",
        help="禁用基线对比 gate(老行为:有违例就返回 1)",
    )
    args = parser.parse_args(argv)

    report = scan(args.root, args.bundles_glob)

    if args.baseline:
        args.baseline_path.parent.mkdir(parents=True, exist_ok=True)
        args.baseline_path.write_text(
            json.dumps(
                {
                    "root": report.root,
                    "total_plugins": report.total_plugins,
                    "by_kind": report.by_kind,
                    "violations": _violations_to_payload(report.violations),
                },
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"baseline written: {args.baseline_path}")
        return 0

    baseline = _read_baseline(args.baseline_path)
    regression = {k: report.by_kind.get(k, 0) - baseline.get(k, 0) for k in ALL_KINDS}
    has_regression = any(v > 0 for v in regression.values())

    if args.json:
        emit_json(report, baseline)
    else:
        emit_human(report, baseline)

    if args.no_baseline_gate:
        return 1 if report.violations else 0
    return 1 if has_regression else 0


if __name__ == "__main__":
    sys.exit(main())
