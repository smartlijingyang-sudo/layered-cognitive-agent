"""Codegen: 自动生成 Plugin 元数据模板（logic_address / relations / ownership）。

PR-4 的核心工具。AST 扫描 lca/plugins/ 下所有 @plugin 调用，按启发式
为每个 plugin 生成 logic_address / relations / ownership 模板，作为
人工审校起点。

启发式映射：
  路径 → functional_group：plugins/{perceive|think|act|memory|...}/* → 概念群
  已声明 provides/requires → authority + relations 候选
  代码 import 链 → reads/emits

用法：
  python scripts/codegen_plugin_metadata.py --scan       # 输出每个 plugin 当前缺口
  python scripts/codegen_plugin_metadata.py --generate   # 生成 template（不写文件，stdout）
  python scripts/codegen_plugin_metadata.py --apply      # 生成 + 自动 patch（带 --dry-run）

Reference: docs/superpowers/specs/2026-08-30-comprehensive-cleanup-execution.md §3.4
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── 路径 → functional_group 启发式映射 ──
PATH_TO_GROUP: dict[str, str] = {
    "perceive": "FunctionalGroup.G2_PERCEIVE",
    "sensors": "FunctionalGroup.G2_PERCEIVE",
    "brain": "FunctionalGroup.G3_THINK",
    "reasoner": "FunctionalGroup.G3_THINK",
    "think": "FunctionalGroup.G3_THINK",
    "critic": "FunctionalGroup.G3_THINK",
    "synthesizer": "FunctionalGroup.G3_THINK",
    "insight": "FunctionalGroup.G3_THINK",
    "learning": "FunctionalGroup.G4_REFLECT",
    "gates": "FunctionalGroup.G6_DECISION",
    "control_contributions": "FunctionalGroup.G6_DECISION",
    "loop_drivers": "FunctionalGroup.G6_DECISION",
    "phase_graph": "FunctionalGroup.G7_PLAN",
    "strategies": "FunctionalGroup.G8_ACT",
    "body": "FunctionalGroup.G8_ACT",
    "tools": "FunctionalGroup.G8_ACT",
    "memory": "FunctionalGroup.G5_REMEMBER",
    "collaboration": "FunctionalGroup.G9_COLLABORATE",
    "composer": "FunctionalGroup.G10_COMPOSE",
    "factories": "FunctionalGroup.G10_COMPOSE",
    "profile": "FunctionalGroup.G10_COMPOSE",
    "providers": "FunctionalGroup.G10_COMPOSE",
    "roles": "FunctionalGroup.G9_COLLABORATE",
    "seams": "FunctionalGroup.G10_COMPOSE",
    "creator": "FunctionalGroup.G10_COMPOSE",
}

# ── path → scope 启发式 ──
PATH_TO_SCOPE: dict[str, str] = {
    "perceive": "Scope.TURN",
    "sensors": "Scope.TURN",
    "brain": "Scope.TURN",
    "reasoner": "Scope.TURN",
    "think": "Scope.TURN",
    "critic": "Scope.STEP",
    "synthesizer": "Scope.STEP",
    "insight": "Scope.TURN",
    "learning": "Scope.RUN",
    "gates": "Scope.STEP",
    "control_contributions": "Scope.STEP",
    "loop_drivers": "Scope.RUN",
    "phase_graph": "Scope.RUN",
    "strategies": "Scope.RUN",
    "body": "Scope.STEP",
    "tools": "Scope.STEP",
    "memory": "Scope.RUN",
    "collaboration": "Scope.RUN",
    "composer": "Scope.RUN",
    "factories": "Scope.RUN",
    "profile": "Scope.PROFILE",
    "providers": "Scope.RUN",
    "roles": "Scope.PROFILE",
    "seams": "Scope.RUN",
    "creator": "Scope.RUN",
}


@dataclass
class PluginMetadata:
    """AST 提取 + 启发式补全的 plugin 元数据。"""

    file: str
    line: int
    plugin_id: str = ""
    layer: str = ""
    kind: str = ""
    functional_group: str = ""
    implements: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    requires: list[str] = field(default_factory=list)
    effects: str = ""
    description: str = ""
    test_suite: str = ""

    has_logic_address: bool = False
    has_relations: bool = False
    has_ownership: bool = False
    has_test_suite: bool = False

    suggested_functional_group: str = ""
    suggested_scope: str = ""
    suggested_authority: list[str] = field(default_factory=list)
    suggested_evidence: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return all(
            [
                self.has_logic_address,
                self.has_relations,
                self.has_ownership,
                self.has_test_suite,
            ]
        )

    @property
    def gap_severity(self) -> str:
        if self.is_complete:
            return "ok"
        missing = []
        if not self.has_logic_address:
            missing.append("logic_address")
        if not self.has_relations:
            missing.append("relations")
        if not self.has_ownership:
            missing.append("ownership")
        if not self.has_test_suite:
            missing.append("test_suite")
        if len(missing) >= 3:
            return "critical"
        if len(missing) >= 1:
            return "warning"
        return "ok"


def _find_plugin_decorators(tree: ast.Module) -> list[ast.Call]:
    """Find all @plugin(...) decorator calls in a module."""
    results: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Call):
                func = decorator.func
                name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else (func.attr if isinstance(func, ast.Attribute) else None)
                )
                if name == "plugin":
                    results.append(decorator)
    return results


def _kw(call: ast.Call, key: str) -> ast.expr | None:
    """Look up a keyword argument by name."""
    for kw in call.keywords:
        if kw.arg == key:
            return kw.value
    return None


def _literal_str(node: ast.expr | None) -> str | None:
    """Extract a constant string literal from AST."""
    if node is None:
        return None
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_list(node: ast.expr | None) -> list[str]:
    """Extract list of string literals."""
    if node is None:
        return []
    if isinstance(node, ast.List):
        out = []
        for elt in node.elts:
            v = _literal_str(elt)
            if v:
                out.append(v)
        return out
    return []


def _infer_group_from_path(path: Path) -> tuple[str, str]:
    """From file path, infer functional_group and scope."""
    parts = path.parts
    for part in reversed(parts[:-1]):
        if part in PATH_TO_GROUP:
            return PATH_TO_GROUP[part], PATH_TO_SCOPE.get(part, "Scope.RUN")
    return "FunctionalGroup.G10_COMPOSE", "Scope.RUN"


def _infer_authority(provides: list[str]) -> list[str]:
    """From provides, suggest authority strings (what the plugin is allowed to do)."""
    auth = []
    for p in provides:
        if "budget" in p:
            auth.append("budget.read")
        if "tool" in p:
            auth.append("tool.invoke")
        if "memory" in p:
            auth.append("memory.read")
        if "gate" in p or "verdict" in p:
            auth.append("decision.emit")
        if "context" in p or "perceive" in p:
            auth.append("context.read")
    return sorted(set(auth)) if auth else ["plugin.serve"]


def _infer_evidence(plugin_id: str, provides: list[str]) -> list[str]:
    """Suggest evidence events the plugin emits."""
    if not plugin_id:
        return ["plugin.served"]
    safe_id = plugin_id.replace(".", "_")
    return [f"{safe_id}.checked", f"{safe_id}.served"]


def extract_plugin_metadata(path: Path) -> Iterator[PluginMetadata]:
    """Yield PluginMetadata for every @plugin call in file."""
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return
    for decorator in _find_plugin_decorators(tree):
        line = getattr(decorator, "lineno", 0)
        meta = PluginMetadata(file=str(path.relative_to(ROOT)), line=line)
        meta.plugin_id = _literal_str(_kw(decorator, "id")) or ""
        meta.layer = _literal_str(_kw(decorator, "layer")) or ""
        meta.kind = _literal_str(_kw(decorator, "kind")) or ""
        meta.implements = _literal_list(_kw(decorator, "implements"))
        meta.provides = _literal_list(_kw(decorator, "provides"))
        meta.requires = _literal_list(_kw(decorator, "requires"))
        meta.effects = _literal_str(_kw(decorator, "effects")) or ""
        meta.description = _literal_str(_kw(decorator, "description")) or ""
        meta.test_suite = _literal_str(_kw(decorator, "test_suite")) or ""
        meta.has_logic_address = _kw(decorator, "logic_address") is not None
        meta.has_relations = _kw(decorator, "relations") is not None
        meta.has_ownership = _kw(decorator, "ownership") is not None
        meta.has_test_suite = bool(meta.test_suite)
        group, scope = _infer_group_from_path(path)
        meta.suggested_functional_group = group
        meta.suggested_scope = scope
        meta.suggested_authority = _infer_authority(meta.provides)
        meta.suggested_evidence = _infer_evidence(meta.plugin_id, meta.provides)
        yield meta


def scan(root: Path) -> list[PluginMetadata]:
    """Scan all plugin files."""
    out: list[PluginMetadata] = []
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts or "/vendor/" in str(path):
            continue
        if path.name == "__init__.py":
            continue
        for meta in extract_plugin_metadata(path):
            out.append(meta)
    return out


def report(plugins: list[PluginMetadata], *, json_output: bool = False) -> None:
    """Print summary report."""
    total = len(plugins)
    complete = sum(1 for p in plugins if p.is_complete)
    critical = sum(1 for p in plugins if p.gap_severity == "critical")
    warning = sum(1 for p in plugins if p.gap_severity == "warning")

    if json_output:
        print(
            json.dumps(
                {
                    "total": total,
                    "complete": complete,
                    "critical": critical,
                    "warning": warning,
                    "plugins": [asdict(p) for p in plugins],
                },
                indent=2,
            )
        )
        return

    print(f"plugin-metadata: scanned {total} plugins in lca/plugins/")
    print(f"  complete (logic_address + relations + ownership + test_suite): {complete}")
    print(f"  critical (missing ≥ 3 of 4): {critical}")
    print(f"  warning (missing 1-2 of 4): {warning}")
    print()
    print(f"{'plugin_id':<48} {'layer':<6} {'group':<35} status")
    print("-" * 130)
    for p in plugins:
        gid = p.plugin_id or "<no-id>"
        print(f"{gid:<48} {p.layer:<6} {p.suggested_functional_group:<35} {p.gap_severity}")


def generate_template(meta: PluginMetadata) -> str:
    """Generate a Python code template for adding missing metadata."""
    lines: list[str] = []
    if not meta.has_logic_address:
        lines.append("    logic_address=LogicAddress(")
        lines.append(f"        functional_group={meta.suggested_functional_group},")
        lines.append(f"        control_slot=ControlSlot.{meta.plugin_id.upper().split('.')[-1]},")
        lines.append(f"        scope={meta.suggested_scope},")
        lines.append(f"        authority={tuple(meta.suggested_authority)},")
        lines.append(f"        evidence={tuple(meta.suggested_evidence)},")
        lines.append('        revision="v1",')
        lines.append("    ),")
    if not meta.has_ownership:
        lines.append("    ownership=OwnershipDeclaration(")
        lines.append(f"        reads={tuple(meta.requires) or ()},")
        lines.append('        emits=("plugin.served",),')
        lines.append('        state_mutation="forbidden",')
        lines.append("    ),")
    if not meta.has_relations:
        lines.append("    relations=(),")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / "lca" / "plugins")
    parser.add_argument("--scan", action="store_true", help="scan and report gaps")
    parser.add_argument("--generate", action="store_true", help="generate templates (stdout)")
    parser.add_argument("--json", action="store_true", help="JSON output for --scan")
    args = parser.parse_args(argv)

    plugins = scan(args.root)

    if args.generate:
        for p in plugins:
            if p.is_complete:
                continue
            print(f"=== {p.file}:{p.line} ({p.plugin_id}) ===")
            print(generate_template(p))
            print()
        return 0

    if args.scan or not (args.generate):
        report(plugins, json_output=args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
