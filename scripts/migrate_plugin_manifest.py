"""One-shot AST migration: 53 legacy @plugin decorators → canonical form.

Rules (per ADR-0062 §1):
1. name="..." -> id="..."
2. layer="service"|"provider"|"behavior"|"guard"|"sensor"
      -> layer="L0"|"L1" + kind=PluginKind.{SEAM|PROVIDER|PRIMITIVE}
3. side_effects="..." -> effects="..." (same string, EffectClass accepts strings)
4. policy_class="..." -> deleted
5. import path lca.plugins._cordis_adapter -> lca.harness.plugin_api
   (preserves PluginKind / EffectClass re-exports; adds missing imports)

Run: uv run python scripts/migrate_plugin_manifest.py [--dry-run] [--paths=...]
Verify: ruff + mypy + tests/test_plugin_alignment.py.
"""

from __future__ import annotations

import argparse
import ast
import pathlib
import sys
from collections.abc import Iterable

PLUGIN_ROOT = pathlib.Path("lca/plugins")

LEGACY_LAYER_MAP: dict[str, tuple[str, str]] = {
    # legacy layer -> (canonical L?, canonical PluginKind)
    "service": ("L0", "PluginKind.SEAM"),
    "provider": ("L0", "PluginKind.PROVIDER"),
    "behavior": ("L1", "PluginKind.PRIMITIVE"),
    "guard": ("L1", "PluginKind.PRIMITIVE"),
    "sensor": ("L1", "PluginKind.PRIMITIVE"),
}

NEEDS_PLUGIN_KIND = {"service", "provider", "behavior", "guard", "sensor"}


def _parse_arg_value(node: ast.AST) -> str:
    """Render a literal kwarg value back to source."""
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover — defensive
        return repr("")


def _is_string_literal(node: ast.AST, value: str) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value == value


def _replace_kwarg(kwargs: list[ast.keyword], name: str, new_node: ast.AST) -> None:
    """Replace (or insert) kwarg `name=new_node`. Preserves ordering otherwise."""
    for i, kw in enumerate(kwargs):
        if kw.arg == name:
            kwargs[i] = ast.keyword(arg=name, value=new_node)
            return
    kwargs.append(ast.keyword(arg=name, value=new_node))


def _drop_kwarg(kwargs: list[ast.keyword], name: str) -> None:
    kwargs[:] = [kw for kw in kwargs if kw.arg != name]


def _has_kwarg(kwargs: list[ast.keyword], name: str) -> bool:
    return any(kw.arg == name for kw in kwargs)


def _get_kwarg(kwargs: list[ast.keyword], name: str) -> ast.keyword | None:
    for kw in kwargs:
        if kw.arg == name:
            return kw
    return None


def migrate_decorator(call: ast.Call) -> set[str]:
    """Rewrite one `@plugin(...)` call. Returns needed extra symbols."""
    kwargs: list[ast.keyword] = list(call.keywords)
    needs: set[str] = set()

    # 1. name=... -> id=...
    name_kw = _get_kwarg(kwargs, "name")
    id_kw = _get_kwarg(kwargs, "id")
    if name_kw is not None and id_kw is None:
        new_id = ast.keyword(arg="id", value=name_kw.value)
        kwargs[:] = [kw for kw in kwargs if kw.arg != "name"]
        # id= goes first in canonical form (matches the 6 canonical plugins)
        kwargs.insert(0, new_id)

    # 2. legacy layer -> (L?, kind)
    layer_kw = _get_kwarg(kwargs, "layer")
    if (
        layer_kw is not None
        and isinstance(layer_kw.value, ast.Constant)
        and isinstance(layer_kw.value.value, str)
    ):
        legacy = layer_kw.value.value
        if legacy in LEGACY_LAYER_MAP:
            canonical_layer, kind_expr = LEGACY_LAYER_MAP[legacy]
            # Replace layer with canonical
            layer_kw.value = ast.Constant(value=canonical_layer)
            # Insert kind= if not already present
            if not _has_kwarg(kwargs, "kind"):
                # kind=PluginKind.X (rendered as a Name/Attribute)
                kind_node = ast.parse(kind_expr + "()", mode="eval").body  # type: ignore[arg-type]
                # We want just `PluginKind.SEAM`, not a call. Re-parse cleanly:
                kind_node = ast.parse(kind_expr, mode="eval").body  # type: ignore[arg-type]
                kwargs.append(ast.keyword(arg="kind", value=kind_node))
                needs.add("PluginKind")

    # 3. side_effects="..." -> effects="..."
    side_kw = _get_kwarg(kwargs, "side_effects")
    if side_kw is not None:
        if _has_kwarg(kwargs, "effects"):
            _drop_kwarg(kwargs, "side_effects")
        else:
            side_kw.arg = "effects"
            # Keep as string — _normalize_effects accepts strings.

    # 4. policy_class=... -> delete
    _drop_kwarg(kwargs, "policy_class")

    call.keywords = kwargs
    return needs


def rewrite_imports(tree: ast.Module, needed_symbols: set[str]) -> ast.Module:
    """Rewrite `from lca.plugins._cordis_adapter import plugin` and ensure PluginKind is imported.

    Strategy: build a fresh body list with the adapter import replaced
    (module changed, names extended with any newly-needed symbols).
    """
    new_body: list[ast.stmt] = []
    adapter_seen = False

    for stmt in tree.body:
        if isinstance(stmt, ast.ImportFrom) and stmt.module == "lca.plugins._cordis_adapter":
            existing_names = {alias.name for alias in stmt.names}
            target_names: list[str] = []
            if "plugin" in existing_names:
                target_names.append("plugin")
            for sym in sorted(needed_symbols):
                if sym not in existing_names:
                    target_names.append(sym)
            stmt.module = "lca.harness.plugin_api"
            stmt.names = [ast.alias(name=n) for n in target_names]
            new_body.append(stmt)
            adapter_seen = True
            continue
        new_body.append(stmt)

    if not adapter_seen and needed_symbols:
        # No adapter import existed; insert a fresh one after __future__.
        names = ["plugin"]
        for sym in sorted(needed_symbols):
            names.append(sym)
        new_import = ast.ImportFrom(
            module="lca.harness.plugin_api",
            names=[ast.alias(name=n) for n in names],
            level=0,
        )
        insert_at = 0
        for i, stmt in enumerate(new_body):
            if isinstance(stmt, ast.ImportFrom) and stmt.module == "__future__":
                insert_at = i + 1
        new_body.insert(insert_at, new_import)

    tree.body = new_body
    return tree


def needs_kind_import(tree: ast.Module) -> bool:
    """Detect whether the source file (pre-migration) already uses PluginKind.

    Caller must invoke this BEFORE migrate_decorator() adds any PluginKind
    references — otherwise the freshly added `PluginKind.X` would itself
    trigger a positive match. Kept as a public helper for callers that
    want to skip the migration in fully-canonical files.
    """
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "PluginKind"
        ):
            return True
    return False


def needs_effectclass_import(tree: ast.Module) -> bool:
    """Detect pre-migration use of EffectClass (canonical form)."""
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == "EffectClass"
        ):
            return True
    return False


def migrate_file(path: pathlib.Path) -> bool:
    """Return True if file was rewritten."""
    src = path.read_text()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False

    needed: set[str] = set()
    changed = False

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "plugin"
        ):
            before_kwargs = list(node.keywords)
            extra = migrate_decorator(node)
            if list(node.keywords) != before_kwargs:
                changed = True
            needed |= extra

    if not changed:
        return False

    # rewrite_imports itself dedupes against existing import names; no
    # need to manually drop needs based on post-migration AST.
    rewrite_imports(tree, needed)

    new_src = ast.unparse(tree)
    # ast.unparse drops comments and collapses blank lines; ruff format
    # the caller (see PR-1.b top-level script) restores canonical layout.
    path.write_text(new_src + "\n")
    return True


def discover_targets() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for path in sorted(PLUGIN_ROOT.rglob("*.py")):
        if path.name in {"__init__.py", "_cordis_adapter.py"} or "/__pycache__/" in str(path):
            continue
        src = path.read_text()
        if "name=" not in src and "side_effects=" not in src:
            continue
        # Confirm @plugin(...) call exists
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "plugin"
            ):
                out.append(path)
                break
    return out


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true", help="Print files that would change, don't write."
    )
    parser.add_argument("--paths", nargs="*", help="Override file list.")
    args = parser.parse_args(list(argv) if argv is not None else None)

    targets = [pathlib.Path(p) for p in args.paths] if args.paths else discover_targets()
    if not targets:
        print("No legacy @plugin decorators found.")
        return 0

    changed = 0
    for path in targets:
        if args.dry_run:
            print(f"[dry-run] would rewrite {path}")
            changed += 1
        elif migrate_file(path):
            print(f"rewrote {path}")
            changed += 1
    print(f"\n{changed} file(s) {'would be ' if args.dry_run else ''}rewritten")
    return 0


if __name__ == "__main__":
    sys.exit(main())
