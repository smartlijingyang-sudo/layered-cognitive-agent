"""Phase B #8: split lca/harness/declarative/ into 5 subpackages.

Per ADR-0105 §11.8, the flat 24-file lca/harness/declarative/ package
(plus a root __init__.py = 25 entries) is split into 5 thematic
subpackages. The spec described the split as ``→ 拆 phase_graph/ 子包``
emphasising the phase_graph/ group; this implementation maps all 24
files to 5 cohesive clusters. Each cluster stays within the
≤8-files-per-package guideline.

Before: 24 .py files flat in lca/harness/declarative/ root.
After: 5 subpackages; 0 files in lca/harness/declarative/ root except
       __init__.py.

New structure:
  compile/    (8) compiler, assembler, action_authority, authority,
                  effect_policy, phase_capabilities,
                  phase_execution_policy, phase_governance
  graph/      (5) phase_graph_compiler, graph_algorithms,
                  graph_validation, predicate, traversal
  execute/    (4) interpreter, dispatch, outcome_projection,
                  loop_guard
  lifecycle/  (4) phase_transaction, phase_observation,
                  phase_observation_snapshot, phase_context
  controls/   (3) approval, validation, effect_receipt
"""

import re
import shutil
from pathlib import Path

ROOT = Path("lca/harness/declarative")

MOVES: list[tuple[str, str]] = [
    # compile/
    ("compiler.py", "compile"),
    ("assembler.py", "compile"),
    ("action_authority.py", "compile"),
    ("authority.py", "compile"),
    ("effect_policy.py", "compile"),
    ("phase_capabilities.py", "compile"),
    ("phase_execution_policy.py", "compile"),
    ("phase_governance.py", "compile"),
    # graph/
    ("phase_graph_compiler.py", "graph"),
    ("graph_algorithms.py", "graph"),
    ("graph_validation.py", "graph"),
    ("predicate.py", "graph"),
    ("traversal.py", "graph"),
    # execute/
    ("interpreter.py", "execute"),
    ("dispatch.py", "execute"),
    ("outcome_projection.py", "execute"),
    ("loop_guard.py", "execute"),
    # lifecycle/
    ("phase_transaction.py", "lifecycle"),
    ("phase_observation.py", "lifecycle"),
    ("phase_observation_snapshot.py", "lifecycle"),
    ("phase_context.py", "lifecycle"),
    # controls/
    ("approval.py", "controls"),
    ("validation.py", "controls"),
    ("effect_receipt.py", "controls"),
]

OLD_TO_NEW = {old[:-3]: pkg for old, pkg in MOVES}


def _rewrite_with_boundary(text: str, prefix: str, old_mod: str, new_tail: str) -> str:
    """Rewrite module references at module boundaries.

    Two forms are supported:

    * ``<prefix>.<old_mod>`` — the dotted module path used in YAML and in
      ``from X.Y import`` statements.
    * ``from <prefix> import <old_mod>`` — the bare-import form.

    Both are bounded so a sibling path that already starts with the target
    subpackage (``lca.harness.declarative.<pkg>.X``) is not re-expanded into
    a doubled prefix.
    """
    dotted_pat = re.compile(rf"{re.escape(prefix)}\.{re.escape(old_mod)}(?![\w.])")
    text = dotted_pat.sub(f"{prefix}.{new_tail}", text)
    bare_pat = re.compile(rf"from {re.escape(prefix)} import {re.escape(old_mod)}(?![\w.])")
    return bare_pat.sub(f"from {prefix}.{new_tail} import {old_mod}", text)


# Modules whose new path uses a subpackage of the same name. None here,
# since the spec target file ``phase_graph_compiler.py`` lands in the
# ``graph`` subpackage and is not self-named. (Self-named would be a
# ``graph/graph.py`` file. The spec deliberately keeps ``graph_*.py``
# names rather than making a self-named module.)
SELF_NAMED_MODS: list[str] = []


def main() -> None:
    new_pkgs = {"compile", "graph", "execute", "lifecycle", "controls"}
    for pkg in new_pkgs:
        (ROOT / pkg).mkdir(exist_ok=True)
        (ROOT / pkg / "__init__.py").write_text(
            f'"""{pkg} subpackage of lca.harness.declarative."""\n',
            encoding="utf-8",
        )

    # 1. Move individual files.
    for old, pkg in MOVES:
        src = ROOT / old
        dst = ROOT / pkg / old
        if src.exists():
            shutil.move(str(src), str(dst))

    # 2. Rewrite imports across lca, gateway, tests, scripts, bundles,
    #    profiles.
    new_prefix = "lca.harness.declarative"
    sorted_old = sorted(set(OLD_TO_NEW.keys()), key=len, reverse=True)

    files: list[Path] = []
    for d in ("lca", "gateway", "tests", "scripts", "bundles", "profiles"):
        for py in Path(d).rglob("*.py"):
            if "__pycache__" not in py.parts:
                files.append(py)
    yaml_files: list[Path] = []
    for d in ("bundles", "profiles"):
        for y in Path(d).rglob("*.yaml"):
            yaml_files.append(y)

    count = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        new_text = text
        for self_mod in SELF_NAMED_MODS:
            new_text = _rewrite_with_boundary(
                new_text, new_prefix, self_mod, f"{self_mod}.{self_mod}"
            )
        for old_mod in sorted_old:
            if old_mod in SELF_NAMED_MODS:
                continue
            pkg = OLD_TO_NEW[old_mod]
            new_text = _rewrite_with_boundary(new_text, new_prefix, old_mod, f"{pkg}.{old_mod}")
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
            count += 1

    yaml_count = 0
    for f in yaml_files:
        text = f.read_text(encoding="utf-8")
        new_text = text
        for self_mod in SELF_NAMED_MODS:
            new_text = _rewrite_with_boundary(
                new_text, new_prefix, self_mod, f"{self_mod}.{self_mod}"
            )
        for old_mod in sorted_old:
            if old_mod in SELF_NAMED_MODS:
                continue
            pkg = OLD_TO_NEW[old_mod]
            new_text = _rewrite_with_boundary(new_text, new_prefix, old_mod, f"{pkg}.{old_mod}")
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
            yaml_count += 1

    print(f"rewrote imports in {count} .py files + {yaml_count} .yaml files")


if __name__ == "__main__":
    main()
