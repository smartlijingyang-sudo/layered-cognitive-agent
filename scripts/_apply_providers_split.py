"""Phase B #6: split lca/plugins/providers/ into 14 subpackages.

Mirrors the 9 seams/ groups (state/perceive/think/gate/act/memory/
collaboration/journal/observability) so each provider joins its seam's
package, plus retains the 5 already-encapsulated subpackages
(event_identity/, journal_schema/, openai_stream_encoder/,
profile_snapshot/, run_ui_encoder/).

Before: 54 .py files flat in providers/ root + 11 in 5 subpackages.
After: 14 subpackages, 0 files in providers/ root except __init__.py.

New structure (largest = observability/ memory/ act at 8-13 files):
  state/             (5) state_store, component_state_store,
                         runtime_lifecycle, runtime_lifecycle_logging,
                         component_budget_policy
  perceive/          (2) phase_observer, phase_observer_tracing
  think/             (6) cognitive_think_pipeline,
                         cognitive_reflection_pipeline,
                         composition_composer, composition_provider,
                         loop_guard, llm
  gate/              (2) gate_chain_composer, decision_classifier
  act/               (8) action_handlers, delta_handlers,
                         delta_handler_registry, effect_handlers,
                         sandbox, transport, tools,
                         tool_batch_execution_policy
  memory/            (8) attachment, component_memory, file_store,
                         journal_memory, memory, search, skills, workspace
  collaboration/     (6) continuous_control_plane,
                         session_command_ledger,
                         session_followup_policy, session_persistence,
                         session_projections, session_turn_controller
  journal/           (4) artifact_closure, declarative_runtime_seams,
                         fact_store_memory, runtime_factory
  observability/    (13) attribute_policy, cli_debug_trace,
                         event_descriptor, evidence_store_filesystem,
                         fact_reader_console, fact_reader_jsonl,
                         fact_reader_langfuse, fact_reader_otel,
                         fact_scorer_langfuse, genai_llm, genai_tool,
                         tracer_otel, trace_tool
  event_identity/    (1) stable_ulid          (existing subdir)
  journal_schema/    (1) v2                   (existing subdir)
  openai_stream_encoder/ (2) _chunk, _encoder  (existing subdir)
  profile_snapshot/  (1) run_boot             (existing subdir)
  run_ui_encoder/    (1) _encoder             (existing subdir)
"""

import shutil
from pathlib import Path

ROOT = Path("lca/plugins/providers")

MOVES: list[tuple[str, str]] = [
    # state/
    ("state_store.py", "state"),
    ("component_state_store.py", "state"),
    ("runtime_lifecycle.py", "state"),
    ("runtime_lifecycle_logging.py", "state"),
    ("component_budget_policy.py", "state"),
    # perceive/
    ("phase_observer.py", "perceive"),
    ("phase_observer_tracing.py", "perceive"),
    # think/
    ("cognitive_think_pipeline.py", "think"),
    ("cognitive_reflection_pipeline.py", "think"),
    ("composition_composer.py", "think"),
    ("composition_provider.py", "think"),
    ("loop_guard.py", "think"),
    ("llm.py", "think"),
    # gate/
    ("gate_chain_composer.py", "gate"),
    ("decision_classifier.py", "gate"),
    # act/
    ("action_handlers.py", "act"),
    ("delta_handlers.py", "act"),
    ("delta_handler_registry.py", "act"),
    ("effect_handlers.py", "act"),
    ("sandbox.py", "act"),
    ("transport.py", "act"),
    ("tools.py", "act"),
    ("tool_batch_execution_policy.py", "act"),
    # memory/
    ("attachment.py", "memory"),
    ("component_memory.py", "memory"),
    ("file_store.py", "memory"),
    ("journal_memory.py", "memory"),
    ("memory.py", "memory"),
    ("search.py", "memory"),
    ("skills.py", "memory"),
    ("workspace.py", "memory"),
    # collaboration/
    ("continuous_control_plane.py", "collaboration"),
    ("session_command_ledger.py", "collaboration"),
    ("session_followup_policy.py", "collaboration"),
    ("session_persistence.py", "collaboration"),
    ("session_projections.py", "collaboration"),
    ("session_turn_controller.py", "collaboration"),
    # journal/
    ("artifact_closure.py", "journal"),
    ("declarative_runtime_seams.py", "journal"),
    ("fact_store_memory.py", "journal"),
    ("runtime_factory.py", "journal"),
    # observability/
    ("attribute_policy.py", "observability"),
    ("cli_debug_trace.py", "observability"),
    ("event_descriptor.py", "observability"),
    ("evidence_store_filesystem.py", "observability"),
    ("fact_reader_console.py", "observability"),
    ("fact_reader_jsonl.py", "observability"),
    ("fact_reader_langfuse.py", "observability"),
    ("fact_reader_otel.py", "observability"),
    ("fact_scorer_langfuse.py", "observability"),
    ("genai_llm.py", "observability"),
    ("genai_tool.py", "observability"),
    ("tracer_otel.py", "observability"),
    ("trace_tool.py", "observability"),
]

# Modules that stay in their existing subpackages (no move needed).
EXISTING_SUBDIR_MODULES = {
    # already at lca/plugins/providers/event_identity/
    "event_identity": [
        "stable_ulid",
    ],
    "journal_schema": [
        "v2",
    ],
    "openai_stream_encoder": [
        "_chunk",
        "_encoder",
    ],
    "profile_snapshot": [
        "run_boot",
    ],
    "run_ui_encoder": [
        "_encoder",
    ],
}

OLD_TO_NEW = {old[:-3]: pkg for old, pkg in MOVES}


def _rewrite_with_boundary(text: str, prefix: str, old_mod: str, new_tail: str) -> str:
    """Rewrite module references at module boundaries.

    Two forms are supported:

    * ``<prefix>.<old_mod>`` — the dotted module path used in YAML and in
      ``from X.Y import`` statements.
    * ``from <prefix> import <old_mod>`` — the bare-import form
      (``from lca.plugins.providers.state.state_store import state_store``).

    Both are bounded so a sibling path that already starts with the target
    subpackage (``lca.plugins.providers.<pkg>.X``) is not re-expanded into
    a doubled prefix.
    """
    import re

    dotted_pat = re.compile(rf"{re.escape(prefix)}\.{re.escape(old_mod)}(?![\w.])")
    text = dotted_pat.sub(f"{prefix}.{new_tail}", text)
    bare_pat = re.compile(rf"from {re.escape(prefix)} import {re.escape(old_mod)}(?![\w.])")
    return bare_pat.sub(f"from {prefix}.{new_tail} import {old_mod}", text)


# Modules whose new path uses a subpackage of the same name (e.g. memory.py
# becomes memory/memory.py). They must be rewritten in a separate pre-pass
# BEFORE the regular pass, otherwise a later pass that turns a sibling into
# "lca.plugins.providers.<pkg>.<mod>" would itself be re-expanded by the
# same-name pre-pass into "lca.plugins.providers.<pkg>.<pkg>.<mod>".
SELF_NAMED_MODS = sorted(mod for mod, pkg in OLD_TO_NEW.items() if mod == pkg)


def main() -> None:
    # 1. Create destination subpackages (only the 9 NEW ones; the 5
    #    existing subdirs already have __init__.py from a prior split).
    new_pkgs = {"state", "perceive", "think", "gate", "act", "memory", "collaboration", "journal"}
    for pkg in new_pkgs:
        (ROOT / pkg).mkdir(exist_ok=True)
        (ROOT / pkg / "__init__.py").write_text(
            f'"""{pkg} subpackage of lca.plugins.providers."""\n',
            encoding="utf-8",
        )
    # observability/ may already exist (sub-package v1) but ensure __init__.
    (ROOT / "observability").mkdir(exist_ok=True)
    if not (ROOT / "observability" / "__init__.py").exists():
        (ROOT / "observability" / "__init__.py").write_text(
            '"""observability subpackage of lca.plugins.providers."""\n',
            encoding="utf-8",
        )

    # 2. Move individual files
    for old, pkg in MOVES:
        src = ROOT / old
        dst = ROOT / pkg / old
        if src.exists():
            shutil.move(str(src), str(dst))

    # 3. Rewrite imports everywhere.
    new_prefix = "lca.plugins.providers"
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
        # Pre-pass: rewrite self-named modules first (memory -> memory.memory).
        # Anchored to end-of-line / non-word boundary so we don't expand a
        # sibling path that already starts with `<pkg>.`.
        for self_mod in SELF_NAMED_MODS:
            new_text = _rewrite_with_boundary(
                new_text, new_prefix, self_mod, f"{self_mod}.{self_mod}"
            )
        # Main pass: rewrite remaining modules (longest first, stable).
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
