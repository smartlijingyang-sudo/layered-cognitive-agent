"""PR-C compat residue guards.

After PR-C deletes 3 leftover Cordis-abstracted plugins
(``phase.think.role_profile`` / ``phase.think.reasoner.compose`` /
``lca-composer-provider``) and the corresponding capability keys
(``REASONER_ROLE_PROFILE`` / ``COMPOSITION_COMPOSE_FACTORY`` /
``COMPOSITION_INVARIANT_CHECKER``), these guards pin the end state:

* ``REASONER_ROLE_PROFILE`` capability constant is gone (no caller can
  import it; boot path does not register it).
* ``bundles/base.yaml`` + ``bundles/scenario-cordis-creator.yaml`` no
  longer register the 3 deleted plugin ids.

Negative grep (brief §4 个负向 grep) is also enforced at the module
level — this file is the ONLY allowed hit for the patterns.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]


def test_no_role_profile_capability() -> None:
    """PR-C end state: ``REASONER_ROLE_PROFILE`` Capability constant is removed.

    Brief item #4 / #5: ``REASONER_ROLE_PROFILE`` is gone from the
    Capability registry. Boot profile yaml does not list
    ``phase.think.role_profile`` plugin entry.
    """
    from lca.contracts import capabilities

    assert not hasattr(capabilities, "REASONER_ROLE_PROFILE"), (
        "REASONER_ROLE_PROFILE capability constant should be removed in PR-C"
    )

    # Confirm no plugin id `phase.think.role_profile` registered in boot
    # bundles/base.yaml.
    base = yaml.safe_load((REPO / "bundles" / "base.yaml").read_text(encoding="utf-8"))
    base_ids = {entry["id"] for entry in base.get("entries", [])}
    assert "phase.think.role_profile" not in base_ids, (
        f"phase.think.role_profile plugin should not be in bundles/base.yaml: {base_ids}"
    )


def test_no_reasoner_compose_plugin_registered() -> None:
    """PR-C end state: ``phase.think.reasoner.compose`` plugin not in base bundle."""
    base = yaml.safe_load((REPO / "bundles" / "base.yaml").read_text(encoding="utf-8"))
    base_ids = {entry["id"] for entry in base.get("entries", [])}
    assert "phase.think.reasoner.compose" not in base_ids, (
        f"phase.think.reasoner.compose plugin should not be in bundles/base.yaml: {base_ids}"
    )


def test_no_composer_provider_plugin_registered() -> None:
    """PR-C end state: ``lca-composer-provider`` plugin not in any boot bundle.

    PR-C only checks the 3 deleted plugin ids; the 4 ``lca-plan-*-composer``
    plugins are PR-D scope and not asserted here.
    """
    forbidden_pr_c = {"lca-composer-provider"}
    base = yaml.safe_load((REPO / "bundles" / "base.yaml").read_text(encoding="utf-8"))
    base_ids = {entry["id"] for entry in base.get("entries", [])}
    creator_path = REPO / "bundles" / "scenario-cordis-creator.yaml"
    if creator_path.exists():
        creator = yaml.safe_load(creator_path.read_text(encoding="utf-8"))
        creator_ids = {entry["id"] for entry in creator.get("entries", [])}
    else:
        creator_ids = set()
    leaked = (base_ids | creator_ids) & forbidden_pr_c
    assert not leaked, f"PR-C deleted plugin ids should not appear in boot bundles: {leaked}"


def test_no_composition_compose_factory_capability() -> None:
    """PR-C end state: ``COMPOSITION_COMPOSE_FACTORY`` Capability constant removed.

    The provider plugin is deleted; no caller should reference this constant.
    """
    from lca.contracts import capabilities

    assert not hasattr(capabilities, "COMPOSITION_COMPOSE_FACTORY"), (
        "COMPOSITION_COMPOSE_FACTORY capability constant should be removed in PR-C"
    )


def test_no_composition_invariant_checker_capability() -> None:
    """PR-C end state: ``COMPOSITION_INVARIANT_CHECKER`` Capability constant removed.

    The provider plugin (``lca-composition-invariant-default``) was an
    orphan after ``lca-composer-provider`` was deleted; PR-C removes
    both the provider plugin and the capability constant.
    """
    from lca.contracts import capabilities

    assert not hasattr(capabilities, "COMPOSITION_INVARIANT_CHECKER"), (
        "COMPOSITION_INVARIANT_CHECKER capability constant should be removed in PR-C"
    )


def test_no_phase_think_role_profile_plugin_file() -> None:
    """PR-C end state: source file for ``phase.think.role_profile`` plugin is gone."""
    assert not (REPO / "lca/plugins/think/role_profile_provider.py").exists(), (
        "lca/plugins/think/role_profile_provider.py should be deleted in PR-C"
    )


def test_no_phase_think_reasoner_compose_plugin_file() -> None:
    """PR-C end state: source file for ``phase.think.reasoner.compose`` plugin is gone."""
    assert not (REPO / "lca/plugins/think/reasoner/compose.py").exists(), (
        "lca/plugins/think/reasoner/compose.py should be deleted in PR-C"
    )


def test_no_lca_composer_provider_plugin_files() -> None:
    """PR-C end state: source files for ``lca-composer-provider`` pair are gone."""
    assert not (REPO / "lca/plugins/think/composition/composer_provider.py").exists(), (
        "lca/plugins/think/composition/composer_provider.py should be deleted in PR-C"
    )
    assert not (REPO / "lca/plugins/think/composition/provider_provider.py").exists(), (
        "lca/plugins/think/composition/provider_provider.py should be deleted in PR-C"
    )


def test_no_lca_composition_invariant_default_plugin_file() -> None:
    """PR-C end state: ``lca-composition-invariant-default`` plugin file gone."""
    assert not (REPO / "lca/plugins/journal/composition/invariant_seam.py").exists(), (
        "lca/plugins/journal/composition/invariant_seam.py should be deleted in PR-C"
    )


def test_cordis_composer_relocated_outside_think_composition() -> None:
    """PR-C end state: ``CordisComposer`` is importable from non-plugin helper.

    The deleted plugin location was ``lca/plugins/think/composition/``;
    PR-C relocates the class to ``lca/plugins/composer/composition/`` so
    downstream callers (``cordis_control`` tool + composition root) can
    import it directly.
    """
    relocated = REPO / "lca/plugins/composer/composition/cordis_composer.py"
    assert relocated.exists(), (
        "CordisComposer should be relocated to lca/plugins/composer/composition/cordis_composer.py"
    )
    # Sanity check: the relocation module is NOT a @plugin module.
    text = relocated.read_text(encoding="utf-8")
    assert "@plugin" not in text, (
        "cordis_composer.py is a non-plugin helper; @plugin decorator is forbidden"
    )


# ─────────────────────────────────────────────────────────────────────
# Negative-grep guard (brief §4 个负向 grep).
# ─────────────────────────────────────────────────────────────────────


_NEGATIVE_GREP_PATTERNS: dict[str, re.Pattern[str]] = {
    "grep1_role_profile": re.compile(
        # The bare capability identifiers. Excludes Python attribute access
        # (e.g. ``reasoner.role_profile``) which is a legitimate Brain/Reasoner
        # Protocol attribute, not a Cordis capability key.
        r"(?:^|[^\w.])phase\.think\.role_profile|(?:^|[^\w.])reasoner\.role_profile\b|REASONER_ROLE_PROFILE"
    ),
    "grep2_reasoner_compose": re.compile(
        # Bare capability / plugin identifiers, not Python attribute access.
        r"(?:^|[^\w.])phase\.think\.reasoner\.compose|reasoner\.compose_plugin"
    ),
    "grep3_compose_factory": re.compile(
        # Bare identifiers; ``composition.compose_factory`` may appear in
        # unrelated docs as the historical name; keep the literal matches.
        r"(?:^|[^\w.])lca-composer-provider\b|composition\.compose_factory|COMPOSITION_COMPOSE_FACTORY"
    ),
    "grep4_invariant_checker": re.compile(
        r"composition\.invariant_checker|COMPOSITION_INVARIANT_CHECKER"
    ),
}


def test_negative_grep_outside_this_file_has_zero_hits() -> None:
    """Brief §4 负向 grep:每个 pattern 只在本文件出现。

    这条 guard 静态扫描 lca/ 与 tests/ 目录,确认 4 个 pattern
    只在 ``tests/architecture/test_no_compat_residue.py`` 内出现
    (即本文件内的"删除验证断言"自己)。其他任何 lca/tests 文件出现
    这些 pattern 即为 PR-C 残留。
    """
    roots = [REPO / "lca", REPO / "tests"]
    allowed_file = Path(__file__).resolve()
    offenders: dict[str, list[str]] = {name: [] for name in _NEGATIVE_GREP_PATTERNS}
    for root in roots:
        if not root.exists():
            continue
        for py in sorted(root.rglob("*.py")):
            if py.resolve() == allowed_file:
                continue
            try:
                text = py.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for name, pat in _NEGATIVE_GREP_PATTERNS.items():
                if pat.search(text):
                    offenders[name].append(str(py.relative_to(REPO)))
    leaking = {name: paths for name, paths in offenders.items() if paths}
    assert not leaking, (
        "PR-C deleted traces still present outside "
        f"tests/architecture/test_no_compat_residue.py:\n"
        + "\n".join(f"  {name}: {paths}" for name, paths in sorted(leaking.items()))
    )


__all__ = [
    "test_no_role_profile_capability",
    "test_no_reasoner_compose_plugin_registered",
    "test_no_composer_provider_plugin_registered",
    "test_no_composition_compose_factory_capability",
    "test_no_composition_invariant_checker_capability",
    "test_no_phase_think_role_profile_plugin_file",
    "test_no_phase_think_reasoner_compose_plugin_file",
    "test_no_lca_composer_provider_plugin_files",
    "test_no_lca_composition_invariant_default_plugin_file",
    "test_cordis_composer_relocated_outside_think_composition",
    "test_negative_grep_outside_this_file_has_zero_hits",
]
