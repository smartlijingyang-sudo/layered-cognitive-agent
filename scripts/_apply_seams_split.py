"""Phase B #5: rename lca/plugins/seam_definitions/ to seams/ + split into 9 subpackages.

Renames seam_definitions/ to seams/ per naming-constitution §10.1, then
groups the 38 root files + existing observability/ subdir into 9 subpackages.

  state/          (4) state_store.py, run_mode_registry.py,
                       runtime_lifecycle_registry.py, component_registry.py
  perceive/       (2) observability_service.py, phase_observer_registry.py
  think/          (4) reasoner_template_catalog.py, system_prompt.py,
                       llm.py, llm_resolver.py
  gate/           (2) gate_chain_composer.py, decision_classifier.py
  act/            (6) action_handler.py, delta_handler.py, effect_handler.py,
                       tools.py, sandbox.py, transport.py
  memory/         (7) memory.py, skills.py, attachment.py, workspace.py,
                       file_store.py, search.py, remember_effects.py
  collaboration/  (7) team_seam.py, team_caster.py,
                       team_casting_prompt_renderer.py, team_role_library.py,
                       team_communication.py, team_shared_memory.py,
                       session_service.py
  journal/        (4) artifact_closure.py, composition_invariant.py,
                       journal_store.py, journal_store_factories.py
  observability/ (17) existing subdir, moved as-is
"""

import shutil
from contextlib import suppress
from pathlib import Path

ROOT = Path("lca/plugins/seam_definitions")
DEST_ROOT = Path("lca/plugins/seams")

MOVES = [
    ("state_store.py", "state"),
    ("run_mode_registry.py", "state"),
    ("runtime_lifecycle_registry.py", "state"),
    ("component_registry.py", "state"),
    ("observability_service.py", "perceive"),
    ("phase_observer_registry.py", "perceive"),
    ("reasoner_template_catalog.py", "think"),
    ("system_prompt.py", "think"),
    ("llm.py", "think"),
    ("llm_resolver.py", "think"),
    ("gate_chain_composer.py", "gate"),
    ("decision_classifier.py", "gate"),
    ("action_handler.py", "act"),
    ("delta_handler.py", "act"),
    ("effect_handler.py", "act"),
    ("tools.py", "act"),
    ("sandbox.py", "act"),
    ("transport.py", "act"),
    ("memory.py", "memory"),
    ("skills.py", "memory"),
    ("attachment.py", "memory"),
    ("workspace.py", "memory"),
    ("file_store.py", "memory"),
    ("search.py", "memory"),
    ("remember_effects.py", "memory"),
    ("team_seam.py", "collaboration"),
    ("team_caster.py", "collaboration"),
    ("team_casting_prompt_renderer.py", "collaboration"),
    ("team_role_library.py", "collaboration"),
    ("team_communication.py", "collaboration"),
    ("team_shared_memory.py", "collaboration"),
    ("session_service.py", "collaboration"),
    ("artifact_closure.py", "journal"),
    ("composition_invariant.py", "journal"),
    ("journal_store.py", "journal"),
    ("journal_store_factories.py", "journal"),
]

OLD_TO_NEW = {old[:-3]: pkg for old, pkg in MOVES}


def main():
    # 1. Create destination root + subpackages
    DEST_ROOT.mkdir(exist_ok=True)
    seen = set()
    for _, pkg in MOVES:
        if pkg in seen:
            continue
        (DEST_ROOT / pkg).mkdir(exist_ok=True)
        (DEST_ROOT / pkg / "__init__.py").write_text(
            f'"""{pkg} subpackage of lca.plugins.seams."""\n', encoding="utf-8"
        )
        seen.add(pkg)

    # 2. Move observability/ as-is
    src_obs = ROOT / "observability"
    dst_obs = DEST_ROOT / "observability"
    if src_obs.exists() and not dst_obs.exists():
        shutil.move(str(src_obs), str(dst_obs))

    # 3. Move individual files
    for old, pkg in MOVES:
        src = ROOT / old
        dst = DEST_ROOT / pkg / old
        if src.exists():
            shutil.move(str(src), str(dst))

    # 4. Remove old empty root (only if directory is empty)
    with suppress(OSError):
        ROOT.rmdir()

    # 5. Rewrite imports everywhere: seam_definitions -> seams.<pkg>
    old_prefix = "lca.plugins.seam_definitions"
    new_prefix = "lca.plugins.seams"
    sorted_old = sorted(set(OLD_TO_NEW.keys()), key=len, reverse=True)

    files = []
    for d in ("lca", "gateway", "tests", "scripts", "bundles", "profiles"):
        for py in Path(d).rglob("*.py"):
            if "__pycache__" not in py.parts:
                files.append(py)
    # Also handle YAML bundle / profile references
    yaml_files = []
    for d in ("bundles", "profiles"):
        for y in Path(d).rglob("*.yaml"):
            yaml_files.append(y)

    count = 0
    for f in files:
        text = f.read_text(encoding="utf-8")
        new_text = text
        # First: handle plain seam_definitions.observability.X (already-existing subdir)
        new_text = new_text.replace(f"{old_prefix}.observability", f"{new_prefix}.observability")
        # Then: handle each known module
        for old_mod in sorted_old:
            pkg = OLD_TO_NEW[old_mod]
            new_text = new_text.replace(
                f"from {old_prefix}.{old_mod}", f"from {new_prefix}.{pkg}.{old_mod}"
            )
            new_text = new_text.replace(f"{old_prefix}.{old_mod}", f"{new_prefix}.{pkg}.{old_mod}")
        # Finally: any remaining seam_definitions references (e.g. .seam_definitions itself)
        new_text = new_text.replace(old_prefix, new_prefix)
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
            count += 1

    # YAML files: just rename prefix
    yaml_count = 0
    for f in yaml_files:
        text = f.read_text(encoding="utf-8")
        new_text = text.replace(old_prefix, new_prefix)
        if new_text != text:
            f.write_text(new_text, encoding="utf-8")
            yaml_count += 1

    print(f"rewrote imports in {count} .py files + {yaml_count} .yaml files")


if __name__ == "__main__":
    main()
