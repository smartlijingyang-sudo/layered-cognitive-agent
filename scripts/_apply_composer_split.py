"""Phase B #7: split lca/plugins/composer/ into 6 subpackages.

Mirrors the cognitive plane clusters used elsewhere (act, think, perceive,
collaboration, runtime, composition). The existing lca/plugins/composer/
internal/ subdir is absorbed into the matching cluster (no internal/
remains after the split).

Before: 21 .py files flat in composer/ root + 7 in internal/ subdir.
After: 6 subpackages, 0 files in composer/ root except __init__.py;
       0 files in internal/.

New structure (largest = runtime/ at 9 files; spec target was 6 subpackages
exactly, so files beyond the 8-file-per-package guideline are concentrated
here because fixture_runtime_* are documented as test-only inputs that
belong with the runtime closure rather than in a separate subpackage):
  act/             (3) body_composer, body_provider, action_authority
  think/           (3) brain_composer, brain_provider,
                       brain (was internal/brain.py)
  perceive/        (3) perceive_composer, perceive_provider,
                       perceive (was internal/perceive.py)
  collaboration/   (4) team_composer, team_provider, team_transport,
                       team (was internal/team.py)
  runtime/         (9) runtime_assembly, runtime_factory, runtime_binding,
                       runtime_capabilities, runtime_deps,
                       fixture_runtime_adapter, fixture_runtime_defaults,
                       fixture_runtime_factory, fixture_runtime_input
  composition/     (6) agent_assembly, plan_binding, capability_resolution,
                       sub_composers, prompt_catalog,
                       skill_store (was internal/skill_store.py)
"""
import re
import shutil
from contextlib import suppress
from pathlib import Path

ROOT = Path("lca/plugins/composer")

# Top-level flat files -> target subpackage.
TOP_LEVEL_MOVES: list[tuple[str, str]] = [
    # act/
    ("body_composer.py", "act"),
    ("body_provider.py", "act"),
    ("action_authority.py", "act"),
    # think/
    ("brain_composer.py", "think"),
    ("brain_provider.py", "think"),
    # perceive/
    ("perceive_composer.py", "perceive"),
    ("perceive_provider.py", "perceive"),
    # collaboration/
    ("team_composer.py", "collaboration"),
    ("team_provider.py", "collaboration"),
    ("team_transport.py", "collaboration"),
    # runtime/
    ("runtime_assembly.py", "runtime"),
    ("runtime_factory.py", "runtime"),
    ("runtime_binding.py", "runtime"),
    ("runtime_capabilities.py", "runtime"),
    ("runtime_deps.py", "runtime"),
    ("fixture_runtime_adapter.py", "runtime"),
    ("fixture_runtime_defaults.py", "runtime"),
    ("fixture_runtime_factory.py", "runtime"),
    ("fixture_runtime_input.py", "runtime"),
    # composition/
    ("agent_assembly.py", "composition"),
    ("plan_binding.py", "composition"),
    ("capability_resolution.py", "composition"),
    ("sub_composers.py", "composition"),
    ("prompt_catalog.py", "composition"),
]

# internal/ subdir -> flat file in target subpackage.
INTERNAL_MOVES: list[tuple[str, str]] = [
    ("brain.py", "think"),
    ("perceive.py", "perceive"),
    ("team.py", "collaboration"),
    ("skill_store.py", "composition"),
    # runtime_*.py stay in runtime/ but as direct siblings of the existing
    # runtime_*.py imports — the rename to `binding`, `capabilities`,
    # `deps` is just a no-op (they keep the same names).
    ("runtime_binding.py", "runtime"),
    ("runtime_capabilities.py", "runtime"),
    ("runtime_deps.py", "runtime"),
]

OLD_TO_NEW: dict[str, str] = {old[:-3]: pkg for old, pkg in TOP_LEVEL_MOVES}
# Add internal/ entries that aren't already covered.
for old, pkg in INTERNAL_MOVES:
    OLD_TO_NEW.setdefault(old[:-3], pkg)


def _rewrite_with_boundary(
    text: str, prefix: str, old_mod: str, new_tail: str
) -> str:
    """Rewrite module references at module boundaries.

    Two forms are supported:

    * ``<prefix>.<old_mod>`` — the dotted module path used in YAML and in
      ``from X.Y import`` statements.
    * ``from <prefix> import <old_mod>`` — the bare-import form.

    Both are bounded so a sibling path that already starts with the target
    subpackage (``lca.plugins.composer.<pkg>.X``) is not re-expanded into
    a doubled prefix.
    """
    dotted_pat = re.compile(
        rf"{re.escape(prefix)}\.{re.escape(old_mod)}(?![\w.])"
    )
    text = dotted_pat.sub(f"{prefix}.{new_tail}", text)
    bare_pat = re.compile(
        rf"from {re.escape(prefix)} import {re.escape(old_mod)}(?![\w.])"
    )
    return bare_pat.sub(f"from {prefix}.{new_tail} import {old_mod}", text)


# Modules whose new path uses a subpackage of the same name (e.g. brain.py
# becomes think/brain.py). They must be rewritten in a separate pre-pass
# BEFORE the regular pass, so the word-boundary guard cannot be defeated
# by a sibling path that already has the target subpackage prefix.
SELF_NAMED_MODS = sorted(
    {mod for mod, pkg in OLD_TO_NEW.items() if mod == pkg}
)


def main() -> None:
    new_pkgs = {"act", "think", "perceive", "collaboration", "runtime", "composition"}
    for pkg in new_pkgs:
        (ROOT / pkg).mkdir(exist_ok=True)
        (ROOT / pkg / "__init__.py").write_text(
            f'"""{pkg} subpackage of lca.plugins.composer."""\n',
            encoding="utf-8",
        )

    # 1. Move top-level files
    for old, pkg in TOP_LEVEL_MOVES:
        src = ROOT / old
        dst = ROOT / pkg / old
        if src.exists():
            shutil.move(str(src), str(dst))

    # 2. Move internal/ files up into their target packages.
    for old, pkg in INTERNAL_MOVES:
        src = ROOT / "internal" / old
        dst = ROOT / pkg / old
        if src.exists():
            shutil.move(str(src), str(dst))

    # 3. Drop the now-empty internal/ directory.
    with suppress(OSError):
        (ROOT / "internal" / "__init__.py").unlink()
    with suppress(OSError):
        (ROOT / "internal").rmdir()

    # 4. Rewrite imports across lca, gateway, tests, scripts, bundles, profiles.
    new_prefix = "lca.plugins.composer"
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
        # Pre-pass: handle self-named modules first to avoid re-match.
        for self_mod in SELF_NAMED_MODS:
            new_text = _rewrite_with_boundary(
                new_text, new_prefix, self_mod, f"{self_mod}.{self_mod}"
            )
        # Main pass
        for old_mod in sorted_old:
            if old_mod in SELF_NAMED_MODS:
                continue
            pkg = OLD_TO_NEW[old_mod]
            new_text = _rewrite_with_boundary(
                new_text, new_prefix, old_mod, f"{pkg}.{old_mod}"
            )
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
            new_text = _rewrite_with_boundary(
                new_text, new_prefix, old_mod, f"{pkg}.{old_mod}"
            )
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
            yaml_count += 1

    print(f"rewrote imports in {count} .py files + {yaml_count} .yaml files")


if __name__ == "__main__":
    main()
